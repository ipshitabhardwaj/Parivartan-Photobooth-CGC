/*
 * CGC SQUARE kiosk UI (keyboard driven).
 *   A / B / C / D   pick a look
 *   SPACE           take the photo (countdown -> capture -> AI repaint); press again after the result to go on
 * Every finished photo is saved by the server as the next number (1, 2, 3, ...) and uploaded to the Google Drive
 * folder whose QR code is shown on screen. If the server can't be reached the look is made here with SVG filters.
 */
'use strict';

const THEME_COLORS = { 'Sci-Fi': '#dde4ff', 'Anime': '#ffdfec', 'Cats': '#ffe9c9', 'Vintage': '#efdcc2' };
const HINTS = {
  live: 'Press SPACE to take your photo',
  liveCats: 'Press SPACE. The kittens land on top.',
  countdown: '',
  working: '',
  done: 'Press SPACE for the next photo',
};
const IDLE_RETURN_MS = 45000;      // the result stays up this long, then the camera comes back for the next student
const RESULT_LOCK_MS = 1500;       // ignore SPACE this long after a result, so a double press can't skip it

const state = {
  theme: 'Sci-Fi',
  phase: 'live',
  stream: null,
  cameraReady: false,
  busy: false,
  resultUrl: null,
  doneAt: 0,
  idleTimer: null,
};

const hintFor = (phase) => (phase === 'live' && state.theme === 'Cats' ? HINTS.liveCats : HINTS[phase]) || '';

const $ = (id) => document.getElementById(id);
const el = {
  video: $('webcam'), result: $('resultImage'), canvas: $('captureCanvas'), square: $('photoSquare'), viewfinder: $('viewfinder'),
  loading: $('loadingOverlay'), placeholder: $('cameraPlaceholder'), cameraMessage: $('cameraMessage'),
  retryCamera: $('retryCameraBtn'), banner: $('statusBanner'), hint: $('hint'), countdown: $('countdown'),
  guide: $('faceGuide'), flash: $('flash'), looks: document.querySelectorAll('.look'),
  qrImg: $('qrImg'), qrEmpty: $('qrEmpty'), photoNo: $('photoNo'), photoNoValue: $('photoNoValue'),
};
const KEY_TO_THEME = {};
el.looks.forEach((b) => { KEY_TO_THEME[b.dataset.key] = b.dataset.theme; });

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/* ---------- phases ---------- */
function setPhase(phase) {
  state.phase = phase;
  const done = phase === 'done';
  el.square.dataset.mode = done ? 'done' : 'live';
  el.viewfinder.dataset.mode = done ? 'done' : 'live';           // the result is a taller Polaroid
  el.video.classList.toggle('hidden', done);
  el.result.classList.toggle('hidden', !done);
  el.loading.classList.toggle('hidden', phase !== 'working');
  el.countdown.classList.toggle('hidden', phase !== 'countdown');
  el.hint.textContent = hintFor(phase);
  el.guide.classList.toggle('hidden', phase === 'done' || phase === 'working');
  el.looks.forEach((b) => { b.disabled = phase === 'countdown' || phase === 'working'; });
  clearTimeout(state.idleTimer);
  if (done) {
    state.doneAt = Date.now();
    state.idleTimer = setTimeout(() => { if (state.phase === 'done') initCamera(); }, IDLE_RETURN_MS);
  }
  if (phase === 'countdown') showPhotoNumber(null);
}

function showPhotoNumber(number) {
  el.photoNoValue.textContent = number == null ? '' : `No. ${number}`;
  el.photoNo.classList.toggle('hidden', number == null);
}

/* ---------- camera ---------- */
async function initCamera() {
  setPhase('live');
  state.cameraReady = false;
  el.placeholder.classList.add('hidden');
  hideStatus();
  try {
    if (state.stream) state.stream.getTracks().forEach((t) => t.stop());
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 1280 }, facingMode: 'user' },
      audio: false,
    });
    el.video.srcObject = state.stream;
    await el.video.play().catch(() => {});
    state.cameraReady = true;
  } catch (err) {
    console.error('Camera error:', err);
    const missing = err && err.name === 'NotFoundError';
    el.cameraMessage.textContent = missing
      ? 'No camera found. Plug one in, then press SPACE.'
      : 'Camera is blocked. Allow it in the address bar, then press SPACE.';
    el.placeholder.classList.remove('hidden');
  }
}

/** Centre-crop the live video to a square, mirrored to match the preview. */
function captureSquareFrame() {
  const vw = el.video.videoWidth, vh = el.video.videoHeight;
  if (!vw || !vh) throw new Error('The camera is still warming up');
  const side = Math.min(vw, vh), sx = (vw - side) / 2, sy = (vh - side) / 2, out = 768;
  el.canvas.width = out;
  el.canvas.height = out;
  const ctx = el.canvas.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.translate(out, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(el.video, sx, sy, side, side, 0, 0, out, out);
  return el.canvas.toDataURL('image/jpeg', 0.92);
}

/* ---------- countdown + flash ---------- */
async function runCountdown(seconds = 3) {
  setPhase('countdown');
  for (let n = seconds; n >= 1; n--) {
    el.countdown.innerHTML = `<span>${n}</span>`; // fresh element restarts the pop animation
    await sleep(1000);
  }
  el.countdown.innerHTML = '';
  el.flash.classList.remove('go');
  void el.flash.offsetWidth;
  el.flash.classList.add('go');
}

/* ---------- generation ---------- */
/** A small, un-mirrored preview picture so the server can get its model ready while the countdown runs. */
function previewFrame(side = 384) {
  const vw = el.video.videoWidth, vh = el.video.videoHeight;
  if (!vw || !vh) return null;
  const s = Math.min(vw, vh), c = document.createElement('canvas');
  c.width = c.height = side;
  c.getContext('2d').drawImage(el.video, (vw - s) / 2, (vh - s) / 2, s, s, 0, 0, side, side);
  return c.toDataURL('image/jpeg', 0.85);
}

/** Tell the server to start preparing NOW. Never throws: resolves to an id, or null if the server can't be reached. */
async function startPrepare(theme) {
  try {
    const image = previewFrame();
    if (!image) return null;
    const res = await fetch('/api/prepare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image, theme }),
    });
    const data = await res.json();
    return res.ok && data.success ? data.id : null;
  } catch (err) {
    return null;
  }
}

async function requestLook(photo, theme, prepareId) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 40000);
  try {
    const res = await fetch('/api/reimagine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: photo, theme, prepareId }),
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success) throw new Error(data.error || `Server answered ${res.status}`);
    let recipe = completeRecipe(data.recipe, theme);
    // The server cut the person out (Sci-Fi quick look): drop them into the neon scene instead of the framed look.
    if (data.cutout) recipe = { ...recipe, scene: 'cyber', stickers: [], frame: 'none', caption_style: 'none' };
    return { photo: data.imageUrl, recipe, applyFilter: false, note: data.note, method: data.method };
  } finally {
    clearTimeout(timer);
  }
}

/** Browser-only look: same recipe format, rendered with SVG filters. */
function localLook(photo, theme, reason) {
  return {
    photo,
    recipe: completeRecipe(null, theme),
    applyFilter: true,
    note: `Styled in this browser with SVG filters (${reason}).`,
    method: 'svg',
  };
}

function loadImage(img, url) {
  return new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error('The picture could not be shown'));
    img.src = url;
  });
}

async function showLook(look) {
  // The print already has an ornate frame, so the Sci-Fi fallback (no person cut-out) gets a plain neon border instead of its own.
  const recipe = look.recipe.frame === 'cyber' ? { ...look.recipe, frame: 'neon', caption_style: 'pill' } : look.recipe;
  const svg = composePolaroid(composeSvg({ photo: look.photo, recipe, applyFilter: look.applyFilter }));
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
  try {
    await loadImage(el.result, url);
  } catch (err) {
    URL.revokeObjectURL(url);
    throw err;
  }
  if (state.resultUrl) URL.revokeObjectURL(state.resultUrl);
  state.resultUrl = url;
  el.result.classList.remove('developing');
  void el.result.offsetWidth;
  el.result.classList.add('developing');
  return svg;
}

const blobToDataUrl = (blob) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(reader.result);
  reader.onerror = () => reject(reader.error);
  reader.readAsDataURL(blob);
});

/** Hand the finished picture to the server: it saves it as the next numbered photo and queues the Drive upload. */
async function savePhoto(blob) {
  const res = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: await blobToDataUrl(blob) }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.success) throw new Error(data.error || `Server answered ${res.status}`);
  return data.number;
}

async function capture() {
  if (state.busy) return;
  state.busy = true;
  try {
    await takePhoto();
  } finally {
    state.busy = false;
  }
}

async function takePhoto() {
  hideStatus();
  const theme = state.theme;

  let photo;
  const preparing = startPrepare(theme);       // the server gets going while the countdown ticks
  try {
    await runCountdown(3);
    photo = captureSquareFrame();
  } catch (err) {
    setPhase('live');
    showStatus(`Could not take the photo: ${err.message}.`, 'error');
    return;
  }

  setPhase('working');
  let look;
  try {
    look = await requestLook(photo, theme, await preparing);
  } catch (err) {
    console.warn('Server look failed, using browser filters:', err);
    look = localLook(photo, theme, err.name === 'AbortError' ? 'the server took too long' : 'the server is unreachable');
  }
  console.info('Look:', look.method, '-', look.note);

  try {
    const svg = await showLook(look);
    setPhase('done');
    const png = await svgToPngBlob(svg);
    try {
      showPhotoNumber(await savePhoto(png));
    } catch (err) {
      console.warn('Save failed:', err);
      showStatus('This photo could not be saved (server offline).', 'error');
    }
  } catch (err) {
    console.error(err);
    setPhase('live');
    showStatus(`Something went wrong: ${err.message}. Try again.`, 'error');
  }
}

/* ---------- status banner (only for problems) ---------- */
function showStatus(message, type = 'info') {
  el.banner.className = `status ${type}`;
  el.banner.textContent = message;
}
function hideStatus() { el.banner.classList.add('hidden'); }

/* ---------- looks ---------- */
function renderGuide() {
  el.guide.innerHTML = guideMarkup(DEFAULT_RECIPES[state.theme].guide);
}

function selectLook(theme) {
  state.theme = theme;
  renderGuide();
  if (!state.busy) el.hint.textContent = hintFor(state.phase === 'done' ? 'done' : 'live');
  document.documentElement.dataset.theme = theme;
  $('themeColor').setAttribute('content', THEME_COLORS[theme]);
  el.looks.forEach((b) => {
    const on = b.dataset.theme === theme;
    b.classList.toggle('active', on);
    b.setAttribute('aria-checked', String(on));
  });
}

/* ---------- QR code of the Drive folder (appears once Google Drive is connected) ---------- */
function loadQr() {
  el.qrImg.onload = () => { el.qrEmpty.classList.add('hidden'); el.qrImg.classList.remove('hidden'); };
  el.qrImg.onerror = () => {
    el.qrImg.classList.add('hidden');
    el.qrEmpty.classList.remove('hidden');
    setTimeout(loadQr, 8000);                  // Drive may still be connecting: try again shortly
  };
  el.qrImg.src = `/api/qr.svg?t=${Date.now()}`;
}

/* ---------- keyboard ---------- */
function onSpace() {
  if (state.busy) return;
  if (state.phase === 'done') {                // first press after a result: back to the camera
    if (Date.now() - state.doneAt > RESULT_LOCK_MS) initCamera();
    return;
  }
  if (!state.cameraReady) {                    // camera blocked or unplugged: SPACE tries again
    if (!el.placeholder.classList.contains('hidden')) initCamera();
    return;
  }
  capture();
}

/* Match the PHYSICAL key (e.code) first, then the typed character: this works with Caps Lock, other keyboard
   layouts and input methods. Listening in the capture phase means nothing on the page can swallow the key. */
const CODE_TO_KEY = { KeyA: 'a', KeyB: 'b', KeyC: 'c', KeyD: 'd' };
function onKeyDown(e) {
  if (e.repeat || e.ctrlKey || e.metaKey) return;
  if (e.code === 'Space' || e.key === ' ' || e.key === 'Spacebar') {
    e.preventDefault();                        // no page scroll, and no click on whichever button has focus
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    onSpace();
    return;
  }
  const letter = CODE_TO_KEY[e.code] || (typeof e.key === 'string' ? e.key.toLowerCase() : '');
  const theme = KEY_TO_THEME[letter];
  if (theme) {
    e.preventDefault();
    if (state.phase !== 'countdown' && state.phase !== 'working') selectLook(theme);
  }
}
window.addEventListener('keydown', onKeyDown, true);
document.addEventListener('keydown', (e) => { if (!e.defaultPrevented && (e.code === 'Space' || CODE_TO_KEY[e.code])) onKeyDown(e); });
window.addEventListener('keyup', (e) => { if (e.code === 'Space') e.preventDefault(); });

/* ---------- wiring ---------- */
el.looks.forEach((b) => b.addEventListener('click', () => { selectLook(b.dataset.theme); b.blur(); }));
el.retryCamera.addEventListener('click', initCamera);

window.addEventListener('DOMContentLoaded', () => {
  renderGuide();
  loadQr();
  initCamera();
});
