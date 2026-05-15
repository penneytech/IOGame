// IO-style game client.
//
// Renders an "agar.io"-style camera that follows the local player. The world
// is bigger than the viewport; we translate the canvas so the local player is
// in the centre, clamping to the world boundary so the edge of the arena is
// always visible when you reach it.

(function () {
  const canvas = document.getElementById('game');
  const ctx = canvas.getContext('2d');
  const statusEl = document.getElementById('status');
  const killFeedEl = document.getElementById('killFeed');
  const playerCardEl = document.getElementById('playerCard');
  const pcPortrait = document.getElementById('pcPortrait');
  const pcName = document.getElementById('pcName');
  const pcChar = document.getElementById('pcChar');
  const hpFill = document.getElementById('hpFill');
  const hpLabel = document.getElementById('hpLabel');
  const stamFill = document.getElementById('stamFill');
  const hotbarEl = document.getElementById('hotbar');
  const bannerEl = document.getElementById('banner');

  // Floating damage numbers and particle effects.
  const floaters = [];   // { x, y, text, color, born, ttl, vy }
  const ripples = [];    // { x, y, color, born, ttl, r0, r1 }
  // Health-tracking for hit-flash effect (no need to rely on events).
  const lastHealth = Object.create(null);
  const flashes = Object.create(null);   // pid -> until-timestamp

  // --- Procedural sound effects (WebAudio) -------------------------------
  // No external assets — every sound is synthesized so it always works
  // offline and there are no licensing/CORS issues.
  const SFX = (() => {
    let ctxA = null;
    let muted = false;
    let masterGain = null;
    const ensure = () => {
      if (ctxA) return ctxA;
      try {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return null;
        ctxA = new AC();
        masterGain = ctxA.createGain();
        masterGain.gain.value = 0.35;
        masterGain.connect(ctxA.destination);
      } catch (_) { ctxA = null; }
      return ctxA;
    };
    // Resume on first user gesture (browser autoplay policy).
    const resume = () => { const a = ensure(); if (a && a.state === 'suspended') a.resume(); };
    window.addEventListener('pointerdown', resume, { once: false });
    window.addEventListener('keydown', resume, { once: false });

    const tone = (opts) => {
      const a = ensure(); if (!a || muted) return;
      const t0 = a.currentTime;
      const dur = opts.dur || 0.18;
      const osc = a.createOscillator();
      osc.type = opts.type || 'sine';
      osc.frequency.setValueAtTime(opts.f0 || 440, t0);
      if (opts.f1) osc.frequency.exponentialRampToValueAtTime(Math.max(20, opts.f1), t0 + dur);
      const g = a.createGain();
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.exponentialRampToValueAtTime(opts.peak || 0.4, t0 + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      osc.connect(g).connect(masterGain);
      osc.start(t0);
      osc.stop(t0 + dur + 0.02);
    };
    const noise = (opts) => {
      const a = ensure(); if (!a || muted) return;
      const t0 = a.currentTime;
      const dur = opts.dur || 0.18;
      const buf = a.createBuffer(1, Math.floor(a.sampleRate * dur), a.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1);
      const src = a.createBufferSource();
      src.buffer = buf;
      const filt = a.createBiquadFilter();
      filt.type = opts.filter || 'lowpass';
      filt.frequency.setValueAtTime(opts.f0 || 1200, t0);
      if (opts.f1) filt.frequency.exponentialRampToValueAtTime(Math.max(40, opts.f1), t0 + dur);
      const g = a.createGain();
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.exponentialRampToValueAtTime(opts.peak || 0.35, t0 + 0.005);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      src.connect(filt).connect(g).connect(masterGain);
      src.start(t0);
      src.stop(t0 + dur + 0.02);
    };

    return {
      cast(kind) {
        switch (kind) {
          case 'projectile': // laser zap
            tone({ type: 'sawtooth', f0: 880, f1: 220, dur: 0.16, peak: 0.35 });
            break;
          case 'area': // boom
            noise({ filter: 'lowpass', f0: 900, f1: 80, dur: 0.45, peak: 0.55 });
            tone({ type: 'sine', f0: 110, f1: 40, dur: 0.4, peak: 0.45 });
            break;
          case 'melee': // whoosh + thud
            noise({ filter: 'bandpass', f0: 2200, f1: 600, dur: 0.18, peak: 0.4 });
            tone({ type: 'square', f0: 180, f1: 90, dur: 0.12, peak: 0.3 });
            break;
          case 'dash': // upward whoosh
            noise({ filter: 'highpass', f0: 400, f1: 2400, dur: 0.22, peak: 0.35 });
            tone({ type: 'triangle', f0: 300, f1: 900, dur: 0.18, peak: 0.25 });
            break;
          case 'shield': // warm hum-up
            tone({ type: 'triangle', f0: 220, f1: 440, dur: 0.32, peak: 0.35 });
            tone({ type: 'sine', f0: 330, f1: 660, dur: 0.32, peak: 0.18 });
            break;
          case 'heal': // chime
            tone({ type: 'sine', f0: 660, f1: 990, dur: 0.22, peak: 0.3 });
            setTimeout(() => tone({ type: 'sine', f0: 990, f1: 1320, dur: 0.22, peak: 0.28 }), 70);
            break;
          default:
            tone({ type: 'square', f0: 500, f1: 250, dur: 0.12, peak: 0.25 });
        }
      },
      hit() {
        noise({ filter: 'lowpass', f0: 1600, f1: 200, dur: 0.12, peak: 0.45 });
        tone({ type: 'square', f0: 160, f1: 60, dur: 0.09, peak: 0.32 });
      },
      heal() {
        tone({ type: 'sine', f0: 880, f1: 1320, dur: 0.18, peak: 0.25 });
      },
      death() {
        tone({ type: 'sawtooth', f0: 440, f1: 60, dur: 0.55, peak: 0.5 });
        noise({ filter: 'lowpass', f0: 800, f1: 80, dur: 0.5, peak: 0.3 });
      },
      pickup() {
        tone({ type: 'square', f0: 660, f1: 1320, dur: 0.14, peak: 0.3 });
      },
      capture() {
        tone({ type: 'triangle', f0: 523, f1: 784, dur: 0.18, peak: 0.35 });
        setTimeout(() => tone({ type: 'triangle', f0: 784, f1: 1046, dur: 0.22, peak: 0.35 }), 90);
      },
      setMuted(m) { muted = !!m; },
      isMuted() { return muted; },
    };
  })();
  // Expose for the mute toggle.
  window.__SFX = SFX;

  function toggleMute() {
    SFX.setMuted(!SFX.isMuted());
    const btn = document.getElementById('muteBtn');
    if (btn) btn.textContent = SFX.isMuted() ? '🔇' : '🔊';
  }
  function toggleFx() {
    setFxMode(fxMode === 'high' ? 'low' : 'high');
    fitCanvas();
  }
  function wireToolbarButtons() {
    const m = document.getElementById('muteBtn');
    if (m) m.addEventListener('click', toggleMute);
    const f = document.getElementById('fxBtn');
    if (f) {
      f.addEventListener('click', toggleFx);
      f.textContent = fxMode === 'high' ? 'FX: High' : 'FX: Low';
    }
  }
  document.addEventListener('DOMContentLoaded', wireToolbarButtons);
  // Defer in case DOM is already ready, so all `let` bindings (fxMode etc.)
  // declared further down in this IIFE are initialized before we read them.
  setTimeout(wireToolbarButtons, 0);

  // FX quality mode (low/high). Declared early because fitCanvas() reads it.
  // 'low' (default) skips per-frame radial gradients, shadowBlur on the
  // boundary, twinkling stars, nebulae and pulse rings — these were the
  // cause of choppy framerates on older hardware. Toggle via the FX button
  // or press 'F'. Persisted in localStorage.
  let fxMode = (() => {
    try { return localStorage.getItem('iogame.fx') || 'low'; } catch (_) { return 'low'; }
  })();

  function setStatus(text, cls) {
    statusEl.textContent = text;
    statusEl.className = 'status ' + (cls || '');
  }

  function fitCanvas() {
    // Render at the CSS pixel size of the canvas for crisp output.
    // In low-FX mode we cap DPR at 1 — on a hi-DPI laptop the canvas would
    // otherwise be drawing 4x the pixels, which is the second-biggest perf
    // hit after the animated background.
    const rect = canvas.getBoundingClientRect();
    const dprRaw = window.devicePixelRatio || 1;
    const dpr = fxMode === 'high' ? Math.min(dprRaw, 2) : 1;
    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(rect.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener('resize', fitCanvas);
  fitCanvas();

  // Load (or prompt for) a session.
  let session = null;
  try { session = JSON.parse(sessionStorage.getItem('iog.session') || 'null'); }
  catch (e) { session = null; }

  if (!session) {
    const username = (prompt('Pick a username (or cancel to go to the editor):') || '').trim();
    if (!username) { location.href = '/student'; return; }
    session = {
      username,
      manifest: {
        characterName: 'Default',
        color: '#5dd6ff',
        size: 24,
        speed: 220,
        maxHealth: 100,
        powers: [{
          name: 'Bolt', key: 'space', cooldownMs: 600,
          cast: {
            kind: 'projectile', color: '#ffb13b',
            speed: 480, radius: 6, lifetimeMs: 2000,
            count: 1, spreadDeg: 0,
            onHit: [{ effect: 'damage', amount: 15 }],
          },
        }],
      },
    };
  }

  // --- Networking ---------------------------------------------------------

  const wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws';
  let ws;
  let myPid = null;  let world = { width: 2400, height: 1600 };
  let snapshot = { players: [], projectiles: [], areas: [], meleeFx: [] };

  function connect() {
    setStatus('connecting…');
    ws = new WebSocket(wsUrl);
    ws.addEventListener('open', () => {
      ws.send(JSON.stringify({
        type: 'join',
        payload: { username: session.username, manifest: session.manifest },
      }));
    });
    ws.addEventListener('message', (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (msg.type === 'welcome') {
        myPid = msg.pid;
        world = msg.world || world;
        setStatus('connected as ' + session.username, 'connected');
      } else if (msg.type === 'join_error') {
        setStatus('join error: ' + msg.error, 'error');
      } else if (msg.type === 'state') {
        snapshot = msg.payload;
        detectHealthChanges();
      } else if (msg.type === 'event') {
        for (const e of (msg.payload || [])) handleEvent(e);
      }
    });
    ws.addEventListener('close', () => {
      setStatus('disconnected — reconnecting…', 'error');
      myPid = null;
      setTimeout(connect, 1500);
    });
    ws.addEventListener('error', () => { /* surfaced via close */ });
  }
  connect();

  // --- Input --------------------------------------------------------------

  const keys = Object.create(null);
  const MOVE_KEYS = {
    'arrowup': 'up', 'w': 'up',
    'arrowdown': 'down', 's': 'down',
    'arrowleft': 'left', 'a': 'left',
    'arrowright': 'right', 'd': 'right',
  };

  // Mouse position (in canvas/viewport pixels) — used for aim direction.
  // Default to "looking right" so very early frames don't snap to (0,0).
  const mouse = { x: 0, y: 0, ready: false };
  canvas.addEventListener('mousemove', (ev) => {
    const rect = canvas.getBoundingClientRect();
    mouse.x = ev.clientX - rect.left;
    mouse.y = ev.clientY - rect.top;
    mouse.ready = true;
  });

  function normalizeKey(ev) {
    let k = (ev.key || '').toLowerCase();
    if (k === ' ') k = 'space';
    return k;
  }

  function powerKeysForMe() {
    if (!myPid) return [];
    const me = snapshot.players.find(p => p.pid === myPid);
    if (!me) return [];
    return (me.powers || []).map(p => p.key);
  }

  function iAmEliminated() {
    if (!myPid || !snapshot.players) return false;
    const me = snapshot.players.find(p => p.pid === myPid);
    return !!(me && me.eliminated);
  }

  window.addEventListener('keydown', (ev) => {
    const k = normalizeKey(ev);
    const isMove = !!MOVE_KEYS[k];
    const isPower = powerKeysForMe().includes(k);
    const isSprint = (k === 'shift');
    const isRoll = (k === 'c');
    if (isMove || isPower || isSprint || isRoll) ev.preventDefault();
    if (keys[k]) return;
    keys[k] = true;
    if (iAmEliminated()) return;  // spectator: ignore game inputs
    if (isPower && ws && ws.readyState === 1) {
      ws.send(JSON.stringify({ type: 'fire', payload: { key: k } }));
      flashHotbarSlot(k);
      // Also trigger attack-sprite animation locally for our own player.
      const a = (playerAnim[myPid] = playerAnim[myPid] || {state:'idle',frame:0,lastT:0,lastDx:0,lastDy:0});
      a.attackUntil = performance.now() + 260;
    }
    if (isRoll && ws && ws.readyState === 1) {
      ws.send(JSON.stringify({ type: 'roll' }));
    }
    if (k === 'm') toggleMute();
    if (k === 'f') toggleFx();
  });
  window.addEventListener('keyup', (ev) => {
    const k = normalizeKey(ev);
    keys[k] = false;
  });

  setInterval(() => {
    if (!ws || ws.readyState !== 1 || !myPid) return;
    if (iAmEliminated()) {
      // Spectator: send zero input so the server stops moving us.
      try { ws.send(JSON.stringify({ type: 'input', payload: { mx: 0, my: 0 } })); } catch (_) {}
      return;
    }
    let mx = 0, my = 0;
    for (const k in keys) {
      if (!keys[k]) continue;
      const dir = MOVE_KEYS[k];
      if (dir === 'up') my -= 1;
      else if (dir === 'down') my += 1;
      else if (dir === 'left') mx -= 1;
      else if (dir === 'right') mx += 1;
    }
    // Aim from mouse position relative to my player on screen.
    let ax = null, ay = null;
    if (mouse.ready) {
      const me = snapshot.players.find(p => p.pid === myPid);
      if (me) {
        const off = cameraOffset();
        const sx = me.x + off.ox;
        const sy = me.y + off.oy;
        const dx = mouse.x - sx;
        const dy = mouse.y - sy;
        const len = Math.hypot(dx, dy);
        if (len > 1) { ax = dx / len; ay = dy / len; }
      }
    }
    ws.send(JSON.stringify({
      type: 'input',
      payload: { mx, my, ax, ay, sprint: !!keys['shift'] },
    }));
  }, 1000 / 30);

  // --- Camera + Rendering -------------------------------------------------

  function viewportSize() {
    const rect = canvas.getBoundingClientRect();
    return { w: rect.width, h: rect.height };
  }

  function cameraOffset() {
    const me = snapshot.players.find(p => p.pid === myPid);
    const { w, h } = viewportSize();
    let cx, cy;
    if (me) { cx = me.x; cy = me.y; }
    else { cx = world.width / 2; cy = world.height / 2; }
    // Center the camera, then clamp so we don't show beyond the world.
    let ox = w / 2 - cx;
    let oy = h / 2 - cy;
    // Only clamp if the world is bigger than the viewport in that axis.
    if (world.width >= w) {
      ox = Math.min(0, ox);
      ox = Math.max(w - world.width, ox);
    } else {
      ox = (w - world.width) / 2;
    }
    if (world.height >= h) {
      oy = Math.min(0, oy);
      oy = Math.max(h - world.height, oy);
    } else {
      oy = (h - world.height) / 2;
    }
    return { ox, oy };
  }

  // FX quality. fxMode is declared earlier so fitCanvas() can read it.
  // setFxMode lives here next to the cache builders it depends on.
  function setFxMode(m) {
    fxMode = m;
    try { localStorage.setItem('iogame.fx', m); } catch (_) {}
    rebuildBgCaches();
    const btn = document.getElementById('fxBtn');
    if (btn) btn.textContent = m === 'high' ? 'FX: High' : 'FX: Low';
  }

  // Star field. In low mode this is rendered ONCE to an offscreen canvas
  // (3200x2200) and blitted with parallax — a single drawImage per frame
  // instead of 380 arc() calls.
  const stars = (() => {
    const out = [];
    let s = 0x9e3779b1;
    function rnd() { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; }
    for (let i = 0; i < 220; i++) {
      out.push({
        x: rnd() * 3200, y: rnd() * 2200,
        r: rnd() * 1.6 + 0.3,
        a: rnd() * 0.6 + 0.2,
        ph: rnd() * Math.PI * 2,
        sp: 0.4 + rnd() * 1.2,
      });
    }
    return out;
  })();

  // Optional background image: drop a file at static/background.png and it
  // will be drawn stretched to the arena, with a dark wash overlay so the
  // characters always read clearly on top.
  const bgImage = (() => {
    const img = new Image();
    img.src = '/static/background.png';
    img.onload = () => rebuildBgCaches();
    img.onerror = () => { img._failed = true; rebuildBgCaches(); };
    return img;
  })();

  // High-FX-only nebulae.
  const nebulae = [
    { x: 0.20, y: 0.30, r: 380, c: 'rgba(93, 214, 255, 0.10)', sp: 0.07 },
    { x: 0.75, y: 0.20, r: 460, c: 'rgba(255, 100, 180, 0.08)', sp: 0.05 },
    { x: 0.55, y: 0.75, r: 520, c: 'rgba(255, 177, 59, 0.09)', sp: 0.06 },
    { x: 0.10, y: 0.85, r: 320, c: 'rgba(160, 110, 255, 0.10)', sp: 0.09 },
  ];

  // -------- Pre-rendered background caches --------
  // arenaCache: world-sized offscreen canvas with floor + bg image + grid +
  //   boundary glow baked in. Drawn with one drawImage per frame.
  // starCache: 3200x2200 offscreen canvas with all stars.
  // vignetteCache: viewport-sized radial gradient backdrop.
  let arenaCache = null;
  let starCache = null;
  let vignetteCache = null;
  let vignetteCacheSize = { w: 0, h: 0 };

  function rebuildBgCaches() {
    // --- arena layer (world.width x world.height) ---
    arenaCache = document.createElement('canvas');
    arenaCache.width = world.width;
    arenaCache.height = world.height;
    const a = arenaCache.getContext('2d');
    a.fillStyle = 'rgba(14, 18, 38, 0.92)';
    a.fillRect(0, 0, world.width, world.height);
    if (bgImage && !bgImage._failed && bgImage.complete && bgImage.naturalWidth > 0) {
      a.globalAlpha = 0.72;
      a.drawImage(bgImage, 0, 0, world.width, world.height);
      a.globalAlpha = 1;
      a.fillStyle = 'rgba(8, 10, 24, 0.42)';
      a.fillRect(0, 0, world.width, world.height);
    }
    // grid
    a.strokeStyle = 'rgba(255,255,255,0.05)';
    a.lineWidth = 1;
    const step = 80;
    for (let x = 0; x <= world.width; x += step) {
      a.beginPath(); a.moveTo(x + 0.5, 0); a.lineTo(x + 0.5, world.height); a.stroke();
    }
    for (let y = 0; y <= world.height; y += step) {
      a.beginPath(); a.moveTo(0, y + 0.5); a.lineTo(world.width, y + 0.5); a.stroke();
    }
    // boundary (no shadowBlur — baked thicker stroke instead)
    a.strokeStyle = 'rgba(255, 177, 59, 0.95)';
    a.lineWidth = 4;
    a.strokeRect(2, 2, world.width - 4, world.height - 4);
    a.strokeStyle = 'rgba(255, 177, 59, 0.35)';
    a.lineWidth = 8;
    a.strokeRect(2, 2, world.width - 4, world.height - 4);

    // --- star layer (3200x2200, fixed) ---
    starCache = document.createElement('canvas');
    starCache.width = 3200;
    starCache.height = 2200;
    const sc = starCache.getContext('2d');
    sc.fillStyle = '#ffffff';
    for (const s of stars) {
      sc.globalAlpha = s.a;
      sc.beginPath(); sc.arc(s.x, s.y, s.r, 0, Math.PI * 2); sc.fill();
    }
    sc.globalAlpha = 1;

    vignetteCache = null; // force rebuild on next draw
  }

  function ensureVignette(w, h) {
    if (vignetteCache && vignetteCacheSize.w === w && vignetteCacheSize.h === h) return;
    vignetteCache = document.createElement('canvas');
    vignetteCache.width = w;
    vignetteCache.height = h;
    const v = vignetteCache.getContext('2d');
    const g = v.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.2,
                                     w / 2, h / 2, Math.max(w, h) * 0.8);
    g.addColorStop(0, '#13162a');
    g.addColorStop(1, '#03040a');
    v.fillStyle = g;
    v.fillRect(0, 0, w, h);
    vignetteCacheSize = { w, h };
  }

  // ----- Sprite cache + per-player animation state -----
  const spriteCache = Object.create(null); // dataURI -> HTMLImageElement
  const playerAnim = Object.create(null);  // pid -> {state, frame, lastT, lastX, lastY, attackUntil, hurtUntil}
  function getSprite(uri) {
    let img = spriteCache[uri];
    if (!img) {
      img = new Image();
      img.src = uri;
      spriteCache[uri] = img;
    }
    return img.complete && img.naturalWidth > 0 ? img : null;
  }
  function pickAnimState(p, anim, now) {
    const sprites = p.sprites || {};
    // Trigger transient states from events handled elsewhere.
    if (anim.hurtUntil && now < anim.hurtUntil && sprites.hurt) return 'hurt';
    if (anim.attackUntil && now < anim.attackUntil && sprites.attack) return 'attack';
    const moving = (anim.lastDx * anim.lastDx + anim.lastDy * anim.lastDy) > 4;
    if (moving && sprites.walk) return 'walk';
    if (sprites.idle) return 'idle';
    if (sprites.walk) return 'walk';
    return null;
  }

  function drawBackground(ox, oy) {
    const { w, h } = viewportSize();
    if (!arenaCache) rebuildBgCaches();
    ensureVignette(w, h);
    // 1) Vignette (cached, single blit).
    ctx.drawImage(vignetteCache, 0, 0);
    // 2) Star field at parallax (cached, single blit).
    ctx.drawImage(starCache, ox * 0.3, oy * 0.3);
    // 3) Arena floor + bg image + grid + boundary (cached, single blit).
    ctx.drawImage(arenaCache, ox, oy);
    // 4) High-FX extras: nebulae + pulse rings.
    if (fxMode === 'high') {
      const tNow = performance.now() / 1000;
      ctx.save();
      ctx.beginPath();
      ctx.rect(ox, oy, world.width, world.height);
      ctx.clip();
      ctx.globalCompositeOperation = 'lighter';
      for (const n of nebulae) {
        const dx = Math.cos(tNow * n.sp) * 80;
        const dy = Math.sin(tNow * n.sp * 1.3) * 60;
        const cx = ox + n.x * world.width + dx;
        const cy = oy + n.y * world.height + dy;
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, n.r);
        g.addColorStop(0, n.c);
        g.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g;
        ctx.fillRect(cx - n.r, cy - n.r, n.r * 2, n.r * 2);
      }
      ctx.globalCompositeOperation = 'source-over';
      const ccx = ox + world.width / 2, ccy = oy + world.height / 2;
      const maxR = Math.hypot(world.width, world.height) / 2;
      for (let i = 0; i < 3; i++) {
        const phase = (tNow * 0.18 + i / 3) % 1;
        const rr = phase * maxR;
        ctx.strokeStyle = `rgba(255, 177, 59, ${(1 - phase) * 0.10})`;
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(ccx, ccy, rr, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.restore();
    }
  }

  function drawAreas(ox, oy) {
    for (const a of snapshot.areas || []) {
      ctx.fillStyle = a.color;
      ctx.globalAlpha = 0.18;
      ctx.beginPath(); ctx.arc(ox + a.x, oy + a.y, a.radius, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = 0.8;
      ctx.strokeStyle = a.color;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(ox + a.x, oy + a.y, a.radius, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  function drawMeleeFx(ox, oy) {
    for (const m of snapshot.meleeFx || []) {
      const a = Math.atan2(m.facingY, m.facingX);
      const half = (m.arcDeg * Math.PI / 180) / 2;
      ctx.fillStyle = m.color;
      ctx.globalAlpha = 0.35;
      ctx.beginPath();
      ctx.moveTo(ox + m.x, oy + m.y);
      ctx.arc(ox + m.x, oy + m.y, m.range, a - half, a + half);
      ctx.closePath();
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }

  function drawProjectiles(ox, oy) {
    const high = (fxMode === 'high');
    for (const pr of snapshot.projectiles || []) {
      if (high) {
        // True glow (expensive): shadowBlur.
        ctx.save();
        ctx.shadowColor = pr.color;
        ctx.shadowBlur = 14;
        ctx.fillStyle = pr.color;
        ctx.beginPath(); ctx.arc(ox + pr.x, oy + pr.y, pr.radius, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      } else {
        // Cheap glow: translucent halo + opaque core.
        ctx.globalAlpha = 0.35;
        ctx.fillStyle = pr.color;
        ctx.beginPath(); ctx.arc(ox + pr.x, oy + pr.y, pr.radius * 1.9, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
        ctx.fillStyle = pr.color;
        ctx.beginPath(); ctx.arc(ox + pr.x, oy + pr.y, pr.radius, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.beginPath(); ctx.arc(ox + pr.x, oy + pr.y, pr.radius * 0.45, 0, Math.PI * 2); ctx.fill();
    }
  }

  function drawPlayers(ox, oy) {
    const now = performance.now();
    const RENDER_SCALE = 1.8; // visual-only; hitboxes stay server-authoritative
    for (const p of snapshot.players || []) {
      // Hide dead and eliminated players entirely.
      if (!p.alive || p.eliminated) continue;
      const r = (p.size / 2) * RENDER_SCALE;
      const px = ox + p.x, py = oy + p.y;
      ctx.globalAlpha = 1;

      // Shadow disc on the floor.
      ctx.fillStyle = 'rgba(0,0,0,0.35)';
      ctx.beginPath(); ctx.ellipse(px, py + r * 0.55, r * 0.85, r * 0.32, 0, 0, Math.PI * 2); ctx.fill();

      // Team ring (only in team / ctf modes).
      if (p.team === 1 || p.team === 2) {
        ctx.strokeStyle = p.team === 1 ? '#5dd6ff' : '#ff7a7a';
        ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(px, py, r + 9, 0, Math.PI * 2); ctx.stroke();
      }
      // Status auras.
      if (p.status && p.status.shielded) {
        if (fxMode === 'high') {
          ctx.save();
          ctx.shadowColor = '#a0e6ff';
          ctx.shadowBlur = 12;
          ctx.strokeStyle = 'rgba(160,230,255,0.9)';
          ctx.lineWidth = 3;
          ctx.beginPath(); ctx.arc(px, py, r + 6, 0, Math.PI * 2); ctx.stroke();
          ctx.restore();
        } else {
          ctx.strokeStyle = 'rgba(160,230,255,0.9)';
          ctx.lineWidth = 3;
          ctx.beginPath(); ctx.arc(px, py, r + 6, 0, Math.PI * 2); ctx.stroke();
          ctx.strokeStyle = 'rgba(160,230,255,0.35)';
          ctx.lineWidth = 6;
          ctx.beginPath(); ctx.arc(px, py, r + 8, 0, Math.PI * 2); ctx.stroke();
        }
      }
      if (p.status && p.status.invulnerable) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.arc(px, py, r + 3, 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([]);
      }

      // Body — sprite if provided, otherwise a radial-gradient disc.
      const anim = (playerAnim[p.pid] = playerAnim[p.pid] || {
        state: 'idle', frame: 0, lastT: now, lastDx: 0, lastDy: 0,
      });
      const dx = p.x - (anim.lastX != null ? anim.lastX : p.x);
      const dy = p.y - (anim.lastY != null ? anim.lastY : p.y);
      anim.lastDx = dx; anim.lastDy = dy;
      anim.lastX = p.x; anim.lastY = p.y;
      let drewSprite = false;
      if (p.sprites) {
        const state = pickAnimState(p, anim, now);
        const frames = state ? p.sprites[state] : null;
        if (frames && frames.length) {
          // Advance frame at ~6 fps.
          if (anim.state !== state) { anim.state = state; anim.frame = 0; anim.lastT = now; }
          if (now - anim.lastT > 160) {
            anim.lastT = now;
            anim.frame = (anim.frame + 1) % frames.length;
          }
          const img = getSprite(frames[anim.frame % frames.length]);
          if (img) {
            const draw = r * 2.4; // sprite slightly larger than hitbox
            ctx.save();
            // Flip horizontally based on facing.
            if (p.facingX < -0.05) {
              ctx.translate(px, py); ctx.scale(-1, 1);
              ctx.drawImage(img, -draw / 2, -draw / 2, draw, draw);
            } else {
              ctx.drawImage(img, px - draw / 2, py - draw / 2, draw, draw);
            }
            ctx.restore();
            drewSprite = true;
          }
        }
      }
      if (!drewSprite) {
        if (fxMode === 'high') {
          const bg = ctx.createRadialGradient(px - r * 0.35, py - r * 0.45, r * 0.1, px, py, r);
          bg.addColorStop(0, lighten(p.color, 0.5));
          bg.addColorStop(0.6, p.color);
          bg.addColorStop(1, darken(p.color, 0.4));
          ctx.save();
          if (p.pid === myPid) {
            ctx.shadowColor = p.color;
            ctx.shadowBlur = 16;
          }
          ctx.fillStyle = bg;
          ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill();
          ctx.restore();
        } else {
          // Flat fill with a small inner highlight — no per-frame gradient.
          ctx.fillStyle = p.color;
          ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = 'rgba(255,255,255,0.18)';
          ctx.beginPath(); ctx.arc(px - r * 0.35, py - r * 0.4, r * 0.45, 0, Math.PI * 2); ctx.fill();
          if (p.pid === myPid) {
            // Cheap "this is you" highlight: extra outline ring.
            ctx.strokeStyle = lighten(p.color, 0.5);
            ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(px, py, r + 2, 0, Math.PI * 2); ctx.stroke();
          }
        }

        // Outline ring.
        ctx.strokeStyle = 'rgba(255,255,255,0.18)';
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.stroke();
      }

      // Hit flash overlay.
      if (flashes[p.pid] && now < flashes[p.pid]) {
        const k = (flashes[p.pid] - now) / 260;
        if (fxMode === 'high') {
          ctx.save();
          ctx.shadowColor = '#ff3030';
          ctx.shadowBlur = 18 * k;
          ctx.fillStyle = `rgba(255, 80, 80, ${0.65 * k})`;
          ctx.beginPath(); ctx.arc(px, py, r * 1.05, 0, Math.PI * 2); ctx.fill();
          ctx.restore();
        } else {
          ctx.fillStyle = `rgba(255, 80, 80, ${0.65 * k})`;
          ctx.beginPath(); ctx.arc(px, py, r * 1.05, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = `rgba(255, 80, 80, ${0.25 * k})`;
          ctx.beginPath(); ctx.arc(px, py, r * 1.5, 0, Math.PI * 2); ctx.fill();
        }
      } else if (flashes[p.pid]) { delete flashes[p.pid]; }

      // Sprint dust (cheap).
      if (p.sprinting && p.alive) {
        ctx.fillStyle = 'rgba(255,255,255,0.18)';
        for (let i = 0; i < 2; i++) {
          const ang = Math.atan2(-p.facingY, -p.facingX) + (Math.random() - 0.5) * 0.6;
          const d = r * (0.9 + Math.random() * 0.5);
          ctx.beginPath();
          ctx.arc(px + Math.cos(ang) * d, py + Math.sin(ang) * d, 1.5 + Math.random(), 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Slowed/stunned tint.
      if (p.status && (p.status.slowed || p.status.stunned)) {
        ctx.fillStyle = p.status.stunned ? 'rgba(255,210,74,0.33)' : 'rgba(93,214,255,0.33)';
        ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill();
      }
      // Burning marker.
      if (p.status && p.status.burning) {
        ctx.fillStyle = '#ff7a00';
        for (let i = 0; i < 3; i++) {
          const ang = Math.random() * Math.PI * 2;
          ctx.beginPath();
          ctx.arc(px + Math.cos(ang) * r * 0.7, py + Math.sin(ang) * r * 0.7, 2, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      // Facing tick — the "barrel" of a tank.
      ctx.strokeStyle = 'rgba(255,255,255,0.85)';
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(px + p.facingX * r * 0.4, py + p.facingY * r * 0.4);
      ctx.lineTo(px + p.facingX * (r + 10), py + p.facingY * (r + 10));
      ctx.stroke();
      ctx.lineCap = 'butt';

      // Carrying-flag indicator.
      if (p.hasFlag) {
        const fc = p.hasFlag === 1 ? '#5dd6ff' : '#ff7a7a';
        ctx.fillStyle = fc;
        ctx.strokeStyle = '#e7e9f3';
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(px + r + 4, py - r - 12); ctx.lineTo(px + r + 4, py - r + 4); ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(px + r + 4, py - r - 12);
        ctx.lineTo(px + r + 18, py - r - 8);
        ctx.lineTo(px + r + 4, py - r - 4);
        ctx.closePath(); ctx.fill();
      }

      ctx.globalAlpha = 1;
      // Name label with subtle shadow.
      ctx.font = '600 12px -apple-system,BlinkMacSystemFont,sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      const label = p.username + (p.pid === myPid ? ' (you)' : '');
      ctx.fillText(label, px + 1, py - r - 13);
      ctx.fillStyle = '#e7e9f3';
      ctx.fillText(label, px, py - r - 14);

      // HP bar (above name).
      const w = Math.max(40, r * 2.4);
      const hpRatio = Math.max(0, p.health) / Math.max(1, p.maxHealth);
      ctx.fillStyle = 'rgba(0,0,0,0.55)';
      ctx.fillRect(px - w / 2 - 1, py - r - 28, w + 2, 6);
      ctx.fillStyle = hpRatio > 0.4 ? '#51d88a' : (hpRatio > 0.2 ? '#ffb13b' : '#ff5a5a');
      ctx.fillRect(px - w / 2, py - r - 27, w * hpRatio, 4);
    }
  }

  function lighten(hex, amt) { return mixHex(hex, '#ffffff', amt); }
  function darken(hex, amt) { return mixHex(hex, '#000000', amt); }
  function mixHex(a, b, t) {
    const pa = parseHex(a), pb = parseHex(b);
    const r = clamp255(Math.round(pa[0] + (pb[0] - pa[0]) * t));
    const g = clamp255(Math.round(pa[1] + (pb[1] - pa[1]) * t));
    const bl = clamp255(Math.round(pa[2] + (pb[2] - pa[2]) * t));
    return `rgb(${r},${g},${bl})`;
  }
  function clamp255(n) { if (!isFinite(n)) return 128; return Math.max(0, Math.min(255, n | 0)); }
  function parseHex(c) {
    if (typeof c !== 'string') return [128, 128, 128];
    if (c[0] === '#') c = c.slice(1);
    if (c.length === 3) c = c.split('').map(x => x + x).join('');
    if (c.length !== 6) return [128, 128, 128];
    const r = parseInt(c.slice(0, 2), 16);
    const g = parseInt(c.slice(2, 4), 16);
    const b = parseInt(c.slice(4, 6), 16);
    if (!isFinite(r) || !isFinite(g) || !isFinite(b)) return [128, 128, 128];
    return [r, g, b];
  }

  function drawFloaters(ox, oy) {
    const now = performance.now();
    for (let i = floaters.length - 1; i >= 0; i--) {
      const f = floaters[i];
      const age = now - f.born;
      if (age >= f.ttl) { floaters.splice(i, 1); continue; }
      const t = age / f.ttl;
      ctx.globalAlpha = 1 - t;
      ctx.font = '700 16px -apple-system,BlinkMacSystemFont,sans-serif';
      ctx.textAlign = 'center';
      const x = ox + f.x + (f.dx || 0) * t;
      const y = oy + f.y + (f.vy || -32) * (age / 1000);
      ctx.fillStyle = 'rgba(0,0,0,0.7)';
      ctx.fillText(f.text, x + 1, y + 1);
      ctx.fillStyle = f.color;
      ctx.fillText(f.text, x, y);
    }
    ctx.globalAlpha = 1;
  }

  function drawRipples(ox, oy) {
    const now = performance.now();
    for (let i = ripples.length - 1; i >= 0; i--) {
      const r = ripples[i];
      const age = now - r.born;
      if (age >= r.ttl) { ripples.splice(i, 1); continue; }
      const t = age / r.ttl;
      const cx = ox + r.x, cy = oy + r.y;
      const rad = r.r0 + (r.r1 - r.r0) * t;
      ctx.globalAlpha = (1 - t) * 0.9;
      ctx.strokeStyle = r.color;
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.arc(cx, cy, rad, 0, Math.PI * 2);
      ctx.stroke();
      // Inner echo ring for extra punch.
      ctx.globalAlpha = (1 - t) * 0.5;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(cx, cy, rad * 0.6, 0, Math.PI * 2);
      ctx.stroke();
      if (r.label) {
        ctx.globalAlpha = 1 - t;
        ctx.fillStyle = r.color;
        ctx.font = 'bold 12px system-ui';
        ctx.textAlign = 'center';
        ctx.fillText(r.label, cx, cy - rad - 6 - t * 18);
      }
    }
    ctx.globalAlpha = 1;
    ctx.textAlign = 'start';
  }

  function drawMinimap() {
    const { w, h } = viewportSize();
    const mw = 160, mh = mw * (world.height / world.width);
    const x0 = w - mw - 12, y0 = 12;
    ctx.globalAlpha = 0.85;
    ctx.fillStyle = '#0a0c14';
    ctx.fillRect(x0, y0, mw, mh);
    ctx.strokeStyle = '#ffb13b';
    ctx.lineWidth = 1;
    ctx.strokeRect(x0 + 0.5, y0 + 0.5, mw - 1, mh - 1);
    for (const p of snapshot.players || []) {
      ctx.fillStyle = p.color;
      const mx = x0 + (p.x / world.width) * mw;
      const my = y0 + (p.y / world.height) * mh;
      ctx.beginPath();
      ctx.arc(mx, my, p.pid === myPid ? 3 : 2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // --- Event stream + HUD overlays ---------------------------------------

  function detectHealthChanges() {
    const now = performance.now();
    for (const p of snapshot.players || []) {
      const prev = lastHealth[p.pid];
      if (prev !== undefined && p.health < prev - 0.01) {
        const dmg = Math.round(prev - p.health);
        floaters.push({
          x: p.x, y: p.y - p.size / 2 - 4,
          text: '-' + dmg, color: '#ff7a7a',
          born: now, ttl: 900,
          vy: -32, // px/s upward
          dx: (Math.random() - 0.5) * 20,
        });
        flashes[p.pid] = now + 260;
        const a = (playerAnim[p.pid] = playerAnim[p.pid] || {state:'idle',frame:0,lastT:0,lastDx:0,lastDy:0});
        a.hurtUntil = now + 260;
        SFX.hit();
      } else if (prev !== undefined && p.health > prev + 0.01) {
        const heal = Math.round(p.health - prev);
        floaters.push({
          x: p.x, y: p.y - p.size / 2 - 4,
          text: '+' + heal, color: '#7affad',
          born: now, ttl: 900, vy: -28, dx: (Math.random() - 0.5) * 20,
        });
        SFX.heal();
      }
      lastHealth[p.pid] = p.health;
    }
    // Drop tracking for players that left.
    const ids = new Set((snapshot.players || []).map(p => p.pid));
    for (const id in lastHealth) if (!ids.has(id)) delete lastHealth[id];
  }

  function handleEvent(e) {
    const playersById = Object.create(null);
    for (const p of snapshot.players || []) playersById[p.pid] = p;
    if (e.kind === 'death') {
      const victim = playersById[e.pid];
      const killer = playersById[e.by];
      addKillRow(killer, victim);
      SFX.death();
      if (e.pid === myPid) {
        if (e.eliminated) {
          showBanner('You\'re out — spectating until next round', 4000);
        } else if (typeof e.livesRemaining === 'number') {
          showBanner(`You died — ${e.livesRemaining} ${e.livesRemaining === 1 ? 'life' : 'lives'} left`, 1600);
        }
      }
    } else if (e.kind === 'flag_pickup') {
      const carrier = playersById[e.pid];
      if (carrier) showBanner(`${carrier.username} grabbed the ${e.team === 1 ? 'Blue' : 'Red'} flag!`, 1500);
      SFX.pickup();
    } else if (e.kind === 'flag_capture') {
      const scorer = playersById[e.pid];
      if (scorer) showBanner(`${e.team === 1 ? 'Blue' : 'Red'} captured! (${e.score})`, 1800);
      SFX.capture();
    } else if (e.kind === 'roll') {
      const p = playersById[e.pid];
      if (p) ripples.push({
        x: p.x, y: p.y, color: p.color,
        born: performance.now(), ttl: 350,
        r0: p.size / 2, r1: p.size,
      });
    } else if (e.kind === 'fire') {
      // Universal cast telegraph: a colored ring at the caster's feet so
      // every power has SOME visible feedback, even non-projectile ones
      // like heal / shield / dash.
      const p = playersById[e.pid];
      if (p) ripples.push({
        x: p.x, y: p.y, color: p.color,
        born: performance.now(), ttl: 600,
        r0: p.size * 0.4, r1: p.size * 2.2,
        label: e.power || '',
      });
      SFX.cast(e.castKind);
    } else if (e.kind === 'round_start') {
      showBanner(`Round #${e.id} — fight!`, 1400);
    } else if (e.kind === 'round_end') {
      showBanner('Round over', 1800);
    }
  }

  function addKillRow(killer, victim) {
    if (!victim) return;
    const row = document.createElement('div');
    row.className = 'kill-row';
    if (killer && killer.pid !== victim.pid) {
      row.innerHTML =
        `<span class="kf-name" style="color:${killer.color}">${escapeHtml(killer.username)}</span>` +
        `<span class="kf-icon">⚔</span>` +
        `<span class="kf-name" style="color:${victim.color}">${escapeHtml(victim.username)}</span>`;
    } else {
      row.innerHTML =
        `<span class="kf-name" style="color:${victim.color}">${escapeHtml(victim.username)}</span>` +
        `<span class="kf-icon">☠</span>`;
    }
    killFeedEl.appendChild(row);
    setTimeout(() => row.remove(), 5200);
    // Cap at ~6 rows.
    while (killFeedEl.children.length > 6) killFeedEl.firstChild.remove();
  }

  let bannerTimer = 0;
  function showBanner(text, ms) {
    bannerEl.textContent = text;
    bannerEl.classList.add('show');
    clearTimeout(bannerTimer);
    bannerTimer = setTimeout(() => bannerEl.classList.remove('show'), ms || 1500);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\'':'&#39;','"':'&quot;'}[c]));
  }

  // Hotbar DOM rebuild (only when power list changes).
  let hotbarSig = '';
  function updateHotbar(me) {
    const sig = me ? me.powers.map(p => p.key + ':' + p.name + ':' + p.cast.color).join('|') : '';
    if (sig !== hotbarSig) {
      hotbarSig = sig;
      hotbarEl.innerHTML = '';
      if (me) {
        for (const pw of me.powers) {
          const slot = document.createElement('div');
          slot.className = 'hb-slot';
          slot.dataset.key = pw.key;
          slot.innerHTML =
            `<span class="hb-color" style="color:${pw.cast.color};background:${pw.cast.color}"></span>` +
            `<span class="hb-key">${pw.key === 'space' ? '␣' : escapeHtml(pw.key.toUpperCase())}</span>` +
            `<span class="hb-name">${escapeHtml(pw.name)}</span>` +
            `<div class="hb-cd-mask" style="height:0%"></div>`;
          hotbarEl.appendChild(slot);
        }
      }
    }
    // Cooldown overlay updates every frame from snapshot. The server doesn't
    // expose remaining cooldowns directly, so we estimate from a local map.
    if (!me) return;
    const slots = hotbarEl.querySelectorAll('.hb-slot');
    slots.forEach(slot => {
      const k = slot.dataset.key;
      const due = cooldownDueAt[k] || 0;
      const totalMs = cooldownTotal[k] || 1;
      const remain = Math.max(0, due - performance.now());
      const ratio = Math.min(1, remain / totalMs);
      slot.querySelector('.hb-cd-mask').style.height = (ratio * 100) + '%';
    });
  }
  // Estimated local cooldowns (server is authoritative; this is purely visual).
  const cooldownDueAt = Object.create(null);
  const cooldownTotal = Object.create(null);
  function flashHotbarSlot(k) {
    const me = (snapshot.players || []).find(p => p.pid === myPid);
    if (!me) return;
    const pw = (me.powers || []).find(p => p.key === k);
    if (!pw) return;
    cooldownDueAt[k] = performance.now() + pw.cooldownMs;
    cooldownTotal[k] = pw.cooldownMs;
    const slot = hotbarEl.querySelector(`.hb-slot[data-key="${CSS.escape(k)}"]`);
    if (slot) {
      slot.classList.add('fired');
      setTimeout(() => slot.classList.remove('fired'), 100);
    }
  }

  function updatePlayerCard(me) {
    if (!me) { playerCardEl.classList.add('hidden'); return; }
    playerCardEl.classList.remove('hidden');
    pcPortrait.style.background = me.color;
    pcPortrait.style.color = me.color;
    pcName.textContent = me.username;
    pcChar.textContent = me.characterName;
    const hpRatio = Math.max(0, me.health) / Math.max(1, me.maxHealth);
    hpFill.style.width = (hpRatio * 100) + '%';
    hpFill.classList.toggle('warn', hpRatio <= 0.4 && hpRatio > 0.2);
    hpFill.classList.toggle('crit', hpRatio <= 0.2);
    hpLabel.textContent = `${Math.max(0, Math.round(me.health))} / ${me.maxHealth}`;
    const stam = me.stamina != null ? me.stamina : 100;
    stamFill.style.width = stam + '%';
  }

  function drawMatchHud() {
    const m = snapshot.match;
    let hud = document.getElementById('matchHud');
    if (!hud) {
      hud = document.createElement('div');
      hud.id = 'matchHud';
      hud.className = 'match-hud';
      const wrap = document.getElementById('stage') || document.querySelector('.arena-wrap') || canvas.parentNode || document.body;
      if (getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';
      wrap.appendChild(hud);
    }
    if (!m) { hud.textContent = ''; return; }
    const modeLabel = ({ ffa: 'Solo', team: 'Teams', ctf: 'Capture the Flag' })[m.mode] || '';
    const ts = m.teamScores || {};
    const teamSuffix = (m.mode === 'team' || m.mode === 'ctf')
      ? `  ·  Blue ${ts['1'] ?? 0} – Red ${ts['2'] ?? 0}` : '';
    if (m.status === 'running') {
      const s = Math.floor(m.remaining);
      hud.textContent = `${modeLabel}  ·  Round #${m.id}  ·  ${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}${teamSuffix}`;
      hud.style.color = 'var(--text)';
    } else if (m.status === 'ended') {
      let result = 'Round over';
      if (m.mode === 'ctf' || m.mode === 'team') {
        const a = ts['1'] ?? 0, b = ts['2'] ?? 0;
        const winner = a === b ? 'Tie' : (a > b ? 'Blue team wins' : 'Red team wins');
        result = `Round over — ${winner} (${a}–${b})`;
      } else {
        const w = (m.lastScoreboard && m.lastScoreboard[0]) || null;
        if (w) result = `Round over — winner: ${w.username} (${w.score} pts)`;
      }
      hud.textContent = result;
      hud.style.color = 'var(--accent)';
    } else {
      hud.textContent = 'Lobby — waiting for teacher to start a round';
      hud.style.color = 'var(--muted)';
    }
  }

  function drawCtf(ox, oy) {
    if (snapshot.mode !== 'ctf') return;
    const zones = snapshot.captureZones || [];
    const t = performance.now() / 1000;
    for (const z of zones) {
      const color = z.team === 1 ? '#5dd6ff' : '#ff7a7a';
      const cx = ox + z.x, cy = oy + z.y;
      const r = z.radius || 90;
      const active = z.carrierPid && z.progress > 0;
      // Pulse intensity when an enemy carrier is scoring inside.
      const pulse = active ? 0.55 + 0.35 * Math.sin(t * 6) : 0.35;
      ctx.save();
      ctx.strokeStyle = color;
      ctx.globalAlpha = pulse;
      ctx.lineWidth = active ? 4 : 3;
      ctx.setLineDash(active ? [] : [6, 6]);
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
      ctx.setLineDash([]);
      // Filled tint when active.
      if (active) {
        ctx.globalAlpha = 0.15;
        ctx.fillStyle = color;
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
        // Progress arc (clockwise from top).
        const frac = Math.min(1, (z.progress || 0) / (z.holdSeconds || 10));
        ctx.globalAlpha = 0.95;
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 5;
        ctx.beginPath();
        ctx.arc(cx, cy, r + 8, -Math.PI / 2, -Math.PI / 2 + frac * Math.PI * 2);
        ctx.stroke();
      }
      ctx.restore();
    }
    const flags = snapshot.flags || [];
    for (const f of flags) {
      const color = f.team === 1 ? '#5dd6ff' : '#ff7a7a';
      // Flag itself (a triangle on a pole).
      const fx = ox + f.x, fy = oy + f.y;
      ctx.strokeStyle = '#e7e9f3';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(fx, fy - 22); ctx.lineTo(fx, fy + 6); ctx.stroke();
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(fx, fy - 22);
      ctx.lineTo(fx + 16, fy - 16);
      ctx.lineTo(fx, fy - 10);
      ctx.closePath(); ctx.fill();
    }
  }

  function loop() {
    const me = (snapshot.players || []).find(p => p.pid === myPid);
    const { ox, oy } = cameraOffset();
    drawBackground(ox, oy);
    drawAreas(ox, oy);
    drawCtf(ox, oy);
    drawRipples(ox, oy);
    drawMeleeFx(ox, oy);
    drawProjectiles(ox, oy);
    drawPlayers(ox, oy);
    drawFloaters(ox, oy);
    drawMinimap();
    drawMatchHud();
    updatePlayerCard(me);
    updateHotbar(me);
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();
