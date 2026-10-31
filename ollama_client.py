"""
Bridge to a local Ollama server.

Ollama's regular models do not output pictures, so we use a *vision* model as
an art director: it looks at the photo and returns a tiny JSON "recipe" (caption,
palette, three tone numbers). ai_generator.py renders it. The step is kept small and
time-boxed so a photo is ready in well under 30 seconds on a laptop GPU:

  * it is started the moment the shutter button is pressed, so it overlaps the countdown
  * the model only has to write ~60 tokens, from a 384px picture
  * if it hasn't answered within LOOK_BUDGET seconds the standard look is used instead
  * if it is repeatedly too slow it is skipped for a few minutes

Environment variables (all optional):
  OLLAMA_HOST        default http://127.0.0.1:11434
  OLLAMA_MODEL       force a model, e.g. moondream (default: auto-pick the fastest installed)
  LOOK_BUDGET        seconds from pressing the shutter to give up on Ollama (default 14)
  OLLAMA_KEEP_ALIVE  how long Ollama keeps the model loaded (default 60m)
"""
import json
import os
import re
import threading
import time

import requests

from recipes import DEFAULT_RECIPES, THEME_BRIEFS

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "").strip()
LOOK_BUDGET = float(os.environ.get("LOOK_BUDGET", "14"))
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "60m")

# Fastest first. On a 4 GB GPU a model that fits entirely in VRAM (moondream, llava-phi3) is several
# times quicker than a bigger one that spills to the CPU, so those are preferred when installed.
VISION_FAMILIES = ["moondream", "llava-phi3", "qwen2.5vl", "gemma3", "minicpm-v",
                   "qwen3-vl", "llava", "llama3.2-vision", "bakllava"]
SUGGESTED_MODEL = "moondream"

_STATUS_TTL = 15  # seconds
_lock = threading.Lock()
_cache = {"at": 0.0, "status": None}

# Structured-output schema: Ollama constrains the model to emit exactly this (kept tiny on purpose).
RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "caption": {"type": "string"},
        "palette": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
        "brightness": {"type": "number"},
        "saturation": {"type": "number"},
        "warmth": {"type": "number"},
    },
    "required": ["caption", "palette", "brightness", "saturation", "warmth"],
}

# Back-off: after repeated slow/failed answers, stop asking for a while so photos stay instant.
SKIP_AFTER = 2
SKIP_SECONDS = 300
_breaker = {"fails": 0, "skip_until": 0.0}


def record_failure():
    with _lock:
        _breaker["fails"] += 1
        if _breaker["fails"] >= SKIP_AFTER:
            _breaker.update(fails=0, skip_until=time.time() + SKIP_SECONDS)
            print(f"[Ollama] too slow or failing: skipping it for {SKIP_SECONDS // 60} minutes")


def record_success():
    with _lock:
        _breaker["fails"] = 0


def _base_name(name):
    return name.split(":", 1)[0].lower()


def _family_rank(name):
    base = _base_name(name)
    for i, family in enumerate(VISION_FAMILIES):
        if base == family or base.endswith("/" + family):
            return i
    return None


def _is_vision(name):
    """Prefer Ollama's own capability list; fall back to known family names."""
    try:
        res = requests.post(f"{OLLAMA_HOST}/api/show", json={"model": name}, timeout=4)
        if res.ok:
            caps = res.json().get("capabilities")
            if isinstance(caps, list):
                return "vision" in caps
    except requests.RequestException:
        pass
    return _family_rank(name) is not None


def _discover():
    """Ask Ollama what is installed and pick a model. Returns a status dict."""
    status = {"available": False, "model": None, "host": OLLAMA_HOST, "reason": "", "installed": []}
    try:
        res = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        res.raise_for_status()
        models = res.json().get("models", [])
    except (requests.RequestException, ValueError):
        status["reason"] = "Ollama isn't running. Start it with: ollama serve"
        return status

    names = [m.get("name", "") for m in models if m.get("name")]
    status["installed"] = names

    if OLLAMA_MODEL:
        wanted = OLLAMA_MODEL.lower()
        match = next((n for n in names if n.lower() == wanted or n.lower() == wanted + ":latest"), None)
        if match:
            status.update(available=True, model=match)
        else:
            status["reason"] = f"Model '{OLLAMA_MODEL}' isn't installed. Run: ollama pull {OLLAMA_MODEL}"
        return status

    sizes = {m.get("name"): m.get("size", 0) for m in models}
    ranked = sorted((n for n in names if _family_rank(n) is not None),
                    key=lambda n: (_family_rank(n), sizes.get(n, 0)))
    others = [n for n in names if n not in ranked]
    # Known families first (smallest first), then anything else Ollama says can see images.
    # _is_vision also weeds out text-only siblings such as gemma3:1b.
    for name in ranked + others:
        if _is_vision(name):
            status.update(available=True, model=name)
            return status
    status["reason"] = f"No vision model installed. Run: ollama pull {SUGGESTED_MODEL}"
    return status


def get_status(force=False):
    with _lock:
        if not force and _cache["status"] and time.time() - _cache["at"] < _STATUS_TTL:
            return _cache["status"]
    status = _discover()
    with _lock:
        _cache.update(at=time.time(), status=status)
    return status


def _extract_json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except ValueError:
            return None
    return None


def _build_messages(theme, image_b64):
    anchors = {k: DEFAULT_RECIPES[theme][k] for k in ("brightness", "saturation", "warmth")}
    system = "You are a photo-booth art director. Answer with JSON only."
    user = (
        f"Theme: {theme}. {THEME_BRIEFS[theme]}\n"
        "For this photo give: caption (max 4 playful words about it), palette (exactly 3 hex colours, "
        "darkest to lightest), brightness and saturation (multipliers near 1.0), warmth (-0.6 cool to 0.6 warm). "
        f"Start from {json.dumps(anchors)} and change them only slightly."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user, "images": [image_b64]},
    ]


def request_recipe(image_b64, theme, budget=None):
    """
    Ask the vision model for a recipe, giving up after `budget` seconds.
    Returns (raw_dict_or_None, model_name_or_None, message). Never raises.
    """
    budget = LOOK_BUDGET if budget is None else budget
    if time.time() < _breaker["skip_until"]:
        return None, None, "Ollama was too slow recently, so it is being skipped for a few minutes"

    status = get_status()
    if not status["available"]:
        return None, None, status["reason"]

    model = status["model"]
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "format": RECIPE_SCHEMA,
        "options": {"temperature": 0.5, "num_predict": 110, "num_ctx": 2048},
        "messages": _build_messages(theme, image_b64),
    }
    url = f"{OLLAMA_HOST}/api/chat"
    started = time.time()
    try:
        res = requests.post(url, json=payload, timeout=(3, budget + 3))
        if res.status_code == 400:            # older Ollama may not accept a full schema
            payload["format"] = "json"
            res = requests.post(url, json=payload, timeout=(3, max(2, budget + 3 - (time.time() - started))))
        res.raise_for_status()
        content = (res.json().get("message") or {}).get("content", "")
    except requests.Timeout:
        record_failure()
        return None, model, f"{model} took longer than {int(budget)}s"
    except (requests.RequestException, ValueError) as exc:
        record_failure()
        get_status(force=True)                # model may have been removed; re-check next time
        return None, model, f"Ollama request failed: {exc}"

    recipe = _extract_json(content)
    if not isinstance(recipe, dict):
        return None, model, f"{model} didn't return usable JSON"
    took = time.time() - started
    print(f"[Ollama] {model} answered in {took:.1f}s")
    if took > budget:
        record_failure()                      # an answer that arrives after the deadline is no use: count it as slow
    else:
        record_success()
    return recipe, model, "ok"


def warm_up():
    """Load the model into memory in the background so the first photo isn't slow."""
    def _run():
        status = get_status(force=True)
        if not status["available"]:
            print(f"[Ollama] not ready: {status['reason']}")
            return
        print(f"[Ollama] using {status['model']} at {OLLAMA_HOST}; warming up...")
        try:
            requests.post(f"{OLLAMA_HOST}/api/generate",
                          json={"model": status["model"], "keep_alive": OLLAMA_KEEP_ALIVE},
                          timeout=(3, 180))
            print("[Ollama] model loaded")
        except requests.RequestException as exc:
            print(f"[Ollama] warm-up skipped: {exc}")
    threading.Thread(target=_run, daemon=True).start()
