"""
Person cut-out, used for the Sci-Fi background swap.

Runs U^2-Net-lite (u2netp, Apache-2.0, ~4.6 MB, bundled in ./models) through onnxruntime on the CPU,
about 0.3 s per photo. Everything here is optional: if onnxruntime, OpenCV or the model file is missing,
or the result doesn't look like a person where the face outline is, `person_alpha` returns None and the
caller keeps the normal framed look.
"""
import os
import threading

import numpy as np
from PIL import Image

try:
    import cv2
    import onnxruntime as ort
    HAVE_LIBS = True
except ImportError:
    HAVE_LIBS = False

from recipes import FACE

MODEL_PATH = os.environ.get("SEG_MODEL", os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "u2netp.onnx"))
_session = None
_lock = threading.Lock()


def available():
    return HAVE_LIBS and os.path.exists(MODEL_PATH)


def _get_session():
    global _session
    with _lock:
        if _session is None:
            _session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
        return _session


def person_alpha(img):
    """Soft person mask (float32 HxW, 0..1) for an RGB PIL image, or None if unavailable/implausible."""
    if not available():
        return None
    try:
        session = _get_session()
        arr = np.asarray(img.resize((320, 320), Image.BILINEAR)).astype(np.float32)
        arr = arr / max(float(arr.max()), 1e-6)
        arr = (arr - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
        out = session.run(None, {session.get_inputs()[0].name: arr.transpose(2, 0, 1)[None].astype(np.float32)})[0][0, 0]
        out = (out - out.min()) / (out.max() - out.min() + 1e-8)
        mask = cv2.resize(out, img.size, interpolation=cv2.INTER_CUBIC).clip(0, 1)

        alpha = np.clip((mask - 0.35) / 0.3, 0, 1)                 # firm up the edge ...
        alpha = alpha * alpha * (3 - 2 * alpha)
        alpha = cv2.GaussianBlur(alpha, (0, 0), 1.2).astype(np.float32)   # ... then feather it a little

        # Sanity: a person should fill a sensible part of the picture and be where the face outline is.
        h, w = alpha.shape
        yy, xx = np.mgrid[0:h, 0:w]
        inside = (((xx / w - FACE["cx"]) / FACE["rx"]) ** 2 + ((yy / h - FACE["cy"]) / FACE["ry"]) ** 2) <= 1
        coverage = float((alpha > 0.5).mean())
        if not (0.06 <= coverage <= 0.85) or float(alpha[inside].mean()) < 0.6:
            print(f"[Segment] cut-out rejected (coverage {coverage:.0%}, face overlap {float(alpha[inside].mean()):.0%})")
            return None
        return alpha
    except Exception as exc:                                         # never let segmentation break a photo
        print(f"[Segment] failed: {exc}")
        return None


def cutout_with_rim(styled, alpha, left_rgb, right_rgb):
    """
    RGBA person cut-out with cinematic rim light: a bright edge on the person plus a soft halo outside,
    cyan on the left and warm on the right, like neon on one side and sunset on the other.
    """
    h, w = alpha.shape
    rgb = np.asarray(styled.convert("RGB")).astype(np.float32) / 255.0

    side = np.linspace(1.0, 0.0, w, dtype=np.float32)[None, :, None]          # 1 on the left -> 0 on the right
    colour = (np.array(left_rgb, np.float32) / 255.0)[None, None, :] * side + \
             (np.array(right_rgb, np.float32) / 255.0)[None, None, :] * (1 - side)

    k = max(3, w // 110)
    eroded = cv2.erode(alpha, np.ones((k, k), np.uint8))
    inner = cv2.GaussianBlur(np.clip(alpha - eroded, 0, 1), (0, 0), k * 0.45)[..., None]
    lit = 1 - (1 - rgb) * (1 - colour * np.clip(inner * 2.3, 0, 0.97))          # screen blend

    halo = cv2.GaussianBlur(alpha, (0, 0), w / 55)
    halo = np.clip((halo - alpha) * 1.9, 0, 0.9)[..., None]

    a = alpha[..., None]
    out_a = a + halo * (1 - a)
    out_rgb = (lit * a + colour * halo * (1 - a)) / np.maximum(out_a, 1e-6)
    rgba = np.dstack([out_rgb.clip(0, 1), out_a.clip(0, 1)])
    return Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")
