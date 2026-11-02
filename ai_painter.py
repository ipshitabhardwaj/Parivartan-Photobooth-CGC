"""
Real AI repainting: Stable Diffusion img2img on the GPU, sized for a 4 GB card (e.g. RTX 3050).

The photo is not filtered. A diffusion model regenerates it in the look's style (anime illustration,
cyberpunk lab, ...) while keeping the pose and face layout, using the standard recipe from the diffusers docs:

  * Stable Diffusion 1.5 family checkpoint (default Lykon/dreamshaper-7), fp16 -> about 2 GB of weights
  * LCM-LoRA (latent-consistency/lcm-lora-sdv1-5) so only ~4-5 denoising steps are needed (about 1-3 s on a 3050)
  * 512x512 working size, attention slicing; if 4 GB turns out not to be enough it falls back to CPU offload

Everything is optional: without torch/diffusers, a CUDA GPU or the downloaded model this module reports
"not available" and the kiosk keeps using the Pillow/Ollama look. Run `python setup_ai.py` once to install-check,
download the model (~2.3 GB, needs internet that one time) and measure the speed on your machine.

Environment variables (all optional):
  AI_MODEL       checkpoint (HF id or local folder), default Lykon/dreamshaper-7
  AI_LCM_LORA    LCM-LoRA id, default latent-consistency/lcm-lora-sdv1-5; "none" = normal sampler (slower, ~25 steps)
  AI_SIZE        working size, default 512 (4 GB cards: stay at 512, 576 at most)
  AI_THEMES      looks repainted by AI, default "Sci-Fi,Anime,Cats" (add Vintage to repaint that too)
  AI_BUDGET      seconds after the shutter press before giving up and using the quick look, default 24
  AI_STRENGTH_SCALE  multiplies every look's repaint strength (0.8 = closer to the photo, 1.2 = bolder), default 1.0
  AI_DEVICE      cuda (default) or cpu (far too slow for a kiosk, only for testing)
"""
import os
import threading
import time

import numpy as np
from PIL import Image, ImageEnhance

import exposure
import segment

try:
    import torch
    from diffusers import AutoPipelineForImage2Image, DPMSolverMultistepScheduler, LCMScheduler
    HAVE_LIBS = True
    IMPORT_ERROR = ""
except Exception as exc:                      # not installed, or a broken CUDA/DLL setup
    HAVE_LIBS = False
    IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

HERE = os.path.dirname(os.path.abspath(__file__))
LOADED_MARKER = os.path.join(HERE, ".ai_model_ok")      # written after the first successful load
MODEL_ID = os.environ.get("AI_MODEL", "Lykon/dreamshaper-7")
_lcm = os.environ.get("AI_LCM_LORA", "latent-consistency/lcm-lora-sdv1-5").strip()
LCM_LORA = "" if _lcm.lower() in ("", "none", "off", "0") else _lcm
SIZE = int(os.environ.get("AI_SIZE", "512"))
DEVICE = os.environ.get("AI_DEVICE", "cuda")
AI_THEMES = tuple(t.strip() for t in os.environ.get("AI_THEMES", "Sci-Fi,Anime,Cats").split(",") if t.strip())
AI_BUDGET = float(os.environ.get("AI_BUDGET", "24"))
STRENGTH_SCALE = float(os.environ.get("AI_STRENGTH_SCALE", "1.0"))   # <1 keeps faces closer to the photo, >1 repaints more

STEPS = 8 if LCM_LORA else 24                 # img2img only runs strength * steps of these (about 4-5 with LCM)
GUIDANCE = 1.5 if LCM_LORA else 6.5

NEGATIVE = ("lowres, blurry, deformed, bad anatomy, extra fingers, extra limbs, disfigured, mutated, "
            "text, watermark, signature, ugly, duplicate, cropped")

# strength = how far the model may move away from your photo (low keeps the face, high repaints more)
STYLES = {
    "Anime": {
        "prompt": "masterpiece, best quality, anime illustration of the same person, 2d, flat colors, clean line art, "
                  "cel shading, large expressive detailed eyes, glossy hair, soft pastel sky background with sparkles, "
                  "vibrant colors, detailed face, anime key visual",
        "strength": 0.6,
        "negative": "photo, photograph, realistic, 3d render, grainy, dull colors, dark, muddy, blurry, lowres",
    },
    "Cats": {
        "prompt": "cute warm anime illustration of the same person, cozy room, soft golden light, smooth cel shading, "
                  "whimsical, pastel colors, highly detailed, masterpiece",
        "strength": 0.5,
    },
    # Two passes: a strong repaint invents the lab around you, a gentle one keeps your face. They are merged with a
    # person cut-out (needs segment.py); without a usable cut-out one balanced pass is used instead.
    "Sci-Fi": {
        "prompt": "portrait of the same person, cyberpunk style, neon cyan rim light on the skin, glowing cybernetic "
                  "details, detailed face, cinematic lighting",
        "strength": 0.45,
        "scene_prompt": "futuristic cyberpunk robotics lab interior, holographic displays, glowing blueprint screens, "
                        "neon cyan and magenta lights, sunset city skyline seen through a large window, flying drones, "
                        "cinematic, highly detailed, empty room",
        "scene_strength": 0.9,
        "scene_negative": "person, people, man, woman, face, portrait, body, text, watermark",
        "rim": ((39, 230, 255), (255, 150, 70)),
        "single_prompt": "cyberpunk portrait of the same person in a futuristic lab, neon cyan and magenta rim light, "
                         "glowing holograms, city skyline at sunset through a large window, sci-fi, cinematic lighting, "
                         "highly detailed",
        "single_strength": 0.65,
    },
    "Vintage": {
        "prompt": "vintage black and white photobooth portrait of the same person, 1970s, soft focus, film grain, "
                  "highly detailed photograph",
        "strength": 0.35,
    },
}


def _fit_square(img, size):
    w, h = img.size
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    return img.resize((size, size), Image.LANCZOS)


class _Painter:
    def __init__(self):
        self.pipe = None
        self.ready = False          # loaded AND warmed up: only then are photos sent here
        self.offloaded = False
        self._load_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._warm_thread = None
        self.fails = 0
        self.disabled_until = 0.0
        self.last_error = ""

    # ---- availability -------------------------------------------------------------------------------------
    def why_not(self):
        if not HAVE_LIBS:
            return f"torch/diffusers are not installed or failed to load ({IMPORT_ERROR})"
        if DEVICE == "cuda" and not torch.cuda.is_available():
            return "no CUDA GPU found (install the CUDA build of torch, see README)"
        if time.time() < self.disabled_until:
            return f"paused after repeated errors: {self.last_error}"
        return ""

    def available(self):
        return not self.why_not()

    def note_failure(self, message):
        self.last_error = message
        self.fails += 1
        print(f"[AI] problem: {message}")
        if self.fails >= 3:                    # three in a row: something is really wrong, rest for a minute
            self.fails = 0
            self.disabled_until = time.time() + 60
            print("[AI] paused for 1 minute after 3 problems in a row; the quick look is used meanwhile")

    def note_ok(self):
        self.fails = 0

    # ---- loading --------------------------------------------------------------------------------------------
    def _build(self, offload):
        dtype = torch.float16 if DEVICE == "cuda" else torch.float32
        kwargs = dict(torch_dtype=dtype, safety_checker=None, requires_safety_checker=False, use_safetensors=True)
        try:
            pipe = AutoPipelineForImage2Image.from_pretrained(MODEL_ID, variant="fp16", **kwargs)
        except (ValueError, OSError):          # this repo has no separate fp16 files: take the default ones
            pipe = AutoPipelineForImage2Image.from_pretrained(MODEL_ID, **kwargs)
        if LCM_LORA:
            pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
            pipe.load_lora_weights(LCM_LORA)
            pipe.fuse_lora()
        else:
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True)
        pipe.set_progress_bar_config(disable=True)
        pipe.enable_attention_slicing()
        if DEVICE == "cuda" and offload:
            pipe.enable_model_cpu_offload()      # keeps only the active part on the GPU: slower but fits any card
        else:
            pipe.to(DEVICE)
        return pipe

    def ensure_loaded(self):
        with self._load_lock:
            if self.ready:
                return
            started = time.time()
            print(f"[AI] loading {MODEL_ID}" + (f" + {LCM_LORA}" if LCM_LORA else "") + " ...")
            if self.pipe is None:
                try:
                    self.pipe = self._build(offload=False)
                except torch.cuda.OutOfMemoryError:
                    print("[AI] GPU memory is tight, switching to CPU offload (slower)")
                    self._free()
                    self.pipe = self._build(offload=True)
                    self.offloaded = True
            where = torch.cuda.get_device_name(0) if DEVICE == "cuda" else DEVICE
            print(f"[AI] model loaded in {time.time() - started:.1f}s on {where}" + (" (CPU offload)" if self.offloaded else ""))
            # One throw-away picture now, so GPU kernels are compiled before the first real photo (it would otherwise
            # take several extra seconds and could miss the deadline).
            try:
                t0 = time.time()
                self._infer(Image.new("RGB", (SIZE, SIZE), (128, 128, 128)), "a portrait", NEGATIVE, 0.5)
                print(f"[AI] warm-up picture done in {time.time() - t0:.1f}s")
            except Exception as exc:
                print(f"[AI] warm-up picture failed ({exc}); continuing")
            self.ready = True
            self.last_error = ""
            print(f"[AI] ready ({time.time() - started:.1f}s in total)")
            try:
                open(LOADED_MARKER, "w").close()
            except OSError:
                pass

    def _free(self):
        self.pipe = None
        if HAVE_LIBS and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _can_run(self):
        """Libraries and GPU are there (ignores the temporary pause after generation errors)."""
        return HAVE_LIBS and not (DEVICE == "cuda" and not torch.cuda.is_available())

    def warming(self):
        """True while the model is being downloaded or loaded in the background."""
        return bool(self._warm_thread and self._warm_thread.is_alive())

    def warm_up_async(self):
        """
        Download (first time only) and load the model in the background. A dropped connection must not end this:
        Hugging Face downloads resume where they stopped, so just try again a few times with a growing pause.
        """
        if self.ready or self.warming() or not self._can_run():
            return

        def run():
            delay = 10
            for attempt in range(1, 41):
                try:
                    self.ensure_loaded()
                    return
                except Exception as exc:
                    self.last_error = f"could not load the model: {exc}"
                    print(f"[AI] model load problem (attempt {attempt}): {exc}")
                    print(f"[AI] trying again in {delay}s; an interrupted download resumes where it stopped")
                    time.sleep(delay)
                    delay = min(60, delay * 2)
            print("[AI] giving up on loading the model. Check the internet connection and restart.")
        self._warm_thread = threading.Thread(target=run, name="ai-warmup", daemon=True)
        self._warm_thread.start()

    # ---- painting -------------------------------------------------------------------------------------------
    def _infer(self, source, prompt, negative, strength):
        """One img2img pass. Retries once with CPU offload if the GPU runs out of memory."""
        seed = int.from_bytes(os.urandom(4), "little")
        args = dict(prompt=prompt, negative_prompt=negative, image=source, strength=strength,
                    num_inference_steps=STEPS, guidance_scale=GUIDANCE)
        try:
            return self.pipe(generator=torch.Generator("cpu").manual_seed(seed), **args).images[0].convert("RGB")
        except torch.cuda.OutOfMemoryError:
            print("[AI] out of GPU memory, retrying with CPU offload")
            self._free()
            self.pipe = self._build(offload=True)
            self.offloaded = True
            return self.pipe(generator=torch.Generator("cpu").manual_seed(seed), **args).images[0].convert("RGB")

    def paint(self, img, theme, alpha=None):
        """
        Regenerate `img` (PIL RGB) in the style of `theme`. Returns a PIL RGB image at 768x768.
        `alpha` is an optional person cut-out (float 0..1, any size): with it, looks that define a scene (Sci-Fi) paint
        the surroundings strongly and the person gently, then merge them.
        """
        style = STYLES[theme]
        self.ensure_loaded()
        scale = lambda s: min(0.92, max(0.2, s * STRENGTH_SCALE))
        extra = lambda text: NEGATIVE + (", " + text if text else "")
        with self._run_lock:
            source = _fit_square(exposure.normalize_exposure(img.convert("RGB")), SIZE)   # dark faces repaint badly
            started = time.time()
            if alpha is not None and style.get("scene_prompt"):
                scene = self._infer(source, style["scene_prompt"], extra(style.get("scene_negative")), scale(style["scene_strength"]))
                person = self._infer(source, style["prompt"], extra(style.get("negative")), scale(style["strength"]))
                out = _merge(person, scene, alpha, style.get("rim"))
                how = "scene + person"
            else:
                prompt, strength = style.get("single_prompt", style["prompt"]), style.get("single_strength", style["strength"])
                out = self._infer(source, prompt, extra(style.get("negative")), scale(strength))
                how = "single pass"
            print(f"[AI] {theme} painted ({how}) in {time.time() - started:.1f}s")
        self.note_ok()
        out = out.convert("RGB").resize((768, 768), Image.LANCZOS)
        return ImageEnhance.Sharpness(out).enhance(1.25)          # img2img + upscale is a touch soft


def _merge(person, scene, alpha, rim):
    """Put the gently repainted person on top of the strongly repainted scene, with optional rim light."""
    size = person.size
    a8 = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype("uint8"), "L").resize(size, Image.LANCZOS)
    if rim:
        soft = np.asarray(a8).astype("float32") / 255.0
        person_rgba = segment.cutout_with_rim(person, soft, rim[0], rim[1])
        return Image.alpha_composite(scene.convert("RGBA"), person_rgba).convert("RGB")
    return Image.composite(person, scene, a8)


_painter = _Painter()


def wants(theme):
    """
    True if this look should be repainted by AI right now. Only once the model is loaded: a photo taken while it is
    still downloading gets the quick look immediately instead of waiting (and the wait is not counted as a failure).
    """
    return theme in AI_THEMES and _painter.available() and _painter.ready


def available():
    return _painter.available()


def warming():
    return _painter.warming()


def loaded():
    """True once the model is in GPU memory and warmed up, so the first photo will be fast."""
    return _painter.ready


def last_error():
    return _painter.last_error


def why_not():
    return _painter.why_not()


def warm_up_async():
    _painter.warm_up_async()


def paint(img, theme, alpha=None):
    return _painter.paint(img, theme, alpha)


def note_failure(message):
    _painter.note_failure(message)
