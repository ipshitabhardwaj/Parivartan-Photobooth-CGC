"""
Exposure fix for webcam photos.

Webcams often expose for the bright wall behind you, which leaves the face too dark (or the opposite). The kiosk asks people
to put their face inside the outline, so we measure the brightness there and lift or lower the whole picture until skin sits
at a natural level, then add a little local contrast. It never changes a well-exposed photo much.
"""
import numpy as np
from PIL import Image, ImageEnhance

from recipes import FACE

try:
    import cv2
    HAVE_CV2 = True
except Exception:                       # missing, or built for a different NumPy (the check is in ai_generator's log line)
    HAVE_CV2 = False

TARGET = 0.50            # desired average brightness of the face (0..1)
BRIGHTEN_LIMIT = 0.40    # smallest exponent allowed: lifts a very dark face (brightness is raised to this power)
DARKEN_LIMIT = 2.50      # largest exponent allowed: tones down a washed-out face


def face_brightness(img):
    """Average perceived brightness (0..1) inside the face outline, ignoring pure black/white pixels."""
    arr = np.asarray(img.convert("RGB")).astype(np.float32) / 255.0
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    inside = (((xx / w - FACE["cx"]) / (FACE["rx"] * 0.75)) ** 2 + ((yy / h - FACE["cy"]) / (FACE["ry"] * 0.75)) ** 2) <= 1
    luma = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    region = luma[inside]
    region = region[(region > 0.03) & (region < 0.97)]
    return float(region.mean()) if region.size > 50 else None


def normalize_exposure(img, strength=1.0):
    """Return an exposure-corrected copy of `img` (PIL RGB). strength 0 = untouched, 1 = full correction."""
    mean = face_brightness(img)
    if mean is None or strength <= 0:
        return img
    exponent = np.log(TARGET) / np.log(max(mean, 0.02))            # < 1 brightens, > 1 darkens
    exponent = 1 + (float(np.clip(exponent, BRIGHTEN_LIMIT, DARKEN_LIMIT)) - 1) * strength
    if abs(exponent - 1) < 0.04:
        out = img.convert("RGB")
    else:
        table = (np.linspace(0, 1, 256) ** exponent * 255).astype(np.uint8)
        out = img.convert("RGB").point(list(table) * 3)
        if exponent < 0.85:                                         # brightening washes colour out: put some back
            out = ImageEnhance.Color(out).enhance(1 + min(0.5, (0.85 - exponent) * 0.9))
    if HAVE_CV2:                                                    # gentle local contrast on lightness only
        lab = cv2.cvtColor(np.asarray(out.convert("RGB")), cv2.COLOR_RGB2LAB)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(6, 6))
        boosted = lab.copy()
        boosted[..., 0] = clahe.apply(lab[..., 0])
        lab = cv2.addWeighted(lab, 1 - 0.55 * strength, boosted, 0.55 * strength, 0)
        out = Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))
    return out
