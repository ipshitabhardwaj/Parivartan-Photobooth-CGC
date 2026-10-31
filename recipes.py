"""
Look "recipes" shared by the Ollama bridge and the Pillow renderer.

A recipe is a small JSON object describing a photo look (colour grade, smoothing, glow,
palette, which SVG stickers to draw). Ollama's vision model proposes one for each photo;
`sanitize_recipe` validates it and pulls it toward the theme's defaults so a weak or odd
model answer can never break the look.

Identity of each theme is NOT up to the model: the frame, the caption style, the face guide
and the must-have stickers (cat ears etc.) are fixed per theme. The model only tunes numbers,
palette, caption and which optional extras to add.

KEEP IN SYNC: svgfx.js has a copy of DEFAULT_RECIPES (and FACE) so the browser can still
style a photo when the server is unreachable. `python check_sync.py` verifies this.
"""
import re

THEMES = ("Sci-Fi", "Anime", "Cats", "Vintage")

STICKERS = (
    "scanlines", "hud", "grid", "glitch", "stars",          # sci-fi
    "rays", "sparkles", "halftone", "petals",                # anime
    "kittens", "chalk", "ears", "nose", "whiskers", "blush", "paws", "hearts",   # cats (kittens/ears/nose sit on the face)
    "filmlines", "lightleak", "dust", "datestamp",           # vintage
    "confetti",                                              # any
)
FRAMES = ("none", "cyber", "neon", "bubble", "polaroid", "film")

# Where the face should be, as fractions of the square capture. Used for the live outline in
# the browser and to anchor ears/nose/whiskers. Must match FACE in svgfx.js.
FACE = {"cx": 0.5, "cy": 0.52, "rx": 0.2, "ry": 0.27}

# Optional extras the model may add on top of a theme's defaults (keeps every look on-theme).
STICKER_POOL = {
    "Sci-Fi": ("scanlines", "hud", "stars"),
    "Anime": ("sparkles", "petals", "stars", "hearts"),
    "Cats": ("kittens", "chalk", "hearts", "paws", "sparkles"),
    "Vintage": ("filmlines", "dust", "lightleak", "datestamp"),
}
# Always drawn for the theme, whatever the model says.
REQUIRED_STICKERS = {
    "Sci-Fi": (),
    "Anime": (),
    "Cats": ("kittens", "chalk"),
    "Vintage": ("filmlines",),
}

# name: (min, max). Model values are clamped into these ranges.
NUMERIC_LIMITS = {
    "brightness":    (0.80, 1.30),
    "contrast":      (0.80, 1.50),
    "saturation":    (0.10, 1.80),
    "hue_shift":     (-20.0, 20.0),   # degrees
    "warmth":        (-0.6, 0.6),
    "tint":          (0.0, 0.92),     # strength of the palette gradient map
    "edge_strength": (0.0, 0.6),
    "grain":         (0.0, 0.8),
    "vignette":      (0.0, 0.85),
    "blur":          (0.0, 2.0),      # px at 768px
    "sharpen":       (0.70, 1.80),
    "smooth":        (0.0, 1.0),      # edge-preserving skin/paint smoothing
    "bloom":         (0.0, 0.7),      # soft glow
    "flatten":       (0.0, 1.0),      # cel-shading: merge colours into flat patches
}

DEFAULT_RECIPES = {
    # Cyberpunk lab: when a person cut-out is available the browser swaps the background for a neon scene
    # (see svgfx.js, `scene`). Without one it falls back to this framed look with a natural cool grade.
    "Sci-Fi": {
        "caption": "Future Rewind", "palette": ["#0b1030", "#7a2cff", "#27e6ff"],
        "brightness": 1.03, "contrast": 1.15, "saturation": 1.2, "hue_shift": 0.0,
        "warmth": -0.1, "tint": 0.12, "posterize_bits": 8,
        "edge_strength": 0.0, "edge_mode": "glow",
        "grain": 0.05, "vignette": 0.25, "blur": 0.0, "sharpen": 1.1, "smooth": 0.15, "bloom": 0.25, "flatten": 0.0,
        "stickers": ["hud", "scanlines"], "frame": "cyber", "caption_style": "plate", "guide": "oval",
    },
    # Whole-picture illustration: flat cel-style shading, clean contours. Nothing added on top.
    "Anime": {
        "caption": "Main Character", "palette": ["#2b1b4f", "#ff7eb3", "#fff0b3"],
        "brightness": 1.05, "contrast": 1.12, "saturation": 1.45, "hue_shift": 0.0,
        "warmth": 0.1, "tint": 0.08, "posterize_bits": 8,
        "edge_strength": 0.35, "edge_mode": "ink",
        "grain": 0.0, "vignette": 0.0, "blur": 0.0, "sharpen": 1.8, "smooth": 0.5, "bloom": 0.3, "flatten": 0.3,
        "stickers": [], "frame": "none", "caption_style": "none", "guide": "oval",
    },
    # Warm illustration with kittens on your head and shoulders and chalk doodles around you.
    "Cats": {
        "caption": "Purr-fect", "palette": ["#5a2d0c", "#ffb547", "#fff1d6"],
        "brightness": 1.05, "contrast": 1.08, "saturation": 1.3, "hue_shift": 0.0,
        "warmth": 0.3, "tint": 0.05, "posterize_bits": 8,
        "edge_strength": 0.3, "edge_mode": "ink",
        "grain": 0.02, "vignette": 0.05, "blur": 0.0, "sharpen": 1.4, "smooth": 0.7, "bloom": 0.35, "flatten": 0.2,
        "stickers": ["kittens", "chalk"], "frame": "none", "caption_style": "none", "guide": "kittens",
    },
    # Monochrome sepia photobooth: heavy grain, dark vignette, soft focus, film streaks.
    "Vintage": {
        "caption": "Summer '78", "palette": ["#14100c", "#74675a", "#e8dfd0"],
        "brightness": 1.0, "contrast": 1.2, "saturation": 0.15, "hue_shift": 0.0,
        "warmth": 0.2, "tint": 0.85, "posterize_bits": 8,
        "edge_strength": 0.0, "edge_mode": "glow",
        "grain": 0.4, "vignette": 0.75, "blur": 0.9, "sharpen": 0.9, "smooth": 0.0, "bloom": 0.25, "flatten": 0.0,
        "stickers": ["filmlines", "dust"], "frame": "none", "caption_style": "script", "guide": "oval",
    },
}

# What each theme means, in words the vision model can act on.
THEME_BRIEFS = {
    "Sci-Fi": "Cyberpunk lab: keep the person natural and flattering with a cool neon grade (navy shadows, "
              "violet and cyan highlights). Palette: deep navy, violet, bright cyan.",
    "Anime": "Anime illustration: clean flat shading, vivid but not blown out, soft glow. "
             "Palette: dark plum, hot pink, cream yellow.",
    "Cats": "Cosy cat-lover illustration: warm golden light, soft shading, sweet mood. "
            "Palette: chocolate brown, amber, cream.",
    "Vintage": "Old monochrome photobooth strip: sepia black-and-white, heavy film grain, dark vignette, "
               "slightly soft focus. Palette: near-black brown, tan, parchment.",
}

MODEL_WEIGHT = 0.6      # how much of the model's number survives vs the theme default
PALETTE_WEIGHT = 0.5    # how much of the model's colours survive vs the theme's own palette
MODEL_KEYS = ("brightness", "saturation", "warmth")   # the only numbers the model may touch

_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _luma(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _darken(hex_color, amount):
    chans = [int(int(hex_color[i:i + 2], 16) * (1 - amount)) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(chans)


def _mix(a, b, weight):
    """Blend hex colour a (weight) with b (1 - weight)."""
    chans = [round(weight * int(a[i:i + 2], 16) + (1 - weight) * int(b[i:i + 2], 16)) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(chans)


def _clean_hex(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not _HEX.match(value):
        return None
    return "#" + value.lstrip("#").lower()


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _clean_caption(value, fallback):
    if not isinstance(value, str):
        return fallback
    text = re.sub(r"[^\w\s'!&.,\-]", "", value, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()[:28].strip()
    return text or fallback


def default_recipe(theme):
    base = DEFAULT_RECIPES.get(theme, DEFAULT_RECIPES["Sci-Fi"])
    return {**base, "palette": list(base["palette"]), "stickers": list(base["stickers"])}


def sanitize_recipe(raw, theme):
    """Turn whatever the model said into a safe, complete recipe."""
    if theme not in DEFAULT_RECIPES:
        theme = "Sci-Fi"
    recipe = default_recipe(theme)
    if not isinstance(raw, dict):
        return recipe

    for key in MODEL_KEYS:                       # everything else (tint, smoothing, lines...) is fixed per theme
        low, high = NUMERIC_LIMITS[key]
        value = _number(raw.get(key))
        if value is None:
            continue
        value = min(high, max(low, value))
        recipe[key] = round(MODEL_WEIGHT * value + (1 - MODEL_WEIGHT) * recipe[key], 3)

    palette = [c for c in (_clean_hex(c) for c in (raw.get("palette") or [])[:6]) if c]
    if len(palette) >= 3:
        palette = sorted(palette[:3], key=_luma)  # shadow -> highlight
        if _luma(palette[0]) > 0.30:              # captions/frames sit on palette[0]; keep it dark
            palette[0] = _darken(palette[0], 0.6)
        base = recipe["palette"]                 # blend with the theme's palette so a wild answer can't recolour the look
        recipe["palette"] = [_mix(m, b, PALETTE_WEIGHT) for m, b in zip(palette, base)]

    recipe["caption"] = _clean_caption(raw.get("caption"), recipe["caption"])

    # Stickers: required ones first (theme identity), then the model's picks that fit the theme,
    # then top up from the theme defaults.
    stickers = list(REQUIRED_STICKERS[theme])
    pool = STICKER_POOL[theme]
    for name in raw.get("stickers") or []:
        if isinstance(name, str) and name in pool and name not in stickers:
            stickers.append(name)
    for name in recipe["stickers"]:
        if len(stickers) >= 4:
            break
        if name not in stickers:
            stickers.append(name)
    recipe["stickers"] = stickers[:6]

    # frame, caption_style and guide stay at the theme's values on purpose.
    return recipe
