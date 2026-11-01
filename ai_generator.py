"""
Photo restyling pipeline. Order of attempts for every photo:

  1. AI repainting (ai_painter.py): Stable Diffusion img2img regenerates the picture in the look's style.
     Used for the looks in AI_THEMES whenever torch + a CUDA GPU + the model are available.
  2. (opt-in) Stable Diffusion WebUI (AUTOMATIC1111) img2img, if SD_API_HOST is set.
  3. Ollama vision model designs a recipe, Pillow renders it (only when the AI painter isn't available,
     because both would compete for the 4 GB of GPU memory).
  4. The theme's default recipe rendered with Pillow (no AI needed).

The browser then adds SVG stickers/frame/caption on top (see svgfx.js), and can also do the
colour styling itself with SVG filters if this server can't be reached.

Optional but recommended: `pip install numpy opencv-python-headless` gives much cleaner
skin/paint smoothing (bilateral filter). Without it a simpler Pillow blur is used.
"""
import os
import base64
import io
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import requests
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except Exception as exc:               # missing, or built for a different NumPy: still works, just less refined
    HAS_CV2 = False
    print(f"[Quality] OpenCV is not usable ({type(exc).__name__}): smoothing, exposure fix and cut-outs are reduced. "
          "Fix: py -m pip install --upgrade opencv-python-headless   (or just run start_kiosk.bat)")

import ai_painter
import exposure
import ollama_client
import segment
from recipes import THEMES, default_recipe, sanitize_recipe

# Optional Stable Diffusion WebUI (AUTOMATIC1111). Off unless you set SD_API_HOST,
# e.g. http://127.0.0.1:7860  (start the WebUI with --api, and --medvram on a 4 GB GPU).
SD_API_HOST = os.environ.get("SD_API_HOST", "").rstrip("/")
SD_THEMES = tuple(t.strip() for t in os.environ.get("SD_THEMES", "Anime").split(",") if t.strip())
SD_SIZE = int(os.environ.get("SD_SIZE", "512"))      # 512 fits a 4 GB GPU; 768 does not

SD_PROMPTS = {
    "Anime": {
        "positive": "anime style portrait of the same person, smooth cel shading, soft clean line art, "
                    "large expressive detailed eyes, glossy hair, vibrant soft colours, gentle rim light, "
                    "digital illustration, high quality, masterpiece",
        "denoise": 0.5,
    },
    "Sci-Fi": {"positive": "cinematic sci-fi portrait, neon rim light, futuristic, detailed, high quality", "denoise": 0.4},
    "Cats": {"positive": "cute portrait, soft warm light, pastel, whimsical, high quality", "denoise": 0.35},
    "Vintage": {"positive": "vintage black and white photobooth portrait, film grain, high quality", "denoise": 0.35},
}
SD_NEGATIVE = "blurry, lowres, deformed, bad anatomy, extra fingers, text, watermark, disfigured"


def decode_base64_image(base64_str):
    """Clean and decode base64 image data."""
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    image_bytes = base64.b64decode(base64_str)
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def encode_pil_image(image, format="JPEG", quality=92):
    """Encode PIL image to data URL."""
    buffered = io.BytesIO()
    image.save(buffered, format=format, quality=quality)
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{img_b64}"


def encode_png(image):
    """Encode an RGBA PIL image to a PNG data URL (keeps transparency)."""
    buffered = io.BytesIO()
    image.save(buffered, format="PNG", compress_level=3)
    return "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode("utf-8")


def try_sd_webui_img2img(source, theme):
    """Stable Diffusion WebUI img2img at a size a 4 GB GPU can handle. Returns a data URL or None."""
    cfg = SD_PROMPTS.get(theme, SD_PROMPTS["Anime"])
    try:
        small = source.resize((SD_SIZE, SD_SIZE), Image.LANCZOS)
        buf = io.BytesIO()
        small.save(buf, format="PNG")
        payload = {
            "init_images": [base64.b64encode(buf.getvalue()).decode("utf-8")],
            "prompt": cfg["positive"],
            "negative_prompt": SD_NEGATIVE,
            "denoising_strength": cfg["denoise"],   # low enough to keep the person recognisable
            "steps": 22,
            "cfg_scale": 7,
            "width": SD_SIZE,
            "height": SD_SIZE,
            "sampler_name": "Euler a",
        }
        res = requests.post(f"{SD_API_HOST}/sdapi/v1/img2img", json=payload, timeout=(3, 240))
        if res.status_code == 200:
            images = res.json().get("images") or []
            if images:
                out = Image.open(io.BytesIO(base64.b64decode(images[0]))).convert("RGB")
                return encode_pil_image(out.resize((768, 768), Image.LANCZOS))
        print(f"[SD WebUI] unexpected answer: HTTP {res.status_code}")
    except Exception as e:
        print(f"[SD WebUI] img2img not available: {e}")
    return None


# ---------------------------------------------------------------------------
# Recipe renderer: turns a (sanitised) recipe into pixels.
# ---------------------------------------------------------------------------
def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _smooth(img, amount):
    """Edge-preserving smoothing: flattens skin/paint texture but keeps edges (eyes, hair, outlines)."""
    if amount < 0.02:
        return img
    if HAS_CV2:
        arr = np.asarray(img)
        passes = 1 + int(round(amount * 3))
        sigma = 25 + amount * 45
        for _ in range(passes):
            arr = cv2.bilateralFilter(arr, 7, sigma, 6)
        return Image.fromarray(arr)
    soft = img.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(1.0))
    return Image.blend(img, soft, min(1.0, amount))


def _flatten(img, amount):
    """Cel-shading: mean-shift filtering merges similar colours into flat patches (works at 512px for speed)."""
    if amount < 0.02 or not HAS_CV2:
        return img
    arr = np.asarray(img)
    h, w = arr.shape[:2]
    small = cv2.resize(arr, (512, 512), interpolation=cv2.INTER_AREA) if max(h, w) > 512 else arr
    flat = cv2.pyrMeanShiftFiltering(small, int(6 + amount * 10), int(12 + amount * 24), 1)
    if small is not arr:
        flat = cv2.resize(flat, (w, h), interpolation=cv2.INTER_CUBIC)
    return Image.fromarray(flat)


def _hue_shift(img, degrees):
    h, s, v = img.convert("HSV").split()
    delta = int(round(degrees * 255 / 360))
    h = h.point(lambda i: (i + delta) % 256)
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def _warmth(img, amount):
    if abs(amount) < 0.02:
        return img
    r, g, b = img.split()
    r = r.point(lambda i: min(255, int(i * (1 + 0.22 * amount))))
    b = b.point(lambda i: min(255, int(i * (1 - 0.22 * amount))))
    return Image.merge("RGB", (r, g, b))


def _bloom(img, amount):
    """Soft glow from the bright parts only (dreamy, not washed out)."""
    radius = max(4, img.size[0] // 40)
    bright = img.point(lambda i: max(0, i - 125) * 255 // 130)
    glow = bright.filter(ImageFilter.GaussianBlur(radius))
    return Image.blend(img, ImageChops.screen(img, glow), min(1.0, amount))


def _line_mask(base, mode):
    """Clean outline mask from the smoothed photo (never from raw sensor noise)."""
    if HAS_CV2 and mode == "ink":
        # adaptive threshold finds contours; keeping only larger connected strokes removes speckle
        gray = cv2.medianBlur(cv2.cvtColor(np.asarray(base), cv2.COLOR_RGB2GRAY), 5)
        lines = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 11, 7)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(lines, connectivity=8)
        big = np.flatnonzero(stats[1:, cv2.CC_STAT_AREA] >= 120) + 1
        keep = np.isin(labels, big).astype(np.uint8) * 255
        return Image.fromarray(cv2.GaussianBlur(keep, (0, 0), 0.8))
    gray = base.convert("L").filter(ImageFilter.GaussianBlur(1.3))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageEnhance.Contrast(edges).enhance(3.0)
    mask = edges.point(lambda p: 255 if p > 70 else 0)
    mask = mask.filter(ImageFilter.MedianFilter(5))            # drops isolated specks
    if mode == "ink":
        mask = mask.filter(ImageFilter.GaussianBlur(0.7))      # softer, pen-like line
    return mask


def apply_recipe(img, r):
    """Render a recipe (see recipes.py) onto a PIL RGB image."""
    img = exposure.normalize_exposure(img)               # fix dark/blown-out webcam frames before styling
    size = img.size
    pal = [_rgb(c) for c in r["palette"]]
    mode = r.get("edge_mode", "glow")

    out = _flatten(_smooth(img, r.get("smooth", 0.0)), r.get("flatten", 0.0))
    base = out                                              # lines are traced from the smoothed photo

    if r["blur"] > 0.05:
        out = out.filter(ImageFilter.GaussianBlur(r["blur"]))
    if abs(r["sharpen"] - 1) > 0.02:
        out = ImageEnhance.Sharpness(out).enhance(r["sharpen"])
    if abs(r["hue_shift"]) > 0.5:
        out = _hue_shift(out, r["hue_shift"])

    out = ImageEnhance.Brightness(out).enhance(r["brightness"])
    out = ImageEnhance.Contrast(out).enhance(r["contrast"])
    out = ImageEnhance.Color(out).enhance(r["saturation"])
    out = _warmth(out, r["warmth"])

    if r["posterize_bits"] < 8:
        out = ImageOps.posterize(out, int(r["posterize_bits"]))

    if r["tint"] > 0.01:                                    # gradient-map the photo through the palette
        gray = ImageOps.autocontrast(out.convert("L"), cutoff=1)
        mapped = ImageOps.colorize(gray, black=pal[0], mid=pal[1], white=pal[2])
        out = Image.blend(out, mapped, r["tint"])

    strength = r["edge_strength"]
    if strength > 0.02:
        mask = _line_mask(base, mode)
        if mode == "ink":
            ink = Image.new("RGB", size, tuple(int(c * 0.5) for c in pal[0]))
            out = Image.composite(ink, out, mask.point(lambda p: int(p * strength * 1.3)))
        else:
            line = Image.new("RGB", size, pal[2])
            out = Image.composite(line, out, mask.point(lambda p: int(p * strength * 1.6)))

    if r.get("bloom", 0) > 0.02:
        out = _bloom(out, r["bloom"])

    if r["grain"] > 0.02:                                   # noise is centred on 128, so subtract 128
        noise = Image.effect_noise(size, 60 * r["grain"]).filter(ImageFilter.GaussianBlur(0.6)).convert("RGB")
        out = ImageChops.add(out, noise, 1.0, -128)         # blurred a touch: film grain, not digital noise

    if r["vignette"] > 0.02:
        w, h = size
        centre = Image.new("L", size, 0)
        ImageDraw.Draw(centre).ellipse([(-w * 0.15, -h * 0.15), (w * 1.15, h * 1.15)], fill=255)
        centre = centre.filter(ImageFilter.GaussianBlur(radius=w // 6))
        amount = r["vignette"]
        keep = centre.point(lambda p: int(255 * (1 - amount) + p * amount))
        edge = Image.new("RGB", size, tuple(int(c * 0.5) for c in pal[0]))
        out = Image.composite(out, edge, keep)

    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
LOOK_BUDGET = ollama_client.LOOK_BUDGET
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ollama")
_jobs = {}                      # prepare_id -> (started_at, future, theme)
_jobs_lock = threading.Lock()


def _small_jpeg_b64(img, max_side=384):
    """A small picture is all the vision model needs, and far quicker to encode on a laptop GPU."""
    small = img.copy()
    small.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    small.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


_ai_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai")


def _ai_recipe(theme):
    """Overlays for an AI-repainted picture: the AI already painted the scene, so Sci-Fi gets nothing on top."""
    recipe = default_recipe(theme)
    if theme == "Sci-Fi":
        recipe.update(stickers=[], frame="none", caption_style="none")
    return recipe


def _run_ai(source, theme, prepare_id):
    """Repaint with the AI model, but never wait past AI_BUDGET seconds after the shutter press."""
    with _jobs_lock:
        job = _jobs.pop(prepare_id, None) if prepare_id else None
    started = job[0] if job else time.time()
    remaining = max(1.0, ai_painter.AI_BUDGET - (time.time() - started))
    future = _ai_pool.submit(ai_painter.paint, source, theme)
    try:
        return future.result(timeout=remaining), "ok"
    except FutureTimeout:
        ai_painter.note_failure(f"took longer than {int(ai_painter.AI_BUDGET)}s")
        return None, f"AI painter took longer than {int(ai_painter.AI_BUDGET)}s"
    except Exception as exc:
        ai_painter.note_failure(str(exc))
        return None, f"AI painter error: {exc}"


def prepare_look(base64_input, theme):
    """
    Start the Ollama step right now (the browser calls this when the shutter is pressed), so it runs
    while the countdown is still ticking. Returns an id that reimagine_image() picks the answer up with.
    """
    if theme not in THEMES:
        theme = "Sci-Fi"
    started = time.time()
    if ai_painter.available():
        # The AI painter owns the GPU: make sure its model is loaded, and keep Ollama out of it (VRAM).
        ai_painter.warm_up_async()
        prepare_id = uuid.uuid4().hex
        with _jobs_lock:
            _jobs[prepare_id] = (started, None, theme)
        return prepare_id
    image_b64 = _small_jpeg_b64(decode_base64_image(base64_input))
    future = _pool.submit(ollama_client.request_recipe, image_b64, theme, LOOK_BUDGET)
    prepare_id = uuid.uuid4().hex
    with _jobs_lock:
        for key in [k for k, (t0, _, _) in _jobs.items() if started - t0 > 120]:
            _jobs.pop(key, None)                        # forget jobs nobody collected
        _jobs[prepare_id] = (started, future, theme)
    return prepare_id


def _collect_recipe(prepare_id, theme, source):
    """Get the model's recipe, but never wait past LOOK_BUDGET seconds after the shutter press."""
    if ai_painter.available():
        return None, None, "Ollama is not used while the AI painter owns the GPU"
    with _jobs_lock:
        job = _jobs.pop(prepare_id, None) if prepare_id else None
    if job and job[2] == theme and job[1] is not None:
        started, future, _ = job
    else:
        started = time.time()
        future = _pool.submit(ollama_client.request_recipe, _small_jpeg_b64(source), theme, LOOK_BUDGET)
    remaining = max(0.5, LOOK_BUDGET - (time.time() - started))
    try:
        return future.result(timeout=remaining)
    except FutureTimeout:                               # (the slow request records its own failure)
        return None, None, f"Ollama didn't answer within {int(LOOK_BUDGET)}s"
    except Exception as exc:
        return None, None, f"Ollama error: {exc}"


def _anime_background(size):
    """Soft pastel anime sky: lavender -> pink -> cream, with a few blurred bokeh lights."""
    w, h = size
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    top, mid, bottom = (np.array(c, np.float32) for c in ((170, 150, 255), (255, 168, 212), (255, 238, 205)))
    col = np.where(t < 0.55, top + (mid - top) * (t / 0.55), mid + (bottom - mid) * ((t - 0.55) / 0.45))
    bg = Image.fromarray(np.repeat(col, w, axis=1).astype(np.uint8), "RGB").convert("RGBA")
    rng = np.random.default_rng(7)
    bokeh = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(bokeh)
    for _ in range(26):
        r = int(rng.uniform(0.015, 0.06) * w)
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.85)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, int(rng.uniform(40, 110))))
    return Image.alpha_composite(bg, bokeh.filter(ImageFilter.GaussianBlur(w / 220)))


def _finish(styled, source, theme, recipe):
    """
    Final encoding. For Sci-Fi, cut the person out and add rim light so the browser can drop them into
    the cyberpunk scene. Returns (data_url, cutout_flag); falls back to the plain photo if no cut-out.
    """
    if theme == "Sci-Fi":
        alpha = segment.person_alpha(source)
        if alpha is not None:
            pal = recipe["palette"]
            rgba = segment.cutout_with_rim(styled, alpha, _rgb(pal[2]), (255, 150, 70))
            return encode_png(rgba), True
    if theme == "Anime":
        # quick look only: put the illustrated person in front of a pastel anime sky instead of the real wall
        alpha = segment.person_alpha(source)
        if alpha is not None:
            person = segment.cutout_with_rim(styled, alpha, (255, 214, 236), (255, 244, 205))
            scene = Image.alpha_composite(_anime_background(styled.size), person)
            return encode_pil_image(scene.convert("RGB")), False
    return encode_pil_image(styled), False


def reimagine_image(base64_input, theme, prepare_id=None):
    """
    Restyle a photo. Always returns a dict:
      image   data URL of the styled photo
      method  "ai" | "ollama" | "builtin" | "sd"
      model   Ollama model name (or None)
      recipe  the look used; the browser draws stickers/frame/caption from it
      cutout  True when image is a transparent person cut-out (Sci-Fi scene); False for a normal photo
      note    one human-readable sentence about what happened (for logs)
    """
    if theme not in THEMES:
        theme = "Sci-Fi"
    started = time.time()
    source = decode_base64_image(base64_input)
    source.thumbnail((1024, 1024))

    if SD_API_HOST and theme in SD_THEMES:
        sd_result = try_sd_webui_img2img(source, theme)
        if sd_result:
            return {"image": sd_result, "method": "sd", "model": None, "cutout": False,
                    "recipe": default_recipe(theme), "note": "Repainted with Stable Diffusion."}

    message = ""
    if ai_painter.wants(theme):
        painted, message = _run_ai(source, theme, prepare_id)
        if painted is not None:
            recipe = _ai_recipe(theme)
            if theme == "Vintage":                      # the model paints a clean picture: add the film look on top
                painted = apply_recipe(painted, recipe)
            print(f"[Look] AI repainted '{theme}' {time.time() - started:.1f}s after the photo arrived")
            return {"image": encode_pil_image(painted), "method": "ai", "model": ai_painter.MODEL_ID,
                    "recipe": recipe, "cutout": False, "note": f"Repainted by {ai_painter.MODEL_ID}."}
        raw, model = None, None                         # AI failed or was too slow: quick look, no more waiting
    else:
        raw, model, message = _collect_recipe(prepare_id, theme, source)
    if raw is not None:
        try:
            recipe = sanitize_recipe(raw, theme)
            styled = apply_recipe(source, recipe)
            image, cutout = _finish(styled, source, theme, recipe)
            print(f"[Look] {model} recipe '{recipe['caption']}' ready {time.time() - started:.1f}s after the photo")
            return {"image": image, "method": "ollama", "model": model, "recipe": recipe, "cutout": cutout,
                    "note": f"{model} designed this look."}
        except Exception as exc:                        # bad recipe must never cost the user their photo
            message = f"the model's recipe couldn't be rendered ({exc})"
    print(f"[Look] standard look used: {message}")

    recipe = default_recipe(theme)
    styled = apply_recipe(source, recipe)
    image, cutout = _finish(styled, source, theme, recipe)
    return {"image": image, "method": "builtin", "model": None, "recipe": recipe, "cutout": cutout,
            "note": f"Standard look used: {message}"}
