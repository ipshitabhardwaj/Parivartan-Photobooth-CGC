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

from PIL import Image, ImageEnhance

import exposure

try:
    import torch
    from diffusers import AutoPipelineForImage2Image, DPMSolverMultistepScheduler, LCMScheduler
    HAVE_LIBS = True
    IMPORT_ERROR = ""
except Exception as exc:                      # not installed, or a broken CUDA/DLL setup
    HAVE_LIBS = False
    IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

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
    "Sci-Fi": {
        "prompt": "cyberpunk portrait of the same person in a futuristic lab, neon cyan and magenta rim light, glowing "
                  "holograms, city skyline at sunset through a large window, sci-fi, cinematic lighting, highly detailed",
        "strength": 0.65,
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
        if self.fails >= 2:
            self.fails = 0
            self.disabled_until = time.time() + 300
            print("[AI] paused for 5 minutes; the quick look is used meanwhile")

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
            if self.pipe is not None:
                return
            started = time.time()
            print(f"[AI] loading {MODEL_ID}" + (f" + {LCM_LORA}" if LCM_LORA else "") + " ...")
            try:
                self.pipe = self._build(offload=False)
            except torch.cuda.OutOfMemoryError:
                print("[AI] GPU memory is tight, switching to CPU offload (slower)")
                self._free()
                self.pipe = self._build(offload=True)
                self.offloaded = True
            where = torch.cuda.get_device_name(0) if DEVICE == "cuda" else DEVICE
            print(f"[AI] ready in {time.time() - started:.1f}s on {where}" + (" (CPU offload)" if self.offloaded else ""))

    def _free(self):
        self.pipe = None
        if HAVE_LIBS and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def warm_up_async(self):
        """Load the model in the background so the first photo doesn't pay for it."""
        if self.pipe is not None or (self._warm_thread and self._warm_thread.is_alive()) or not self.available():
            return

        def run():
            try:
                self.ensure_loaded()
            except Exception as exc:
                self.note_failure(f"could not load the model: {exc}. Run python setup_ai.py (needs internet once)")
        self._warm_thread = threading.Thread(target=run, daemon=True)
        self._warm_thread.start()

    # ---- painting -------------------------------------------------------------------------------------------
    def paint(self, img, theme):
        """Regenerate `img` (PIL RGB) in the style of `theme`. Returns a PIL RGB image at 768x768."""
        style = STYLES[theme]
        self.ensure_loaded()
        with self._run_lock:
            source = _fit_square(exposure.normalize_exposure(img.convert("RGB")), SIZE)   # dark faces repaint badly
            seed = int.from_bytes(os.urandom(4), "little")
            args = dict(prompt=style["prompt"], negative_prompt=NEGATIVE + (", " + style["negative"] if style.get("negative") else ""), image=source, strength=min(0.9, max(0.2, style["strength"] * STRENGTH_SCALE)),
                        num_inference_steps=STEPS, guidance_scale=GUIDANCE)
            started = time.time()
            try:
                out = self.pipe(generator=torch.Generator("cpu").manual_seed(seed), **args).images[0]
            except torch.cuda.OutOfMemoryError:
                print("[AI] out of GPU memory, retrying with CPU offload")
                self._free()
                self.pipe = self._build(offload=True)
                self.offloaded = True
                out = self.pipe(generator=torch.Generator("cpu").manual_seed(seed), **args).images[0]
            print(f"[AI] {theme} painted in {time.time() - started:.1f}s")
        self.note_ok()
        out = out.convert("RGB").resize((768, 768), Image.LANCZOS)
        return ImageEnhance.Sharpness(out).enhance(1.25)          # img2img + upscale is a touch soft


_painter = _Painter()


def wants(theme):
    """True if this look should be repainted by AI right now."""
    return theme in AI_THEMES and _painter.available()


def available():
    return _painter.available()


def why_not():
    return _painter.why_not()


def warm_up_async():
    _painter.warm_up_async()


def paint(img, theme):
    return _painter.paint(img, theme)


def note_failure(message):
    _painter.note_failure(message)
