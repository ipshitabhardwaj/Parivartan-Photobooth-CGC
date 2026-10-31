/*
 * SVG effects layer for CGC SQUARE.
 *
 * Everything the finished picture is made of is built as ONE svg string:
 *   photo  ->  (optional) SVG colour filter  ->  stickers  ->  frame  ->  caption
 * The page shows that string as an <img>, and "Save" rasterises the very same
 * string to PNG, so what you see is exactly what you download.
 *
 * Two jobs:
 *   1. Stickers, frame and caption are always drawn here (they sit on top of
 *      the photo the server styled with Ollama + Pillow).
 *   2. If the server or Ollama can't be reached, `applyFilter: true` makes the
 *      same look happen with SVG filters (feColorMatrix etc.) in the browser.
 *
 * DEFAULT_RECIPES must stay in sync with recipes.py.
 */
'use strict';

const DEFAULT_RECIPES = {
  "Sci-Fi": {
    "caption": "Future Rewind",
    "palette": [
      "#0b1030",
      "#7a2cff",
      "#27e6ff"
    ],
    "brightness": 1.03,
    "contrast": 1.15,
    "saturation": 1.2,
    "hue_shift": 0.0,
    "warmth": -0.1,
    "tint": 0.12,
    "posterize_bits": 8,
    "edge_strength": 0.0,
    "edge_mode": "glow",
    "grain": 0.05,
    "vignette": 0.25,
    "blur": 0.0,
    "sharpen": 1.1,
    "smooth": 0.15,
    "bloom": 0.25,
    "flatten": 0.0,
    "stickers": [
      "hud",
      "scanlines"
    ],
    "frame": "cyber",
    "caption_style": "plate",
    "guide": "oval"
  },
  "Anime": {
    "caption": "Main Character",
    "palette": [
      "#2b1b4f",
      "#ff7eb3",
      "#fff0b3"
    ],
    "brightness": 1.05,
    "contrast": 1.12,
    "saturation": 1.45,
    "hue_shift": 0.0,
    "warmth": 0.1,
    "tint": 0.08,
    "posterize_bits": 8,
    "edge_strength": 0.35,
    "edge_mode": "ink",
    "grain": 0.0,
    "vignette": 0.0,
    "blur": 0.0,
    "sharpen": 1.8,
    "smooth": 0.5,
    "bloom": 0.3,
    "flatten": 0.3,
    "stickers": [],
    "frame": "none",
    "caption_style": "none",
    "guide": "oval"
  },
  "Cats": {
    "caption": "Purr-fect",
    "palette": [
      "#5a2d0c",
      "#ffb547",
      "#fff1d6"
    ],
    "brightness": 1.05,
    "contrast": 1.08,
    "saturation": 1.3,
    "hue_shift": 0.0,
    "warmth": 0.3,
    "tint": 0.05,
    "posterize_bits": 8,
    "edge_strength": 0.3,
    "edge_mode": "ink",
    "grain": 0.02,
    "vignette": 0.05,
    "blur": 0.0,
    "sharpen": 1.4,
    "smooth": 0.7,
    "bloom": 0.35,
    "flatten": 0.2,
    "stickers": [
      "kittens",
      "chalk"
    ],
    "frame": "none",
    "caption_style": "none",
    "guide": "kittens"
  },
  "Vintage": {
    "caption": "Summer '78",
    "palette": [
      "#14100c",
      "#74675a",
      "#e8dfd0"
    ],
    "brightness": 1.0,
    "contrast": 1.2,
    "saturation": 0.15,
    "hue_shift": 0.0,
    "warmth": 0.2,
    "tint": 0.85,
    "posterize_bits": 8,
    "edge_strength": 0.0,
    "edge_mode": "glow",
    "grain": 0.4,
    "vignette": 0.75,
    "blur": 0.9,
    "sharpen": 0.9,
    "smooth": 0.0,
    "bloom": 0.25,
    "flatten": 0.0,
    "stickers": [
      "filmlines",
      "dust"
    ],
    "frame": "none",
    "caption_style": "script",
    "guide": "oval"
  }
};

/* Where the face goes, as fractions of the square capture. Must match FACE in recipes.py. */
const FACE = {"cx": 0.5, "cy": 0.52, "rx": 0.2, "ry": 0.27};

/** Face ellipse in the local coordinates of a W x H photo area (the square capture is cropped to fill it). */
function faceBox(W, H) {
  const s = Math.max(W, H);
  return { cx: (W - s) / 2 + FACE.cx * s, cy: (H - s) / 2 + FACE.cy * s, rx: FACE.rx * s, ry: FACE.ry * s, s };
}

/* Cat ear in unit coordinates (base at y=0, tip at about y=-1.2); the same shape is used for the
   live outline and the finished sticker so they always line up. */
const EAR_D = 'M-0.58 0.18C-0.66 -0.46 -0.34 -0.98 0.02 -1.22C0.40 -0.92 0.66 -0.40 0.60 0.18Z';
function earPlacements(face) {
  const size = face.rx * 0.75;
  return [-1, 1].map((side) => ({
    x: face.cx + side * face.rx * 0.53, y: face.cy - face.ry * 0.85, rot: side * 24, size,
  }));
}

/** Markup for the live camera outline (viewBox 0 0 100 100). kind: 'oval' | 'kittens' */
function guideMarkup(kind) {
  const f = faceBox(100, 100);
  const oval = `M${f.cx - f.rx} ${f.cy}a${f.rx} ${f.ry} 0 1 0 ${2 * f.rx} 0a${f.rx} ${f.ry} 0 1 0 ${-2 * f.rx} 0Z`;
  let extras = '';
  if (kind === 'kittens') {                               // dashed spots where the kittens will sit
    extras = kittenSpots(f).map((s) =>
      `<ellipse cx="${f2(s.x)}" cy="${f2(s.y)}" rx="${f2(46 * s.k)}" ry="${f2(37 * s.k)}" transform="rotate(${s.rot} ${f2(s.x)} ${f2(s.y)})" vector-effect="non-scaling-stroke"/>`).join('');
  }
  const lines = `<ellipse cx="${f.cx}" cy="${f.cy}" rx="${f.rx}" ry="${f.ry}" vector-effect="non-scaling-stroke"/>${extras}`;
  return `<path d="M0 0H100V100H0Z${oval}" fill="rgba(20,12,30,0.32)" fill-rule="evenodd"/>` +
    `<g fill="none" stroke="rgba(0,0,0,0.45)" stroke-width="7" stroke-linejoin="round">${lines}</g>` +
    `<g fill="none" stroke="#fff" stroke-width="3.5" stroke-linejoin="round" stroke-dasharray="9 7" stroke-linecap="round">${lines}</g>`;
}

const FONT_DISPLAY = "'Bagel Fat One','Nunito','Trebuchet MS','Segoe UI',system-ui,sans-serif";
const FONT_HAND = "'Segoe Script','Bradley Hand','Marker Felt','Comic Sans MS',cursive";
const FONT_MONO = "'Consolas','Courier New',monospace";

/* ---------- small helpers ---------- */
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const hexToRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const rgb01 = (h) => hexToRgb(h).map((v) => (v / 255).toFixed(4));
const darken = (h, k) => '#' + hexToRgb(h).map((v) => Math.round(v * (1 - k)).toString(16).padStart(2, '0')).join('');
const lighten = (h, t) => '#' + hexToRgb(h).map((v) => Math.round(v + (255 - v) * t).toString(16).padStart(2, '0')).join('');
const f2 = (n) => Number(n).toFixed(2);

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Four-point sparkle centred on x,y. */
const spark = (x, y, r, fill, op = 1) =>
  `<path d="M${f2(x)} ${f2(y - r)}Q${f2(x)} ${f2(y)} ${f2(x + r)} ${f2(y)}Q${f2(x)} ${f2(y)} ${f2(x)} ${f2(y + r)}` +
  `Q${f2(x)} ${f2(y)} ${f2(x - r)} ${f2(y)}Q${f2(x)} ${f2(y)} ${f2(x)} ${f2(y - r)}Z" fill="${fill}" opacity="${op}"/>`;

/** Random point that avoids the middle of the picture (where the face is). */
function edgePoint(W, H, rnd) {
  for (let i = 0; i < 12; i++) {
    const x = rnd() * W, y = rnd() * H;
    if (!(x > W * 0.28 && x < W * 0.72 && y > H * 0.22 && y < H * 0.80)) return [x, y];
  }
  return [rnd() < 0.5 ? W * 0.08 : W * 0.92, rnd() * H];
}

/* ---------- kittens + chalk doodles (Cats look) ---------- */
const KITTEN_COATS = {
  gray:   { fur: '#9aa0a9', stripe: '#656b75', muzzle: '#f4f2ef', eyes: 'happy', ink: '#4a2f22' },
  orange: { fur: '#f3a652', stripe: '#d17f2e', muzzle: '#fff3e0', eyes: 'happy', ink: '#5a3418' },
  pale:   { fur: '#c9ccd2', stripe: '#8d929b', muzzle: '#ffffff', eyes: 'round', ink: '#4a2f22' },
  tux:    { fur: '#2d2622', stripe: null,      muzzle: '#ffffff', eyes: 'round', ink: '#120d0b' },
};

/** One cute illustrated kitten in a ~100-unit box centred on its head. pose: 'lying' (draped) or 'sitting'. */
function kittenSvg(coatName, pose) {
  const c = KITTEN_COATS[coatName], ink = c.ink, sw = 2.6;
  let body = '', front = '';
  if (pose === 'lying') {
    body = `<path d="M44 20Q80 12 72 -20" fill="none" stroke="${ink}" stroke-width="15" stroke-linecap="round"/>` +
      `<path d="M44 20Q80 12 72 -20" fill="none" stroke="${c.fur}" stroke-width="10" stroke-linecap="round"/>` +
      `<path d="M66 6l8 -2M69 -6l8 -2M71 -17l7 -1" stroke="${c.stripe || ink}" stroke-width="2.4" stroke-linecap="round"/>` +
      `<ellipse cx="4" cy="26" rx="48" ry="20" fill="${c.fur}" stroke="${ink}" stroke-width="${sw}"/>`;
    front = [-19, 19].map((x) => `<ellipse cx="${x}" cy="37" rx="13" ry="9" fill="${c.fur}" stroke="${ink}" stroke-width="${sw}"/>` +
      `<path d="M${x - 4} 39v5M${x + 4} 39v5" stroke="${ink}" stroke-width="1.8" stroke-linecap="round"/>`).join('');
  } else {
    body = `<path d="M-34 24Q-48 74 -8 80H28Q58 74 42 24Z" fill="${c.fur}" stroke="${ink}" stroke-width="${sw}"/>` +
      `<ellipse cx="2" cy="58" rx="15" ry="17" fill="${c.muzzle}" opacity=".95"/>`;
    front = `<ellipse cx="38" cy="38" rx="12" ry="9" transform="rotate(-25 38 38)" fill="${c.fur}" stroke="${ink}" stroke-width="${sw}"/>` +
      `<path d="M33 40v5M41 36v5" stroke="${ink}" stroke-width="1.8" stroke-linecap="round"/>`;
  }
  const ears = [-1, 1].map((s) =>
    `<path d="M${s * 36} -16L${s * 41} -47L${s * 14} -31Z" fill="${c.fur}" stroke="${ink}" stroke-width="${sw}" stroke-linejoin="round"/>` +
    `<path d="M${s * 33} -22L${s * 36} -39L${s * 20} -30Z" fill="#ffb3c7"/>`).join('');
  const stripes = c.stripe
    ? `<path d="M-9 -32q1 8 -1 13M0 -34v14M9 -32q-1 8 1 13" fill="none" stroke="${c.stripe}" stroke-width="3" stroke-linecap="round"/>` : '';
  const eyes = c.eyes === 'happy'
    ? `<path d="M-24 -3q8 -9 16 0M8 -3q8 -9 16 0" fill="none" stroke="${ink}" stroke-width="2.8" stroke-linecap="round"/>`
    : [-16, 16].map((x) => `<ellipse cx="${x}" cy="-3" rx="8" ry="9" fill="${coatName === 'tux' ? '#c9a227' : '#7b6a3a'}"/>` +
        `<ellipse cx="${x}" cy="-3" rx="5" ry="7" fill="#1a120c"/><circle cx="${x - 2}" cy="-6" r="2.4" fill="#fff"/><circle cx="${x + 2.5}" cy="0" r="1.2" fill="#fff"/>`).join('');
  const whiskers = [-1, 1].map((s) => `<path d="M${s * 27} 10L${s * 56} 5M${s * 27} 14L${s * 58} 16M${s * 27} 18L${s * 54} 26" stroke="#fff" stroke-opacity=".85" stroke-width="1.3" stroke-linecap="round"/>`).join('');
  const ticks = [-125, -90, -55].map((a) => {
    const r = a * Math.PI / 180;
    return `<path d="M${f2(Math.cos(r) * 60)} ${f2(Math.sin(r) * 52 - 4)}L${f2(Math.cos(r) * 72)} ${f2(Math.sin(r) * 62 - 4)}" stroke="#ffe9a8" stroke-width="3.6" stroke-linecap="round"/>`;
  }).join('');
  return `<g>${ticks}${body}${ears}` +
    `<ellipse cx="0" cy="0" rx="43" ry="35" fill="${c.fur}" stroke="${ink}" stroke-width="${sw}"/>` +
    `${stripes}<ellipse cx="0" cy="12" rx="19" ry="14" fill="${c.muzzle}"/>${eyes}` +
    `<path d="M-3.6 5H3.6L0 10Z" fill="#ff8fb0" stroke="#c75a7e" stroke-width="1" stroke-linejoin="round"/>` +
    `<path d="M0 10v3.5M0 13.5q-5 5 -9 1M0 13.5q5 5 9 1" fill="none" stroke="#6a3f30" stroke-width="1.7" stroke-linecap="round"/>` +
    `<ellipse cx="-27" cy="10" rx="7" ry="4.5" fill="#ff8aa8" opacity=".42"/><ellipse cx="27" cy="10" rx="7" ry="4.5" fill="#ff8aa8" opacity=".42"/>` +
    `${whiskers}${front}</g>`;
}

/** Where the kittens sit, from the face outline: one on the head, one on each shoulder. */
function kittenSpots(f) {
  return [
    { coat: 'gray',   pose: 'lying',   x: f.cx + f.rx * 0.22, y: f.cy - f.ry * 0.95 - f.rx * 0.3, k: f.rx * 1.45 / 100, rot: 4 },
    { coat: 'pale',   pose: 'sitting', x: f.cx - f.rx * 1.55, y: f.cy + f.ry * 0.62,              k: f.rx * 1.7 / 100,  rot: -6 },
    { coat: 'orange', pose: 'lying',   x: f.cx + f.rx * 1.55, y: f.cy + f.ry * 0.78,              k: f.rx * 1.7 / 100,  rot: 5 },
  ];
}

const CHALK = {
  face: '<path d="M-30-8L-34-34-12-22Q0-26 12-22L34-34 30-8Q38 10 20 24Q0 34-20 24Q-38 10-30-8Z"/>' +
        '<path d="M-18-2q6-6 12 0M6-2q6-6 12 0M0 8l-3-3h6zM0 8q-4 6-9 3M0 8q4 6 9 3M-26 4l-12-3M-26 8l-12 4M26 4l12-3M26 8l12 4"/>',
  heart: '<path d="M0 14C-26-4-14-26 0-12 14-26 26-4 0 14Z" stroke="#ff6b8a" stroke-width="4"/>',
  bubble: '<path d="M-26-18H26a8 8 0 0 1 8 8V12a8 8 0 0 1-8 8H-6L-18 32V20H-26a8 8 0 0 1-8-8V-10a8 8 0 0 1 8-8Z"/>' +
          '<path d="M0 8C-10 0-6-9 0-4 6-9 10 0 0 8Z" stroke="#ff6b8a" stroke-width="2.6"/>',
  paw: '<ellipse cy="9" rx="12" ry="10" fill="#fff" stroke="none"/><ellipse cx="-15" cy="-5" rx="4.6" ry="6" transform="rotate(-20 -15 -5)" fill="#fff" stroke="none"/>' +
       '<ellipse cx="-5" cy="-14" rx="4.6" ry="6" fill="#fff" stroke="none"/><ellipse cx="5" cy="-14" rx="4.6" ry="6" fill="#fff" stroke="none"/>' +
       '<ellipse cx="15" cy="-5" rx="4.6" ry="6" transform="rotate(20 15 -5)" fill="#fff" stroke="none"/>',
};

/* ---------- sticker library (each returns an SVG fragment in photo-local coordinates) ---------- */
const STICKERS = {
  kittens({ face }) {
    return kittenSpots(face).map((s) =>
      `<g transform="translate(${f2(s.x)} ${f2(s.y)}) rotate(${s.rot}) scale(${f2(s.k)})">${kittenSvg(s.coat, s.pose)}</g>`).join('');
  },

  chalk({ W, H }) {
    const k = Math.max(W, H) / 1024;
    const put = (name, fx, fy, size, rot, op = 0.92) =>
      `<g transform="translate(${f2(W * fx)} ${f2(H * fy)}) rotate(${rot}) scale(${f2(size * k)})" opacity="${op}">${CHALK[name]}</g>`;
    return `<g fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">` +
      put('face', 0.14, 0.13, 1.45, -6) + put('face', 0.87, 0.46, 1.3, 7) + put('paw', 0.09, 0.3, 1.0, -14) +
      put('paw', 0.13, 0.43, 0.9, 12) + put('paw', 0.91, 0.66, 0.9, 16) + put('paw', 0.89, 0.27, 0.8, -10) +
      put('heart', 0.17, 0.55, 0.75, -12) + put('bubble', 0.82, 0.14, 1.0, 5) + put('heart', 0.92, 0.84, 0.6, 14) + `</g>`;
  },

  scanlines({ W, H, pal, id }) {
    return `<defs><pattern id="${id}" width="${W}" height="7" patternUnits="userSpaceOnUse"><rect width="${W}" height="2" fill="${pal[2]}" opacity=".07"/></pattern></defs>` +
      `<rect width="${W}" height="${H}" fill="url(#${id})"/>`;
  },

  hud({ W, H, pal }) {
    const c = pal[2], m = 30, L = Math.round(Math.min(W, H) * 0.07);
    const tick = (x, y, sx, sy) => `<path d="M${x} ${y + sy * L}V${y}H${x + sx * L}" fill="none" stroke="${c}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`;
    return `<g opacity=".8">${tick(m, m, 1, 1)}${tick(W - m, m, -1, 1)}${tick(m, H - m, 1, -1)}${tick(W - m, H - m, -1, -1)}</g>` +
      `<circle cx="${m + 8}" cy="${m + L + 26}" r="6" fill="#ff3b6b"/>` +
      `<text x="${m + 24}" y="${m + L + 33}" fill="${c}" font-family="${FONT_MONO}" font-size="22" font-weight="700" letter-spacing="2" opacity=".9">LIVE</text>`;
  },

  grid({ W, H, pal }) {
    const y0 = H * 0.74;
    let s = '';
    for (let i = -9; i <= 9; i++) s += `<line x1="${W / 2}" y1="${y0}" x2="${f2(W / 2 + (i * W) / 5)}" y2="${H}"/>`;
    for (let k = 1; k <= 7; k++) { const y = y0 + (H - y0) * Math.pow(k / 7, 1.8); s += `<line x1="0" y1="${f2(y)}" x2="${W}" y2="${f2(y)}"/>`; }
    return `<g stroke="${pal[2]}" stroke-width="2" opacity=".4">${s}</g>`;
  },

  glitch({ W, H, pal, rnd }) {
    const cols = [pal[2], pal[1], '#ff2d75'];
    let s = '';
    for (let i = 0; i < 5; i++) {
      s += `<rect x="${f2(rnd() * W * 0.5)}" y="${f2(rnd() * H)}" width="${f2(W * (0.2 + rnd() * 0.5))}" height="${f2(6 + rnd() * 22)}" fill="${cols[i % 3]}" opacity="${f2(0.18 + rnd() * 0.25)}"/>`;
    }
    return s;
  },

  stars({ W, H, pal, rnd }) {
    let s = '';
    for (let i = 0; i < 16; i++) s += spark(rnd() * W, rnd() * H * 0.9, 5 + rnd() * 13, i % 2 ? pal[2] : '#fff', 0.55 + rnd() * 0.4);
    return s;
  },

  sparkles({ W, H, pal, rnd }) {
    let s = '';
    for (let i = 0; i < 9; i++) {
      const [x, y] = edgePoint(W, H, rnd);
      s += spark(x, y, 16 + rnd() * 30, '#fff', 0.95) + spark(x + 6, y + 6, 7 + rnd() * 8, pal[1], 0.9);
    }
    return s;
  },

  rays({ W, H, id }) {
    const cx = W / 2, cy = H * 0.46, n = 44, R = Math.hypot(W, H);
    let s = '';
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2, w = ((Math.PI * 2) / n) * 0.34 * (0.5 + ((i * 7) % 5) / 5);
      s += `<path d="M${cx} ${cy}L${f2(cx + Math.cos(a - w) * R)} ${f2(cy + Math.sin(a - w) * R)}L${f2(cx + Math.cos(a + w) * R)} ${f2(cy + Math.sin(a + w) * R)}Z"/>`;
    }
    return `<defs><radialGradient id="${id}g" cx="50%" cy="46%" r="75%"><stop offset=".42" stop-color="#000"/><stop offset="1" stop-color="#fff"/></radialGradient>` +
      `<mask id="${id}m" maskUnits="userSpaceOnUse" x="0" y="0" width="${W}" height="${H}"><rect width="${W}" height="${H}" fill="url(#${id}g)"/></mask></defs>` +
      `<g mask="url(#${id}m)" fill="#fff" opacity=".5">${s}</g>`;
  },

  halftone({ W, H, pal, id }) {
    return `<defs><pattern id="${id}p" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="8" cy="8" r="3.4" fill="${pal[1]}"/></pattern>` +
      `<linearGradient id="${id}g" x1="0" y1="1" x2="0.7" y2="0.3"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#000"/></linearGradient>` +
      `<mask id="${id}m" maskUnits="userSpaceOnUse" x="0" y="0" width="${W}" height="${H}"><rect width="${W}" height="${H}" fill="url(#${id}g)"/></mask></defs>` +
      `<rect width="${W}" height="${H}" fill="url(#${id}p)" mask="url(#${id}m)" opacity=".55"/>`;
  },

  petals({ W, H, rnd }) {
    const cols = ['#ffc6dc', '#ffe0ec', '#ffadc9'];
    let s = '';
    for (let i = 0; i < 13; i++) {
      const [x, y] = edgePoint(W, H, rnd), a = rnd() * 360, k = (0.7 + rnd() * 0.9) * (W / 1024) * 1.4;
      s += `<path transform="translate(${f2(x)} ${f2(y)}) rotate(${f2(a)}) scale(${f2(k)})" d="M0 0C6-14 24-12 26 0C24 12 6 14 0 0Z" fill="${cols[i % 3]}" opacity=".9"/>`;
    }
    return s;
  },

  ears({ face, pal }) {
    // fluffy cat ears planted on the head outline: same shape and spots as the live camera guide
    const fill = lighten(pal[1], 0.3);
    return earPlacements(face).map((e) => {
      const stroke = 9 / e.size;
      return `<g transform="translate(${f2(e.x)} ${f2(e.y)}) rotate(${e.rot}) scale(${f2(e.size)})">` +
        `<path d="${EAR_D}" fill="${fill}" stroke="#fff" stroke-width="${f2(stroke)}" stroke-linejoin="round"/>` +
        `<path d="${EAR_D}" transform="translate(0.02 0.02) scale(0.56)" fill="#ffb3c7" stroke="#ff93b0" stroke-width="${f2(2.5 / (e.size * 0.56))}" stroke-linejoin="round"/></g>`;
    }).join('');
  },

  whiskers({ face }) {
    const y = face.cy + face.ry * 0.36;
    let s = '';
    for (const side of [-1, 1]) {
      const x0 = face.cx + side * face.rx * 0.5, x1 = face.cx + side * face.rx * 1.6;
      for (const k of [-1, 0, 1]) {
        const y0 = y + k * face.ry * 0.045, y1 = y + k * face.ry * 0.19 - face.ry * 0.03;
        s += `<path d="M${f2(x0)} ${f2(y0)}Q${f2((x0 + x1) / 2)} ${f2(y0 - face.ry * 0.05)} ${f2(x1)} ${f2(y1)}"/>`;
      }
    }
    return `<g fill="none" stroke-linecap="round"><g stroke="#2b1b14" stroke-width="8" opacity=".22">${s}</g><g stroke="#fff" stroke-width="4.5" opacity=".95">${s}</g></g>`;
  },

  nose({ face }) {
    const k = face.rx * 0.13, x = face.cx, y = face.cy + face.ry * 0.3;
    return `<path transform="translate(${f2(x)} ${f2(y)}) scale(${f2(k)})" d="M-1 -0.5Q0 -1 1 -0.5Q1.1 0.1 0 0.9Q-1.1 0.1 -1 -0.5Z" fill="#ff8fb0" stroke="#d65a82" stroke-width="${f2(2.5 / k)}" stroke-linejoin="round"/>` +
      `<ellipse cx="${f2(x - k * 0.3)}" cy="${f2(y - k * 0.35)}" rx="${f2(k * 0.28)}" ry="${f2(k * 0.16)}" fill="#fff" opacity=".7"/>`;
  },

  blush({ face, id }) {
    const rx = face.rx * 0.34, ry = rx * 0.6, y = face.cy + face.ry * 0.34;
    return `<defs><radialGradient id="${id}g"><stop offset="0" stop-color="#ff5c8a" stop-opacity=".5"/><stop offset="1" stop-color="#ff5c8a" stop-opacity="0"/></radialGradient></defs>` +
      [-1, 1].map((side) => `<ellipse cx="${f2(face.cx + side * face.rx * 0.6)}" cy="${f2(y)}" rx="${f2(rx)}" ry="${f2(ry)}" fill="url(#${id}g)"/>`).join('');
  },

  paws({ W, H }) {
    const spots = [[0.09, 0.9, -15], [0.17, 0.78, 12], [0.91, 0.9, 15], [0.83, 0.78, -12]];
    const k = (Math.max(W, H) / 1024) * 1.1;
    return spots.map(([px, py, a]) =>
      `<g transform="translate(${f2(W * px)} ${f2(H * py)}) rotate(${a}) scale(${f2(k)})" fill="#fff" stroke="#5a2d0c" stroke-opacity=".3" stroke-width="3" opacity=".88">` +
      `<ellipse cx="0" cy="10" rx="22" ry="18"/><ellipse cx="-27" cy="-8" rx="8" ry="11" transform="rotate(-20 -27 -8)"/>` +
      `<ellipse cx="-9" cy="-25" rx="8" ry="11"/><ellipse cx="9" cy="-25" rx="8" ry="11"/>` +
      `<ellipse cx="27" cy="-8" rx="8" ry="11" transform="rotate(20 27 -8)"/></g>`).join('');
  },

  hearts({ W, H, rnd }) {
    const cols = ['#ff6b9a', '#ffb3c7', '#ffffff'];
    let s = '';
    for (let i = 0; i < 7; i++) {
      const [x, y] = edgePoint(W, H, rnd), k = (0.7 + rnd() * 0.9) * (W / 1024) * 1.7, a = (rnd() - 0.5) * 50;
      s += `<path transform="translate(${f2(x)} ${f2(y)}) rotate(${f2(a)}) scale(${f2(k)})" d="M0-4C0-14-16-14-16-2C-16 8 0 16 0 22C0 16 16 8 16-2C16-14 0-14 0-4Z" fill="${cols[i % 3]}" opacity=".88"/>`;
    }
    return s;
  },

  lightleak({ W, H, id }) {
    return `<defs><radialGradient id="${id}a" cx="100%" cy="0%" r="75%"><stop offset="0" stop-color="#ff7a2f" stop-opacity=".75"/><stop offset=".5" stop-color="#ff3d6e" stop-opacity=".28"/><stop offset="1" stop-color="#ff3d6e" stop-opacity="0"/></radialGradient>` +
      `<linearGradient id="${id}b" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffc24a" stop-opacity=".5"/><stop offset=".25" stop-color="#ffc24a" stop-opacity="0"/></linearGradient></defs>` +
      `<rect width="${W}" height="${H}" fill="url(#${id}a)"/><rect width="${W}" height="${H}" fill="url(#${id}b)"/>`;
  },

  filmlines({ W, H, rnd }) {
    let s = '';
    for (let i = 0; i < 6; i++) {
      const y = rnd() * H, x = rnd() * W * 0.4, w = W * (0.35 + rnd() * 0.6);
      s += `<rect x="${f2(x)}" y="${f2(y)}" width="${f2(w)}" height="${f2(1 + rnd() * 1.6)}" fill="${i % 3 ? '#fff' : '#000'}" opacity="${f2(0.1 + rnd() * 0.16)}"/>`;
    }
    const bandY = H * (0.25 + rnd() * 0.5);
    s += `<rect x="0" y="${f2(bandY)}" width="${W}" height="${f2(5 + rnd() * 9)}" fill="#fff" opacity=".07"/>`;
    s += `<rect x="${f2(W * (0.1 + rnd() * 0.8))}" y="0" width="1.5" height="${H}" fill="#fff" opacity=".13"/>`;
    return s;
  },

  dust({ W, H, rnd }) {
    let s = '';
    for (let i = 0; i < 60; i++) s += `<circle cx="${f2(rnd() * W)}" cy="${f2(rnd() * H)}" r="${f2(0.8 + rnd() * 2.2)}" fill="${rnd() > 0.5 ? '#fff' : '#2a1608'}" opacity="${f2(0.25 + rnd() * 0.5)}"/>`;
    for (let i = 0; i < 3; i++) {
      const x = rnd() * W, y = rnd() * H * 0.4;
      s += `<path d="M${f2(x)} ${f2(y)}q${f2((rnd() - 0.5) * 30)} ${f2(H * 0.25)} ${f2((rnd() - 0.5) * 20)} ${f2(H * 0.5)}" fill="none" stroke="#fff" stroke-width="1.3" opacity=".35"/>`;
    }
    return s;
  },

  datestamp({ W, H }) {
    const d = new Date();
    const text = `${d.getMonth() + 1} ${d.getDate()} '${String(d.getFullYear()).slice(2)}`;
    return `<text x="${W - 40}" y="${H - 40}" text-anchor="end" font-family="${FONT_MONO}" font-size="40" font-weight="700" fill="#ff8a1f" opacity=".92">${text}</text>`;
  },

  confetti({ W, H, pal, rnd }) {
    const cols = [pal[1], pal[2], '#fff', '#ffd166', '#ef476f'];
    let s = '';
    for (let i = 0; i < 40; i++) {
      const [x, y] = edgePoint(W, H, rnd);
      s += `<rect x="${f2(x)}" y="${f2(y)}" width="${f2(8 + rnd() * 10)}" height="${f2(14 + rnd() * 12)}" rx="3" transform="rotate(${f2(rnd() * 180)} ${f2(x)} ${f2(y)})" fill="${cols[i % 5]}" opacity=".9"/>`;
    }
    return s;
  },
};

/** Back layers first, face-adjacent details last. */
const STICKER_ORDER = ['lightleak', 'halftone', 'rays', 'scanlines', 'grid', 'glitch', 'filmlines', 'dust', 'confetti', 'stars',
  'sparkles', 'petals', 'hearts', 'paws', 'chalk', 'blush', 'whiskers', 'nose', 'ears', 'kittens', 'hud', 'datestamp'];

/* ---------- frames ---------- */
function roundedRectPath(x, y, w, h, r) {
  return `M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + h - r}A${r} ${r} 0 0 1 ${x + w - r} ${y + h}` +
    `H${x + r}A${r} ${r} 0 0 1 ${x} ${y + h - r}V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`;
}

/** Retro-future photo-booth frame: circuit traces, metal bevel, neon window, caption plate, CD disc. */
function cyberFrame(recipe, rnd) {
  const [navy, vio, cyan] = recipe.palette;
  const win = { x: 92, y: 92, w: 840, h: 716, r: 26 };
  const winPath = roundedRectPath(win.x, win.y, win.w, win.h, win.r);

  let traces = '';
  for (let i = 0; i < 36; i++) {                         // traces leave the window edge, jog 45 degrees, run off the frame
    const side = i % 4, col = i % 2 ? cyan : vio;
    let x, y, dx = 0, dy = 0;
    if (side === 0) { x = win.x + 50 + rnd() * (win.w - 100); y = win.y - 4; dy = -1; }
    else if (side === 1) { x = win.x + win.w + 4; y = win.y + 40 + rnd() * (win.h - 80); dx = 1; }
    else if (side === 2) { x = win.x + 50 + rnd() * (win.w - 100); y = win.y + win.h + 4; dy = 1; }
    else { x = win.x - 4; y = win.y + 40 + rnd() * (win.h - 80); dx = -1; }
    const bend = rnd() < 0.5 ? -1 : 1, a = 14 + rnd() * 40, b = 10 + rnd() * 26, c = 20 + rnd() * 70;
    const px = dy !== 0 ? bend : 0, py = dx !== 0 ? bend : 0;
    let d = `M${f2(x)} ${f2(y)}`;
    x += dx * a; y += dy * a; d += `L${f2(x)} ${f2(y)}`;
    x += (dx + px) * b; y += (dy + py) * b; d += `L${f2(x)} ${f2(y)}`;
    x += dx * c; y += dy * c; d += `L${f2(x)} ${f2(y)}`;
    traces += `<path d="${d}" stroke="${col}"/><circle cx="${f2(x)}" cy="${f2(y)}" r="5" fill="${navy}" stroke="${col}"/>`;
  }
  let chips = '';
  for (let i = 0; i < 10; i++) chips += `<rect x="${f2(40 + i * 95 + rnd() * 30)}" y="${f2(28 + rnd() * 34)}" width="${f2(22 + rnd() * 34)}" height="${f2(9 + rnd() * 5)}" rx="3"/>`;
  for (let i = 0; i < 8; i++) for (const x of [24, 960]) chips += `<rect x="${f2(x + rnd() * 30)}" y="${f2(130 + i * 85 + rnd() * 30)}" width="${f2(12 + rnd() * 10)}" height="${f2(22 + rnd() * 26)}" rx="3"/>`;

  const bracket = (x, y, sx, sy) =>
    `<path d="M${x} ${y + sy * 70}V${y}H${x + sx * 70}" fill="none" stroke="${cyan}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>` +
    `<path d="M${x + sx * 78} ${y - 6}l${sx * 14} 6l${-sx * 14} 6z" fill="#ff3d9a"/>`;

  const cdx = 118, cdy = 900, cdr = 62, wedgeColours = [cyan, vio, '#ff4fd8', '#ffe45c'];
  let wedges = '';
  for (let i = 0; i < 8; i++) {
    const a1 = (i / 8) * Math.PI * 2, a2 = ((i + 1) / 8) * Math.PI * 2;
    wedges += `<path d="M${cdx} ${cdy}L${f2(cdx + Math.cos(a1) * 70)} ${f2(cdy + Math.sin(a1) * 70)}A70 70 0 0 1 ${f2(cdx + Math.cos(a2) * 70)} ${f2(cdy + Math.sin(a2) * 70)}Z" fill="${wedgeColours[i % 4]}"/>`;
  }

  const back = `<defs>` +
    `<clipPath id="cring"><path clip-rule="evenodd" d="M0 0H1024V1024H0Z${winPath}"/></clipPath>` +
    `<clipPath id="cdclip"><circle cx="${cdx}" cy="${cdy}" r="${cdr}"/></clipPath>` +
    `<linearGradient id="cbg" x1="0" y1="0" x2="0.4" y2="1"><stop offset="0" stop-color="${navy}"/><stop offset="1" stop-color="#1c1048"/></linearGradient>` +
    `<radialGradient id="cglow" cx="50%" cy="45%" r="60%"><stop offset="0" stop-color="${vio}" stop-opacity=".35"/><stop offset="1" stop-color="${vio}" stop-opacity="0"/></radialGradient>` +
    `<linearGradient id="metal" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f6f8ff"/><stop offset=".3" stop-color="#8d9fc9"/><stop offset=".55" stop-color="#e3e9f8"/><stop offset="1" stop-color="#56668f"/></linearGradient>` +
    `<radialGradient id="cdbase"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#a9b5d3"/></radialGradient></defs>` +
    `<rect width="1024" height="1024" fill="url(#cbg)"/><rect width="1024" height="1024" fill="url(#cglow)"/>` +
    `<g clip-path="url(#cring)" fill="none" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" opacity=".92">${traces}</g>` +
    `<g clip-path="url(#cring)" fill="none" stroke="${cyan}" stroke-width="2.4" opacity=".65">${chips}</g>`;

  const fs = Math.max(26, Math.min(44, 500 / (Math.max(1, recipe.caption.length) * 0.6)));
  const deco =
    `<rect x="10" y="10" width="1004" height="1004" rx="54" fill="none" stroke="url(#metal)" stroke-width="16"/>` +
    `<rect x="28" y="28" width="968" height="968" rx="42" fill="none" stroke="${vio}" stroke-width="2.5" opacity=".9"/>` +
    `<g filter="url(#glow)"><rect x="22" y="22" width="980" height="980" rx="46" fill="none" stroke="${cyan}" stroke-width="3" opacity=".85"/></g>` +
    `<path d="${roundedRectPath(win.x - 9, win.y - 9, win.w + 18, win.h + 18, win.r + 9)}" fill="none" stroke="url(#metal)" stroke-width="12"/>` +
    `<g filter="url(#glow)"><path d="${winPath}" fill="none" stroke="${cyan}" stroke-width="5"/></g>` +
    bracket(win.x - 26, win.y - 26, 1, 1) + bracket(win.x + win.w + 26, win.y - 26, -1, 1) +
    bracket(win.x - 26, win.y + win.h + 26, 1, -1) + bracket(win.x + win.w + 26, win.y + win.h + 26, -1, -1) +
    `<rect x="206" y="830" width="612" height="88" rx="22" fill="#070a22" stroke="${cyan}" stroke-width="3"/>` +
    `<rect x="216" y="840" width="592" height="68" rx="15" fill="none" stroke="${vio}" stroke-width="1.5" opacity=".85"/>` +
    `<path d="M240 862l16 12-16 12M268 862l16 12-16 12M784 862l-16 12 16 12M756 862l-16 12 16 12" fill="none" stroke="${cyan}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity=".8"/>` +
    `<text x="512" y="${f2(874 + fs * 0.34)}" text-anchor="middle" font-family="${FONT_DISPLAY}" font-size="${f2(fs)}" fill="#fff" letter-spacing="2" filter="url(#glow)">${esc(recipe.caption)}</text>` +
    `<text x="512" y="962" text-anchor="middle" font-family="${FONT_MONO}" font-size="18" fill="${cyan}" opacity=".7" letter-spacing="5">CGC SQUARE // PHOTO BOOTH</text>` +
    `<circle cx="${cdx}" cy="${cdy}" r="${cdr}" fill="url(#cdbase)"/><g clip-path="url(#cdclip)" opacity=".26">${wedges}</g>` +
    `<g clip-path="url(#cdclip)"><path d="M${cdx} ${cdy}L${f2(cdx + Math.cos(-1.9) * 70)} ${f2(cdy + Math.sin(-1.9) * 70)}A70 70 0 0 1 ${f2(cdx + Math.cos(-1.3) * 70)} ${f2(cdy + Math.sin(-1.3) * 70)}Z" fill="#fff" opacity=".7"/></g>` +
    `<circle cx="${cdx}" cy="${cdy}" r="54" fill="none" stroke="#7c8bb0" stroke-opacity=".35" stroke-width="1"/><circle cx="${cdx}" cy="${cdy}" r="36" fill="none" stroke="#7c8bb0" stroke-opacity=".35" stroke-width="1"/>` +
    `<circle cx="${cdx}" cy="${cdy}" r="${cdr}" fill="none" stroke="#e9eefc" stroke-width="3"/>` +
    `<circle cx="${cdx}" cy="${cdy}" r="44" fill="none" stroke="#fff" stroke-opacity=".4" stroke-width="1.5"/>` +
    `<circle cx="${cdx}" cy="${cdy}" r="19" fill="${navy}" stroke="#d6def2" stroke-width="3"/><circle cx="${cdx}" cy="${cdy}" r="7" fill="#0b1030"/>`;

  return { bg: null, back, photo: win, deco, noCaption: true };
}

function frameGeometry(frame, recipe, rnd) {
  const pal = recipe.palette;
  switch (frame) {
    case 'cyber':
      return cyberFrame(recipe, rnd);
    case 'polaroid':
      return {
        bg: '#faf5ea', photo: { x: 60, y: 60, w: 904, h: 780, r: 8 }, script: true, captionY: 942,
        deco: '<rect x="60" y="60" width="904" height="780" rx="8" fill="none" stroke="#000" stroke-opacity=".14" stroke-width="2"/>',
      };
    case 'film': {
      let holes = '';
      for (const x of [40, 944]) for (let i = 0; i < 11; i++) holes += `<rect x="${x}" y="${40 + i * 92}" width="40" height="56" rx="10" fill="#faf5ea" opacity=".9"/>`;
      return { bg: '#141012', photo: { x: 118, y: 34, w: 788, h: 956, r: 10 }, captionY: 871, deco: holes };
    }
    case 'bubble':
      return {
        bg: lighten(pal[2], 0.7), photo: { x: 34, y: 34, w: 956, h: 956, r: 76 }, captionY: 871,
        deco: `<rect x="34" y="34" width="956" height="956" rx="76" fill="none" stroke="${pal[1]}" stroke-width="6" stroke-opacity=".55"/>`,
      };
    case 'neon':
      return {
        bg: null, photo: { x: 0, y: 0, w: 1024, h: 1024, r: 0 }, captionY: 905,
        deco: `<g filter="url(#glow)"><rect x="22" y="22" width="980" height="980" rx="44" fill="none" stroke="${pal[2]}" stroke-width="7"/></g>` +
          `<rect x="40" y="40" width="944" height="944" rx="30" fill="none" stroke="${pal[1]}" stroke-width="2.5" opacity=".9"/>`,
      };
    default:
      return { bg: null, photo: { x: 0, y: 0, w: 1024, h: 1024, r: 0 }, captionY: 905, deco: '' };
  }
}

function captionSvg(recipe, geo) {
  if (recipe.caption_style === 'none') return '';
  const text = esc(recipe.caption), pal = recipe.palette;
  if (geo.script) {                                       // handwriting on a polaroid's white strip
    return `<text x="512" y="${geo.captionY}" text-anchor="middle" font-family="${FONT_HAND}" font-size="58" font-style="italic" fill="${pal[0]}">${text}</text>`;
  }
  if (recipe.caption_style === 'script') {                // cream handwriting straight on the photo
    const y = geo.captionY + 46;
    return `<text x="512" y="${y}" text-anchor="middle" font-family="${FONT_HAND}" font-size="56" font-style="italic" fill="#000" opacity=".45" transform="translate(2 3)">${text}</text>` +
      `<text x="512" y="${y}" text-anchor="middle" font-family="${FONT_HAND}" font-size="56" font-style="italic" fill="#f4ead6">${text}</text>`;
  }
  const fs = 44, h = 70, w = Math.min(900, recipe.caption.length * fs * 0.6 + 90), cy = geo.captionY;
  return `<rect x="${f2(512 - w / 2)}" y="${cy - h / 2}" width="${f2(w)}" height="${h}" rx="${h / 2}" fill="${pal[0]}" fill-opacity=".84" stroke="${pal[2]}" stroke-width="3"/>` +
    `<text x="512" y="${f2(cy + fs * 0.34)}" text-anchor="middle" font-family="${FONT_DISPLAY}" font-size="${fs}" fill="#fff" letter-spacing="1">${text}</text>`;
}

/* ---------- SVG colour filter: the browser-side stand-in for the Pillow recipe ---------- */
function buildFilter(r, id) {
  const [p0, p1, p2] = r.palette.map(rgb01);
  const warm = r.warmth * 0.22, slope = r.contrast * r.brightness, icpt = 0.5 * (1 - r.contrast);
  const parts = [];
  let cur = 'SourceGraphic', n = 0;
  const next = () => `f${n++}`;
  const channelFuncs = (tag) => ['R', 'G', 'B'].map((c) => tag(c)).join('');

  const soften = r.blur * 1.3 + (r.smooth || 0) * 1.1;
  if (soften > 0.05) { const o = next(); parts.push(`<feGaussianBlur in="${cur}" stdDeviation="${f2(soften)}" result="${o}"/>`); cur = o; }
  if (Math.abs(r.hue_shift) > 0.5) { const o = next(); parts.push(`<feColorMatrix in="${cur}" type="hueRotate" values="${f2(r.hue_shift)}" result="${o}"/>`); cur = o; }
  { const o = next(); parts.push(`<feColorMatrix in="${cur}" type="saturate" values="${f2(r.saturation)}" result="${o}"/>`); cur = o; }
  {
    const o = next(), slopes = { R: slope * (1 + warm), G: slope, B: slope * (1 - warm) };
    parts.push(`<feComponentTransfer in="${cur}" result="${o}">${channelFuncs((c) => `<feFunc${c} type="linear" slope="${f2(slopes[c])}" intercept="${f2(icpt)}"/>`)}</feComponentTransfer>`);
    cur = o;
  }
  if (r.posterize_bits < 8) {
    const o = next(), levels = 2 ** r.posterize_bits;
    const table = Array.from({ length: levels }, (_, i) => (i / (levels - 1)).toFixed(3)).join(' ');
    parts.push(`<feComponentTransfer in="${cur}" result="${o}">${channelFuncs((c) => `<feFunc${c} type="discrete" tableValues="${table}"/>`)}</feComponentTransfer>`);
    cur = o;
  }

  const LUMA = '0.2126 0.7152 0.0722 0 0 0.2126 0.7152 0.0722 0 0 0.2126 0.7152 0.0722 0 0 0 0 0 1 0';
  if (r.tint > 0.01) {
    const lum = next(), duo = next(), o = next(), idx = { R: 0, G: 1, B: 2 };
    parts.push(`<feColorMatrix in="${cur}" type="matrix" values="${LUMA}" result="${lum}"/>`);
    parts.push(`<feComponentTransfer in="${lum}" result="${duo}">${channelFuncs((c) => `<feFunc${c} type="table" tableValues="${p0[idx[c]]} ${p1[idx[c]]} ${p2[idx[c]]}"/>`)}</feComponentTransfer>`);
    parts.push(`<feComposite in="${duo}" in2="${cur}" operator="arithmetic" k1="0" k2="${f2(r.tint)}" k3="${f2(1 - r.tint)}" k4="0" result="${o}"/>`);
    cur = o;
  }
  if (r.edge_strength > 0.02) {                          // edges come from the ORIGINAL photo, lightly blurred to ignore sensor noise
    const srcLum = next(), soft = next(), raw = next(), edge = next(), merged = next();
    const ink = r.edge_mode === 'ink';
    const col = ink ? rgb01(darken(r.palette[0], 0.5)) : p2;
    const A = 16 * r.edge_strength;
    parts.push(`<feColorMatrix in="SourceGraphic" type="matrix" values="${LUMA}" result="${srcLum}"/>`);
    parts.push(`<feGaussianBlur in="${srcLum}" stdDeviation="${ink ? 1.6 : 0.8}" result="${soft}"/>`);
    parts.push(`<feConvolveMatrix in="${soft}" order="3" kernelMatrix="-1 -1 -1 -1 8 -1 -1 -1 -1" divisor="1" preserveAlpha="true" edgeMode="duplicate" result="${raw}"/>`);
    parts.push(`<feColorMatrix in="${raw}" type="matrix" values="0 0 0 0 ${col[0]} 0 0 0 0 ${col[1]} 0 0 0 0 ${col[2]} ${f2(A)} 0 0 0 ${f2(-(ink ? 0.1 : 0.06) * A)}" result="${edge}"/>`);
    if (ink) {
      parts.push(`<feMerge result="${merged}"><feMergeNode in="${cur}"/><feMergeNode in="${edge}"/></feMerge>`);
    } else {
      const glow = next();
      parts.push(`<feGaussianBlur in="${edge}" stdDeviation="4" result="${glow}"/>`);
      parts.push(`<feMerge result="${merged}"><feMergeNode in="${cur}"/><feMergeNode in="${glow}"/><feMergeNode in="${edge}"/></feMerge>`);
    }
    cur = merged;
  }
  if (r.bloom > 0.02) {                                   // soft glow: blurred copy screened over the picture
    const blur = next(), screen = next(), o = next();
    parts.push(`<feGaussianBlur in="${cur}" stdDeviation="14" result="${blur}"/>`);
    parts.push(`<feBlend in="${cur}" in2="${blur}" mode="screen" result="${screen}"/>`);
    parts.push(`<feComposite in="${screen}" in2="${cur}" operator="arithmetic" k1="0" k2="${f2(r.bloom)}" k3="${f2(1 - r.bloom)}" k4="0" result="${o}"/>`);
    cur = o;
  }
  if (r.grain > 0.02) {
    const noise = next(), gray = next(), o = next(), flat = next(), g = r.grain;
    parts.push(`<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" result="${noise}"/>`);
    parts.push(`<feColorMatrix in="${noise}" type="matrix" values="0.33 0.33 0.33 0 0 0.33 0.33 0.33 0 0 0.33 0.33 0.33 0 0 0 0 0 0 1" result="${gray}"/>`);
    parts.push(`<feComposite in="${cur}" in2="${gray}" operator="arithmetic" k1="0" k2="1" k3="${f2(g * 0.5)}" k4="${f2(-g * 0.25)}" result="${o}"/>`);
    parts.push(`<feColorMatrix in="${o}" type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 0 1" result="${flat}"/>`); // force alpha back to 1
    cur = flat;
  }
  return `<filter id="${id}" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">${parts.join('')}</filter>`;
}

/* ---------- cyberpunk lab scene (Sci-Fi look, behind a cut-out person) ---------- */
function cyberScene(recipe, rnd) {
  const [navy, vio, cyan] = recipe.palette;
  const HZ = 640;                                          // horizon line
  let windows = '';

  const skyline = (minW, maxW, minH, maxH, fill, lit, spires) => {
    let s = '', x = -24;
    while (x < 1048) {
      const w = minW + rnd() * (maxW - minW), h = minH + rnd() * (maxH - minH), y = HZ + 40 - h;
      s += `<rect x="${f2(x)}" y="${f2(y)}" width="${f2(w)}" height="${f2(h)}" fill="${fill}"/>`;
      if (spires && rnd() < spires) s += `<path d="M${f2(x + w * 0.5 - 4)} ${f2(y)}L${f2(x + w * 0.5)} ${f2(y - 36 - rnd() * 60)}L${f2(x + w * 0.5 + 4)} ${f2(y)}Z" fill="${fill}"/>`;
      if (lit) for (let wy = y + 12; wy < HZ + 20; wy += 14) for (let wx = x + 6; wx < x + w - 6; wx += 10) {
        if (rnd() < lit) windows += `<rect x="${f2(wx)}" y="${f2(wy)}" width="4" height="6" fill="${rnd() < 0.72 ? cyan : '#ffd27a'}" opacity="${f2(0.5 + rnd() * 0.5)}"/>`;
      }
      x += w + rnd() * 6;
    }
    return s;
  };
  const far = skyline(26, 60, 70, 210, '#47307f', 0, 0.25);
  const mid = skyline(34, 70, 110, 330, '#241a5a', 0.16, 0.2);
  const tower = (x, h, w) =>
    `<path d="M${x - w} ${HZ + 40}L${x - w * 0.55} ${HZ - h * 0.55}L${x - 4} ${HZ - h}L${x} ${HZ - h - 50}L${x + 4} ${HZ - h}L${x + w * 0.55} ${HZ - h * 0.55}L${x + w} ${HZ + 40}Z" fill="#1a1250"/>` +
    `<circle cx="${x}" cy="${HZ - h - 54}" r="4" fill="#ff5a7a" filter="url(#glow)"/><path d="M${x} ${HZ - h}V${HZ + 30}" stroke="${cyan}" stroke-width="2" opacity=".55"/>`;
  const near = skyline(60, 120, 60, 170, '#0d0a2a', 0.12, 0);

  const drone = (x, y, s) =>
    `<g transform="translate(${x} ${y}) scale(${s})" filter="url(#glow)"><rect x="-22" y="-5" width="44" height="10" rx="5" fill="#10132e" stroke="${cyan}" stroke-width="1.6"/>` +
    `<path d="M-32 -10H-12M12 -10H32M-32 10H-12M12 10H32" stroke="${cyan}" stroke-width="2" stroke-linecap="round"/><circle cy="7" r="2.6" fill="${cyan}"/></g>`;

  const globe = (cx, cy, r) => {
    let s = `<circle cx="${cx}" cy="${cy}" r="${r}"/>`;
    for (let i = 1; i <= 3; i++) s += `<ellipse cx="${cx}" cy="${cy}" rx="${f2(r * Math.cos(i * 0.5))}" ry="${r}"/>`;
    for (let i = -2; i <= 2; i++) s += `<ellipse cx="${cx}" cy="${f2(cy + i * r * 0.3)}" rx="${f2(r * Math.sqrt(1 - (i * 0.3) ** 2))}" ry="${f2(r * 0.12)}"/>`;
    s += `<ellipse cx="${cx}" cy="${cy}" rx="${f2(r * 1.45)}" ry="${f2(r * 0.32)}" transform="rotate(-22 ${cx} ${cy})"/>`;
    return `<g fill="none" stroke="${cyan}" stroke-width="2.4" opacity=".78" filter="url(#glow)">${s}</g>`;
  };

  let codeLines = '';
  for (let i = 0; i < 7; i++) codeLines += `<rect x="${f2(26 + rnd() * 14)}" y="${718 + i * 24}" width="${f2(60 + rnd() * 190)}" height="5" rx="2.5"/>`;
  let panelLines = '';
  for (let i = 0; i < 5; i++) panelLines += `<rect x="730" y="${300 + i * 12}" width="${f2(70 + rnd() * 160)}" height="4" rx="2"/>`;

  return `<defs>` +
    `<linearGradient id="skyg" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="${HZ + 40}"><stop offset="0" stop-color="#0d0a2e"/><stop offset=".3" stop-color="#2b1a63"/><stop offset=".5" stop-color="#7b2f8f"/>` +
    `<stop offset=".68" stop-color="#e2557a"/><stop offset=".82" stop-color="#ff9a55"/><stop offset=".95" stop-color="#ffc06a"/></linearGradient>` +
    `<radialGradient id="sung"><stop offset="0" stop-color="#fff1c0" stop-opacity="1"/><stop offset=".25" stop-color="#ffb35a" stop-opacity=".55"/><stop offset="1" stop-color="#ff7a45" stop-opacity="0"/></radialGradient>` +
    `<radialGradient id="svig" cx="50%" cy="48%" r="75%"><stop offset=".55" stop-color="#05051a" stop-opacity="0"/><stop offset="1" stop-color="#05051a" stop-opacity=".6"/></radialGradient>` +
    `</defs>` +
    `<rect width="1024" height="1024" fill="url(#skyg)"/>` +
    `<circle cx="780" cy="${HZ - 40}" r="200" fill="url(#sung)"/><circle cx="780" cy="${HZ - 40}" r="34" fill="#fff4cf"/>` +
    `<g fill="#ff8fb0" opacity=".28"><ellipse cx="250" cy="${HZ - 150}" rx="190" ry="10"/><ellipse cx="760" cy="${HZ - 210}" rx="230" ry="12"/><ellipse cx="560" cy="${HZ - 90}" rx="160" ry="8"/></g>` +
    `<g opacity=".9">${far}</g>${mid}${tower(300, 470, 26)}${tower(690, 400, 22)}${near}${windows}` +
    `<rect x="0" y="${HZ + 40}" width="1024" height="${1024 - HZ - 40}" fill="#0d0a2a"/>` +
    drone(350, 270, 1.1) + drone(600, 215, 0.9) + drone(820, 330, 0.8) +
    globe(120, 470, 120) +
    `<g filter="url(#glow)"><rect x="720" y="34" width="290" height="340" rx="10" fill="rgba(8,24,52,.62)" stroke="${cyan}" stroke-width="3"/></g>` +
    `<g stroke="${cyan}" fill="none" stroke-width="2.4" opacity=".9" transform="translate(865 190)"><circle cy="-96" r="22"/><rect x="-30" y="-68" width="60" height="80" rx="8"/>` +
    `<path d="M-30-58L-62-20-58 40M30-58L62-20 58 40M-16 12L-20 100M16 12L20 100M-60-130H60M0-150V110" opacity=".8"/><circle cx="-62" cy="-20" r="5"/><circle cx="62" cy="-20" r="5"/><circle cy="12" r="5"/></g>` +
    `<g fill="${cyan}" opacity=".55">${panelLines}</g>` +
    `<g filter="url(#glow)"><rect x="18" y="690" width="310" height="200" rx="8" fill="rgba(8,24,52,.68)" stroke="${cyan}" stroke-width="3"/></g><g fill="${cyan}" opacity=".6">${codeLines}</g>` +
    `<g fill="${cyan}" filter="url(#glow)"><rect x="0" y="18" width="380" height="8" rx="4"/><rect x="1006" y="130" width="8" height="430" rx="4"/><rect x="690" y="1004" width="300" height="8" rx="4"/><rect x="18" y="960" width="8" height="64" rx="4"/></g>` +
    `<rect width="1024" height="1024" fill="url(#svig)"/>`;
}

/* ---------- the composite ---------- */
/**
 * @param {string}  photo        data URL of the photo (already styled by the server, or the raw capture)
 * @param {object}  recipe       a full recipe (see DEFAULT_RECIPES)
 * @param {boolean} applyFilter  true when the browser must do the colour styling itself (server unreachable)
 * @returns {string} a 1024x1024 SVG document
 */
function composeSvg({ photo, recipe, applyFilter }) {
  const S = 1024, id = 'k' + Math.floor(Math.random() * 1e6);
  const pal = recipe.palette;
  const rnd = mulberry32((Date.now() ^ Math.floor(Math.random() * 1e9)) >>> 0);
  const geo = recipe.scene === 'cyber'
    ? { bg: null, back: cyberScene(recipe, rnd), photo: { x: 0, y: 0, w: 1024, h: 1024, r: 0 }, deco: '', noCaption: true }
    : frameGeometry(recipe.frame, recipe, rnd);
  const ph = geo.photo;
  const face = faceBox(ph.w, ph.h);

  const chosen = STICKER_ORDER.filter((name) => recipe.stickers.includes(name) && STICKERS[name]);
  const stickers = chosen.map((name) => STICKERS[name]({ W: ph.w, H: ph.h, pal, rnd, face, id: `${id}${name}` })).join('');

  const vignette = applyFilter && recipe.vignette > 0.02
    ? `<radialGradient id="vg" cx="50%" cy="50%" r="72%"><stop offset=".5" stop-color="${darken(pal[0], 0.5)}" stop-opacity="0"/><stop offset="1" stop-color="${darken(pal[0], 0.5)}" stop-opacity="${f2(recipe.vignette)}"/></radialGradient>`
    : '';

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${S}" height="${S}" viewBox="0 0 ${S} ${S}">` +
    `<defs>${applyFilter ? buildFilter(recipe, 'fx') : ''}${vignette}` +
    `<filter id="glow" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>` +
    `<clipPath id="pc"><rect x="${ph.x}" y="${ph.y}" width="${ph.w}" height="${ph.h}" rx="${ph.r}"/></clipPath></defs>` +
    (geo.bg ? `<rect width="${S}" height="${S}" fill="${geo.bg}"/>` : '') + (geo.back || '') +
    `<g clip-path="url(#pc)">` +
    `<image href="${photo}" x="${ph.x}" y="${ph.y}" width="${ph.w}" height="${ph.h}" preserveAspectRatio="xMidYMid slice"${applyFilter ? ' filter="url(#fx)"' : ''}/>` +
    (vignette ? `<rect x="${ph.x}" y="${ph.y}" width="${ph.w}" height="${ph.h}" fill="url(#vg)"/>` : '') +
    `<g transform="translate(${ph.x} ${ph.y})">${stickers}</g></g>` +
    geo.deco + (geo.noCaption ? '' : captionSvg(recipe, geo)) + `</svg>`;
}

/* ---------- Photo-booth print: the saved and shown picture ---------- */
/** Change these two lines to change the text printed on every print. */
const EVENT_TAG = '#Parivartan2k26';
const EVENT_PLACE = 'CGC Landran';

const POLAROID = { W: 1024, H: 1200, win: { x: 96, y: 124, size: 832 } };   // dark frame, square photo window, chalk strip below
const FONT_CHALK = "'Segoe Print','Chalkboard SE','Bradley Hand','Segoe Script','Comic Sans MS',cursive";

/* Original die-cut "paper sticker" icons, drawn in a -50..50 box. Each takes two colours from the pastel set. */
const ink = (w = 3) => `stroke="#2d2233" stroke-width="${w}" stroke-linejoin="round" stroke-linecap="round"`;
const PASTELS = ['#ff9ec4', '#ffd75e', '#8fd3ff', '#b9f08c', '#c4a7ff', '#ffb36b', '#ffffff', '#7fe0d4'];
const ICONS = {
  brain: (a) => {
    const half = `<path d="M0 -34C-14 -40 -32 -32 -32 -16C-44 -12 -44 8 -34 12C-36 26 -24 36 -12 32C-8 38 0 36 0 30Z" fill="${a}" ${ink()}/>` +
      `<path d="M-10 -22q-8 4 -6 12M-24 -4q8 -2 10 6M-8 8q-6 6 0 12" fill="none" ${ink(2.2)}/>`;
    return `<g>${half}</g><g transform="scale(-1 1)">${half}</g>`;
  },
  globe: (a) => `<circle r="32" fill="#cfe9ff" ${ink()}/><ellipse rx="14" ry="32" fill="none" ${ink(2.2)}/><path d="M-32 0H32M-28 -16H28M-28 16H28" fill="none" ${ink(2.2)}/>` +
    `<ellipse rx="44" ry="12" transform="rotate(-24)" fill="none" stroke="${a}" stroke-width="7"/>`,
  gamepad: (a) => `<path d="M-40 -4C-42 -20 -28 -26 -16 -26H16C28 -26 42 -20 40 -4L34 22C32 32 20 32 16 24L12 14H-12L-16 24C-20 32 -32 32 -34 22Z" fill="#f7f7fb" ${ink()}/>` +
    `<path d="M-23 -17v20M-33 -7h20" stroke="#2d2233" stroke-width="7" stroke-linecap="round"/><circle cx="22" cy="-12" r="5" fill="${a}" ${ink(2)}/><circle cx="31" cy="-3" r="5" fill="#8fd3ff" ${ink(2)}/>`,
  bulb: (a) => `<circle cy="-8" r="22" fill="${a}" ${ink()}/><rect x="-9" y="12" width="18" height="14" rx="3" fill="#cfd3da" ${ink()}/><path d="M-6 -4l6 9l6 -9" fill="none" ${ink(2.4)}/>` +
    `<path d="M0 -42V-48M-30 -30l-5 -5M30 -30l5 -5M-40 -8h-6M40 -8h6" stroke="${a}" stroke-width="4" stroke-linecap="round"/>`,
  usb: (a) => `<rect x="-14" y="-8" width="28" height="46" rx="9" fill="${a}" ${ink()}/><rect x="-9" y="-40" width="18" height="34" rx="2" fill="#e8ebf2" ${ink()}/><rect x="-5" y="-33" width="4" height="8" fill="#2d2233"/><rect x="2" y="-33" width="4" height="8" fill="#2d2233"/><circle cy="20" r="4" fill="#fff" ${ink(2)}/>`,
  plane: (a) => `<path d="M-42 -6L42 -36L14 36L2 8Z" fill="${a}" ${ink()}/><path d="M-42 -6L2 8L42 -36M2 8L14 36" fill="none" ${ink(2.4)}/><path d="M2 8L42 -36L14 36Z" fill="#000" opacity=".1"/>`,
  laptop: (a) => `<rect x="-30" y="-32" width="60" height="42" rx="5" fill="#e9eef8" ${ink()}/><rect x="-24" y="-26" width="48" height="30" rx="2" fill="${a}"/><path d="M-42 16H42L35 30H-35Z" fill="#cfd6e6" ${ink()}/><path d="M-6 22h12" stroke="#2d2233" stroke-width="2.4" stroke-linecap="round"/>`,
  mouse: (a) => `<path d="M0 -30q0 -14 14 -16" fill="none" ${ink()}/><ellipse cy="4" rx="22" ry="32" fill="${a}" ${ink()}/><path d="M0 -28V-6M-22 -6H22" fill="none" ${ink(2.4)}/>`,
  printer: (a) => `<rect x="-20" y="-34" width="40" height="30" fill="#fff" ${ink()}/><rect x="-36" y="-6" width="72" height="36" rx="9" fill="${a}" ${ink()}/><rect x="-22" y="20" width="44" height="22" fill="#fff" ${ink()}/><circle cx="26" cy="6" r="3.5" fill="#ff5f7a"/>`,
  camera: (a) => `<path d="M-14 -20l5 -11h18l5 11Z" fill="${a}" ${ink()}/><rect x="-40" y="-20" width="80" height="52" rx="10" fill="${a}" ${ink()}/><circle cy="6" r="18" fill="#fff" ${ink()}/><circle cy="6" r="10" fill="#3a6c9a" ${ink(2)}/><circle cx="-28" cy="-10" r="3" fill="#fff"/>`,
  wifi: (a) => `<g fill="none" stroke="${a}" stroke-width="9" stroke-linecap="round"><path d="M-36 -8A52 52 0 0 1 36 -8"/><path d="M-24 6A34 34 0 0 1 24 6"/><path d="M-12 20A16 16 0 0 1 12 20"/></g><circle cy="34" r="6" fill="${a}"/>`,
  robot: (a) => `<path d="M0 -28V-42" ${ink()}/><circle cy="-44" r="5" fill="#ff5f7a" ${ink(2)}/><rect x="-40" y="-8" width="10" height="22" rx="5" fill="${a}" ${ink()}/><rect x="30" y="-8" width="10" height="22" rx="5" fill="${a}" ${ink()}/>` +
    `<rect x="-31" y="-28" width="62" height="54" rx="18" fill="#fff" ${ink()}/><rect x="-23" y="-16" width="46" height="28" rx="13" fill="#31407a"/><circle cx="-10" cy="-2" r="5" fill="#7ff3ff"/><circle cx="10" cy="-2" r="5" fill="#7ff3ff"/>`,
  cpu: (a) => `<path d="M-14 -26v-12M0 -26v-12M14 -26v-12M-14 26v12M0 26v12M14 26v12M-26 -14h-12M-26 0h-12M-26 14h-12M26 -14h12M26 0h12M26 14h12" stroke="#2d2233" stroke-width="4" stroke-linecap="round"/>` +
    `<rect x="-26" y="-26" width="52" height="52" rx="7" fill="${a}" ${ink()}/><rect x="-18" y="-18" width="36" height="36" rx="4" fill="none" ${ink(2)}/><text y="6" text-anchor="middle" font-family="Consolas,monospace" font-weight="800" font-size="15" fill="#2d2233">CPU</text>`,
  gear: (a) => `<circle r="34" fill="none" stroke="${a}" stroke-width="12" stroke-dasharray="13.35 13.35"/><circle r="26" fill="${a}" ${ink()}/><circle r="10" fill="#fff" ${ink()}/>`,
  rocket: (a) => `<path d="M-12 8L-28 30L-12 24Z" fill="${a}" ${ink()}/><path d="M12 8L28 30L12 24Z" fill="${a}" ${ink()}/><path d="M-6 24Q0 46 6 24Z" fill="#ffb347" ${ink(2)}/>` +
    `<path d="M0 -44C17 -28 19 4 12 26H-12C-19 4 -17 -28 0 -44Z" fill="#fff" ${ink()}/><circle cy="-10" r="8" fill="#7fd0ff" ${ink()}/>`,
  satellite: (a) => `<g transform="rotate(-30)"><rect x="-48" y="-9" width="32" height="18" fill="${a}" ${ink()}/><rect x="16" y="-9" width="32" height="18" fill="${a}" ${ink()}/><path d="M-32 -9v18M-40 0h16M32 -9v18M24 0h16" stroke="#2d2233" stroke-width="1.8"/>` +
    `<rect x="-13" y="-15" width="26" height="30" rx="6" fill="#eef0f6" ${ink()}/><circle r="6" fill="#8fd3ff" ${ink(2)}/><path d="M0 -15V-26" ${ink()}/><circle cy="-28" r="3.5" fill="#ff5f7a"/></g>`,
  glasses: (a) => `<path d="M-34 -2H34M-44 -8L-32 -2M44 -8L32 -2" fill="none" stroke="${a}" stroke-width="6" stroke-linecap="round"/><circle cx="-18" cy="4" r="17" fill="#ffffff55" stroke="${a}" stroke-width="6"/><circle cx="18" cy="4" r="17" fill="#ffffff55" stroke="${a}" stroke-width="6"/>`,
  code: (a) => `<rect x="-38" y="-22" width="76" height="44" rx="11" fill="${a}" ${ink()}/><text y="9" text-anchor="middle" font-family="Consolas,monospace" font-weight="800" font-size="26" fill="#2d2233">&lt;/&gt;</text>`,
  ai: (a) => `<circle r="32" fill="${a}" ${ink()}/><text y="11" text-anchor="middle" font-family="${FONT_DISPLAY}" font-size="32" fill="#2d2233">AI</text><path d="M26 -26l5 -5M30 -18h8" stroke="#fff" stroke-width="4" stroke-linecap="round"/>`,
};
const ICON_NAMES = Object.keys(ICONS);

function paperFlower(x, y, r, rot) {
  let petals = '';
  for (let i = 0; i < 8; i++) {
    petals += `<ellipse cx="0" cy="${-r * 0.5}" rx="${r * 0.34}" ry="${r * 0.52}" transform="rotate(${i * 45})" fill="${i % 2 ? '#b6f28a' : '#9fe874'}" stroke="#4f9a3a" stroke-width="2.4"/>`;
  }
  return `<g transform="translate(${x} ${y}) rotate(${rot})" filter="url(#pzshadow)">${petals}` +
    `<circle r="${r * 0.2}" fill="#f0a35e" stroke="#b86a2a" stroke-width="2.4"/><circle r="${r * 0.09}" fill="#c8742f"/></g>`;
}

/** Strand of paper bunting across the top. */
function bunting(rnd) {
  const cols = ['#ff9ec4', '#ffd75e', '#8fd3ff', '#b9f08c', '#c4a7ff', '#ffb36b'];
  const path = (t) => [40 + t * 944, 16 + Math.sin(t * Math.PI) * 44];
  let flags = '';
  const n = 13;
  for (let i = 0; i < n; i++) {
    const t = (i + 0.5) / n, [x, y] = path(t), h = 46 + rnd() * 10, w = 25;
    flags += `<path d="M${f2(x - w)} ${f2(y - 2)}L${f2(x + w)} ${f2(y + 2)}L${f2(x)} ${f2(y + h)}Z" fill="${cols[i % cols.length]}" stroke="#2d2233" stroke-opacity=".5" stroke-width="2" stroke-linejoin="round"/>`;
  }
  return `<path d="M40 16Q512 104 984 16" fill="none" stroke="#e9dcc2" stroke-width="3"/><g filter="url(#pzshadow)">${flags}</g>`;
}

/**
 * Wrap the finished 1024x1024 picture (from composeSvg) in a photo-booth frame: dark cardboard, a collage of die-cut paper
 * tech stickers, bunting, paper flowers, and the event hashtag in chalk with a location pin on the bottom strip.
 * Returns a complete SVG document, POLAROID.W x POLAROID.H. A fresh sticker arrangement is made for every print.
 */
function composePolaroid(squareSvg) {
  const { W, H, win } = POLAROID;
  const rnd = mulberry32((Date.now() ^ Math.floor(Math.random() * 1e9)) >>> 0);
  const inner = squareSvg.replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');
  const pick = (() => {                                              // every icon once before any repeats
    let bag = [];
    return () => { if (!bag.length) bag = ICON_NAMES.filter((n) => n !== 'camera' && n !== 'wifi').sort(() => rnd() - 0.5); return bag.pop(); };
  })();
  const sticker = (name, x, y, scale, rot, colour) =>
    `<g transform="translate(${f2(x)} ${f2(y)}) rotate(${f2(rot)}) scale(${f2(scale)})" filter="url(#pzsticker)">${ICONS[name](colour)}</g>`;
  const colour = () => PASTELS[Math.floor(rnd() * PASTELS.length)];

  const spots = [];
  const winBottom = win.y + win.size;
  for (let i = 0; i < 8; i++) {                                      // left and right borders
    const y = win.y + 30 + i * ((win.size - 60) / 7);
    spots.push([50 + (rnd() - 0.5) * 12, y + (rnd() - 0.5) * 16, 1.12 + rnd() * 0.22, (rnd() - 0.5) * 56]);
    spots.push([W - 50 + (rnd() - 0.5) * 12, y + (rnd() - 0.5) * 16, 1.12 + rnd() * 0.22, (rnd() - 0.5) * 56]);
  }
  for (const x of [190, 340, 684, 834]) spots.push([x + (rnd() - 0.5) * 20, 98 + (rnd() - 0.5) * 8, 0.8 + rnd() * 0.12, (rnd() - 0.5) * 44]);   // top
  spots.push([118, winBottom + 84, 1.05, -8], [W - 118, winBottom + 84, 1.0, 8]);                                                              // bottom corners
  let stickers = '';
  const fixed = { 14: 'camera', 15: 'wifi' };                        // camera bottom-left, wifi bottom-right like a real booth
  spots.forEach((s, i) => { stickers += sticker(fixed[i - (spots.length - 2) + 14] || pick(), s[0], s[1], s[2], s[3], colour()); });

  const tagY = winBottom + 112, placeY = winBottom + 188, tagSize = 80, placeSize = 44;
  const placeW = EVENT_PLACE.length * placeSize * 0.5, pinW = 30, gap = 14;
  const rowX = (W - (pinW + gap + placeW)) / 2;
  const pin = `<g transform="translate(${f2(rowX)} ${placeY - 36})"><path d="M${pinW / 2} 38C${pinW / 2 - 3} 31 0 23 0 ${pinW / 2}A${pinW / 2} ${pinW / 2} 0 1 1 ${pinW} ${pinW / 2}C${pinW} 23 ${pinW / 2 + 3} 31 ${pinW / 2} 38Z" fill="#ff7fa8" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"/><circle cx="${pinW / 2}" cy="${pinW / 2}" r="5.5" fill="#2a2321"/></g>`;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
    `<defs>` +
    `<filter id="pzcard" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="3" seed="5"/>` +
    `<feColorMatrix type="matrix" values="0 0 0 0 0.75  0 0 0 0 0.62  0 0 0 0 0.5  0 0 0 0.16 0"/></filter>` +
    `<filter id="pzsticker" x="-20%" y="-20%" width="140%" height="140%"><feMorphology in="SourceAlpha" operator="dilate" radius="4.5" result="d"/>` +
    `<feFlood flood-color="#fffdf6"/><feComposite in2="d" operator="in" result="edge"/>` +
    `<feGaussianBlur in="d" stdDeviation="3" result="b"/><feOffset in="b" dx="2" dy="4" result="s"/><feComponentTransfer in="s" result="shadow"><feFuncA type="linear" slope=".55"/></feComponentTransfer>` +
    `<feMerge><feMergeNode in="shadow"/><feMergeNode in="edge"/><feMergeNode in="SourceGraphic"/></feMerge></filter>` +
    `<filter id="pzshadow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur in="SourceAlpha" stdDeviation="3"/><feOffset dx="2" dy="4" result="s"/>` +
    `<feComponentTransfer><feFuncA type="linear" slope=".5"/></feComponentTransfer><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>` +
    `<filter id="pzchalk" x="-5%" y="-20%" width="110%" height="140%"><feTurbulence type="fractalNoise" baseFrequency="0.045" numOctaves="2" seed="2" result="n"/>` +
    `<feDisplacementMap in="SourceGraphic" in2="n" scale="3.2"/></filter>` +
    `<linearGradient id="pzinset" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity=".35"/><stop offset=".05" stop-color="#000" stop-opacity="0"/>` +
    `<stop offset=".95" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".25"/></linearGradient>` +
    `<linearGradient id="pzboard" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#34292a"/><stop offset="1" stop-color="#211a1b"/></linearGradient>` +
    `</defs>` +
    `<rect width="${W}" height="${H}" fill="url(#pzboard)"/><rect width="${W}" height="${H}" filter="url(#pzcard)"/>` +
    `<rect x="${win.x - 10}" y="${win.y - 10}" width="${win.size + 20}" height="${win.size + 20}" fill="#15100f"/>` +
    `<svg x="${win.x}" y="${win.y}" width="${win.size}" height="${win.size}" viewBox="0 0 1024 1024">${inner}</svg>` +
    `<rect x="${win.x}" y="${win.y}" width="${win.size}" height="${win.size}" fill="url(#pzinset)"/>` +
    `<rect x="${win.x - 10}" y="${win.y - 10}" width="${win.size + 20}" height="${win.size + 20}" fill="none" stroke="#4a3d39" stroke-width="3"/>` +
    bunting(rnd) + stickers +
    paperFlower(52, win.y + 4, 72, -10) + paperFlower(W - 58, winBottom - 6, 66, 18) +
    `<g filter="url(#pzchalk)"><text x="${W / 2}" y="${tagY}" text-anchor="middle" font-family="${FONT_CHALK}" font-weight="700" font-size="${tagSize}" fill="#fbf7ee" transform="rotate(-1.5 ${W / 2} ${tagY})">${esc(EVENT_TAG)}</text>` +
    `<path d="M${W / 2 - 250} ${tagY + 20}q125 -10 250 0t250 0" fill="none" stroke="#fbf7ee" stroke-opacity=".5" stroke-width="3" stroke-linecap="round"/>` +
    pin + `<text x="${f2(rowX + pinW + gap)}" y="${placeY}" font-family="${FONT_CHALK}" font-weight="700" font-size="${placeSize}" fill="#fbf7ee">${esc(EVENT_PLACE)}</text></g>` +
    `</svg>`;
}

/** Rasterise an SVG string to a PNG Blob (what "Save photo" downloads). */
async function svgToPngBlob(svg, width = 1024) {
  const dims = /<svg[^>]*\swidth="(\d+)"[^>]*\sheight="(\d+)"/.exec(svg);
  const aspect = dims ? Number(dims[2]) / Number(dims[1]) : 1;     // the Polaroid is taller than it is wide
  const height = Math.round(width * aspect);
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
  try {
    const img = new Image();
    await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = () => reject(new Error('Could not draw the picture')); img.src = url; });
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    canvas.getContext('2d').drawImage(img, 0, 0, width, height);
    return await new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('PNG export failed'))), 'image/png'));
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Make sure a recipe from the server has every field; fall back to the theme default for gaps. */
function completeRecipe(recipe, theme) {
  const base = DEFAULT_RECIPES[theme] || DEFAULT_RECIPES['Sci-Fi'];
  const r = { ...base, ...(recipe || {}) };
  if (!Array.isArray(r.palette) || r.palette.length < 3) r.palette = base.palette;
  if (!Array.isArray(r.stickers)) r.stickers = base.stickers;
  return r;
}
