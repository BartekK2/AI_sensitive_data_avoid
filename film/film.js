const voice = document.getElementById('voice');
const play = document.getElementById('play');
const pct = document.getElementById('pct');
const ring = document.getElementById('ring');
const dots = document.getElementById('dots');
const ms = document.getElementById('ms');
const recVid = document.getElementById('rec-vid');
const packet = document.getElementById('packet');
const token = document.getElementById('token');
const wave = document.getElementById('wave');
const wordsEl = document.getElementById('words');
const ball = document.getElementById('ball');
const scenes = [...document.querySelectorAll('.scene')];
const world = document.getElementById('world');

const cams = [
  { t: 0, x: 0, y: 0, z: 0, ry: 0, rx: 2 },
  { t: 3.6, x: 180, y: -8, z: -2200, ry: -8, rx: 2 },
  { t: 8.3, x: -140, y: 8, z: -4400, ry: 7, rx: 2 },
  { t: 13.55, x: 60, y: -12, z: -6800, ry: -5, rx: 3 },
  { t: 22.15, x: -100, y: 8, z: -9200, ry: 6, rx: 2 },
  { t: 30.65, x: 120, y: -6, z: -11600, ry: -6, rx: 2 },
  { t: 36.85, x: -80, y: -10, z: -14000, ry: 5, rx: 3 },
  { t: 49.9, x: 90, y: 6, z: -16400, ry: -5, rx: 2 },
  { t: 64.9, x: -80, y: 0, z: -18600, ry: 6, rx: 2 },
  { t: 70.9, x: 40, y: -8, z: -20800, ry: -4, rx: 2 },
  { t: 75.7, x: 0, y: 0, z: -23000, ry: 2, rx: 1 },
  { t: 98.4, x: 0, y: 0, z: -25200, ry: 0, rx: 1 },
];

scenes.forEach((scene, i) => {
  const k = cams[i] || cams[cams.length - 1];
  scene.style.transform = `translate3d(${k.x}px, ${k.y}px, ${k.z}px) rotateY(${k.ry}deg) rotateX(${k.rx}deg)`;
});

function ease(u) {
  return u < 0.5 ? 4 * u * u * u : 1 - ((-2 * u + 2) ** 3) / 2;
}

function sampleCam(t) {
  let i = 0;
  while (i < cams.length - 1 && t >= cams[i + 1].t) i += 1;
  const a = cams[i];
  const b = cams[Math.min(i + 1, cams.length - 1)];
  if (a === b) return { ...a };
  const span = b.t - a.t;
  const fly = Math.min(1.05, span * 0.28);
  const local = t - a.t;
  const u = local > span - fly ? ease((local - (span - fly)) / fly) : 0;
  return {
    x: lerp(a.x, b.x, u),
    y: lerp(a.y, b.y, u) + Math.sin(t * 0.7) * 6,
    z: lerp(a.z, b.z, u),
    ry: lerp(a.ry, b.ry, u) + Math.sin(t * 0.45) * 1.1,
    rx: lerp(a.rx, b.rx, u),
  };
}

if (dots) for (let i = 0; i < 100; i++) dots.appendChild(document.createElement('i'));
if (wave) {
  for (let i = 0; i < 28; i++) {
    const b = document.createElement('b');
    b.style.height = `${40 + ((i * 37) % 70)}%`;
    b.style.animationDelay = `${(i % 8) * 0.08}s`;
    wave.appendChild(b);
  }
}

const recClips = [
  { id: 'rules', src: '../rules.mp4', t: 75.7, to: 77.66, dur: 3.648 },
  { id: 'roles', src: '../roles.mp4', t: 77.66, to: 79.7, dur: 5.1 },
  { id: 'chat', src: '../chat_view.mp4', t: 79.7, to: 92.94, dur: 11.233 },
  { id: 'incident', src: '../dashboard_incident.mp4', t: 92.94, to: 98.4, dur: 4.907 },
];
const REC_FROM = recClips[0].t;
const REC_TO = recClips[recClips.length - 1].to;
let recOn = '';

let segments = [];
let lastWord = -1;
let lastSeg = -1;

fetch('../anim/transcript.json')
  .then((r) => r.json())
  .then((data) => {
    segments = data.map((seg) => ({
      s: seg.s,
      e: seg.e,
      words: seg.words
        .map((w) => ({
          t: String(w.w || '').replace('połówne', 'poufne').replace(/[–—]/g, '').trim(),
          s: w.s,
          e: w.e,
        }))
        .filter((w) => w.t),
    }));
  });

function fit() {
  const s = Math.min(innerWidth / 1920, innerHeight / 1080);
  document.getElementById('stage').style.transform = `scale(${s})`;
}

function lerp(a, b, t) {
  return a + (b - a) * Math.min(1, Math.max(0, t));
}

function pickClip(t) {
  let cur = recClips[0];
  for (const clip of recClips) if (t >= clip.t) cur = clip;
  return cur;
}

function clipRate(clip) {
  const slot = Math.max(0.05, clip.to - clip.t);
  return clip.dur > slot ? clip.dur / slot : 1;
}

function playRec(clip) {
  if (!recVid) return;
  recVid.playbackRate = clipRate(clip);
  if (voice.paused || recVid.ended) recVid.pause();
  else if (recVid.paused) recVid.play().catch(() => {});
}

function syncRec(t) {
  if (!recVid) return;
  if (t < REC_FROM || t >= REC_TO) {
    if (recOn) {
      recVid.pause();
      recVid.removeAttribute('src');
      recOn = '';
    }
    return;
  }
  const clip = pickClip(t);
  if (recOn !== clip.id) {
    recOn = clip.id;
    recVid.src = clip.src;
    recVid.playbackRate = clipRate(clip);
    recVid.onloadeddata = () => playRec(clip);
    if (recVid.readyState >= 2) playRec(clip);
    return;
  }
  playRec(clip);
}

function mid(el, parent) {
  if (!parent.offsetWidth) return 16.6;
  return ((el.offsetLeft + el.offsetWidth / 2) / parent.offsetWidth) * 100;
}

function placeChip(chip, track, from, to, u) {
  if (!chip || !track || !from || !to) return;
  const x = lerp(mid(from, track), mid(to, track), u);
  chip.style.left = `${x}%`;
  chip.style.top = '50%';
  chip.classList.add('on');
}

function along(t, a, b) {
  return Math.min(1, Math.max(0, (t - a) / Math.max(0.01, b - a)));
}

function moveFlow(t) {
  const track = packet?.parentElement;
  const a = document.getElementById('st-agent');
  const g = document.getElementById('st-gate');
  const m = document.getElementById('st-model');
  if (!track || !a) return;
  if (t < 4.55) placeChip(packet, track, a, g, ease(along(t, 3.68, 4.55)));
  else if (t < 6.15) {
    placeChip(packet, track, g, g, 0);
    g.classList.add('inspect');
  } else placeChip(packet, track, g, m, ease(along(t, 6.15, 7.7)));
  if (t < 4.55 || t >= 6.15) g?.classList.remove('inspect');
}

function moveCheck(t) {
  const track = token?.parentElement;
  const a = document.getElementById('ck-a');
  const g = document.getElementById('ck-g');
  const model = document.getElementById('ck-m');
  if (!track || !a) return;
  if (t < 24.52) placeChip(token, track, a, a, 0);
  else if (t < 26.2) placeChip(token, track, a, g, ease(along(t, 24.52, 26.2)));
  else {
    placeChip(token, track, g, g, 0);
    g.classList.add('inspect');
  }
  if (t < 26.2) g?.classList.remove('inspect');
  if (model) model.classList.toggle('dim', t >= 27.96);
}

function karaoke(t) {
  if (!segments.length || !wordsEl) return;
  let si = 0;
  for (let i = 0; i < segments.length; i++) if (t >= segments[i].s) si = i;
  const seg = segments[si];
  if (si !== lastSeg) {
    lastSeg = si;
    lastWord = -1;
    wordsEl.innerHTML = seg.words.map((w, i) => `<b data-i="${i}">${w.t}</b>`).join('');
  }
  let wi = 0;
  for (let i = 0; i < seg.words.length; i++) if (t >= seg.words[i].s) wi = i;
  [...wordsEl.children].forEach((el, i) => {
    el.classList.toggle('said', i < wi);
    el.classList.toggle('now', i === wi && t <= seg.e + 0.12);
  });
  const now = wordsEl.children[wi];
  if (now && ball) {
    const kara = document.getElementById('kara');
    const s = Math.min(innerWidth / 1920, innerHeight / 1080) || 1;
    const kr = kara.getBoundingClientRect();
    const wr = now.getBoundingClientRect();
    ball.style.left = `${(wr.left + wr.width / 2 - kr.left) / s}px`;
    ball.style.top = `${(wr.top - kr.top) / s - 18}px`;
    ball.style.opacity = '1';
    if (wi !== lastWord) {
      lastWord = wi;
      ball.classList.remove('hop');
      void ball.offsetWidth;
      ball.classList.add('hop');
    }
  }
}

let raf = 0;

function tick() {
  try {
    const t = voice.currentTime || 0;

    const cam = sampleCam(t);
    world.style.transform = `rotateX(${-cam.rx}deg) rotateY(${-cam.ry}deg) translate3d(${-cam.x}px, ${-cam.y}px, ${-cam.z}px)`;

    scenes.forEach((scene, i) => {
      const k = cams[i] || cams[0];
      const d = Math.hypot(cam.x - k.x, (cam.z - k.z) * 0.55);
      scene.style.opacity = String(Math.max(0, 1 - (d - 180) / 820));
      const from = Number(scene.dataset.from);
      const to = Number(scene.dataset.to);
      scene.classList.toggle('on', t >= from && t < to);
    });

    if (t >= 3.6 && t < 8.3) moveFlow(t);
    else packet?.classList.remove('on');
    if (t >= 13.55 && t < 22.15) {
      const n = Math.round(lerp(0, 38, (t - 15.45) / 1.35));
      if (pct) pct.textContent = `${n}%`;
      if (ring) ring.style.strokeDashoffset = String(603 - 603 * (n / 100));
      if (dots) [...dots.children].forEach((el, i) => el.classList.toggle('on', i < n));
    }
    if (t >= 22.15 && t < 30.65) moveCheck(t);
    else token?.classList.remove('on');
    if (t >= 36.85 && t < 49.9) {
      if (ms) ms.textContent = String(Math.round(lerp(160, 28, (t - 36.85) / 1.25)));
    }

    syncRec(t);
    karaoke(t);
  } finally {
    if (!voice.paused) raf = requestAnimationFrame(tick);
    else raf = 0;
  }
}

async function start(fromStart) {
  document.body.classList.add('playing');
  if (fromStart || voice.ended) voice.currentTime = 0;
  await voice.play();
  if (!raf) raf = requestAnimationFrame(tick);
}

play.addEventListener('click', () => start(true));
document.addEventListener('keydown', (e) => {
  if (e.code !== 'Space') return;
  e.preventDefault();
  if (voice.paused) start(false);
  else voice.pause();
});
voice.addEventListener('pause', () => tick());
voice.addEventListener('ended', () => {
  document.body.classList.remove('playing');
  tick();
});
addEventListener('resize', fit);
fit();
tick();
