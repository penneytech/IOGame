/* spectator.js — read-only big-screen viewer for IOGame
 * Modes:
 *   1: arena      – fit the whole world to the screen, no UI on the canvas.
 *   2: quad       – split screen into 4 follow-cams on the top 4 players.
 *   3: follow     – auto follow the current leader (most kills, then health).
 *   [ / ]         – pick a specific player to follow (overrides mode 3).
 *   H             – hide/show the keyboard hint strip.
 */
(function () {
  'use strict';

  const stage = document.getElementById('spec-stage');
  const canvas = document.getElementById('spec-canvas');
  const ctx = canvas.getContext('2d');
  const modePill = document.getElementById('spec-mode-pill');
  const helpEl = document.getElementById('spec-help');
  const statusEl = document.getElementById('spec-status');
  const countEl = document.getElementById('spec-count');
  const tickEl = document.getElementById('spec-tick');
  const boardEl = document.getElementById('spec-board');

  let world = { width: 1600, height: 1000 };
  let snapshot = { players: [], areas: [], projectiles: [], meleeFx: [], tick: 0 };
  let mode = 'arena'; // arena | quad | follow
  let pinnedPid = null; // when set, overrides mode for the focused player

  // ---- Sprite cache (shared with renderer) ----
  const spriteCache = Object.create(null);
  function getSprite(uri) {
    let img = spriteCache[uri];
    if (!img) { img = new Image(); img.src = uri; spriteCache[uri] = img; }
    return img.complete && img.naturalWidth > 0 ? img : null;
  }
  const playerAnim = Object.create(null);

  // ---- Resize ----
  function resize() {
    const r = stage.getBoundingClientRect();
    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    canvas.width = Math.floor(r.width * dpr);
    canvas.height = Math.floor(r.height * dpr);
    canvas.style.width = r.width + 'px';
    canvas.style.height = r.height + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener('resize', resize);

  // ---- WebSocket ----
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}/ws/spectator`;
    const ws = new WebSocket(url);
    ws.onopen = () => { statusEl.textContent = 'Connected'; };
    ws.onclose = () => {
      statusEl.textContent = 'Disconnected — retrying…';
      setTimeout(connect, 1500);
    };
    ws.onerror = () => { /* close handler will retry */ };
    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === 'welcome' && msg.world) {
        world = msg.world;
      } else if (msg.type === 'state' && msg.payload) {
        snapshot = msg.payload;
        updateSidebar();
      }
    };
  }

  // ---- Sidebar / scoreboard ----
  function leaderboard() {
    const ps = (snapshot.players || []).slice();
    ps.sort((a, b) =>
      (b.kills - a.kills) ||
      ((b.alive ? b.health : -1) - (a.alive ? a.health : -1)) ||
      (a.deaths - b.deaths)
    );
    return ps;
  }
  function updateSidebar() {
    const ps = leaderboard();
    countEl.textContent = ps.length;
    tickEl.textContent = snapshot.tick != null ? snapshot.tick : '—';
    // Spectators
    const watchers = document.getElementById('spec-watchers');
    if (watchers) watchers.textContent = (snapshot.spectators != null) ? snapshot.spectators : 0;
    // Match bar (mode / status / timer)
    const modeEl = document.getElementById('spec-match-mode');
    const statusBar = document.getElementById('spec-match-status');
    const timeEl = document.getElementById('spec-match-time');
    const m = snapshot.match || {};
    if (modeEl) modeEl.textContent = (snapshot.mode || m.mode || 'ffa').toUpperCase();
    if (statusBar) statusBar.textContent = (m.status || 'idle').toUpperCase();
    if (timeEl) {
      const r = m.remaining != null ? m.remaining : 0;
      const mm = Math.floor(r / 60), ss = Math.floor(r % 60);
      timeEl.textContent = (m.status === 'running')
        ? `${mm}:${ss.toString().padStart(2, '0')}`
        : '—';
    }
    // Team scores
    const teamWrap = document.getElementById('spec-team-scores');
    const ts = snapshot.teamScores || {};
    const isTeam = (snapshot.mode === 'team' || snapshot.mode === 'ctf');
    if (teamWrap) {
      teamWrap.hidden = !isTeam;
      if (isTeam) {
        document.getElementById('spec-team-blue').textContent = ts['1'] || ts[1] || 0;
        document.getElementById('spec-team-red').textContent = ts['2'] || ts[2] || 0;
      }
    }
    boardEl.innerHTML = '';
    for (let i = 0; i < ps.length; i++) {
      const p = ps[i];
      const li = document.createElement('li');
      li.className = 'spec-row' + (p.pid === pinnedPid ? ' pinned' : '');
      li.style.setProperty('--col', p.color || '#888');
      li.innerHTML = `
        <span class="rank">${i + 1}</span>
        <span class="swatch"></span>
        <span class="name">${escapeHtml(p.username || '???')}${p.eliminated ? ' <em>·OUT</em>' : (!p.alive ? ' <em>·dead</em>' : '')}</span>
        <span class="kd">${p.kills}/${p.deaths}</span>`;
      li.addEventListener('click', () => {
        pinnedPid = (pinnedPid === p.pid) ? null : p.pid;
        updateMode();
      });
      boardEl.appendChild(li);
    }
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // ---- Camera helpers ----
  function fitCamera(w, h) {
    // Returns {scale, ox, oy} to draw the whole world fit-to-viewport.
    const sx = w / world.width;
    const sy = h / world.height;
    const scale = Math.min(sx, sy) * 0.96;
    const ox = (w - world.width * scale) / 2;
    const oy = (h - world.height * scale) / 2;
    return { scale, ox, oy };
  }
  function followCamera(w, h, target, scale) {
    const s = scale || 1.0;
    const ox = w / 2 - target.x * s;
    const oy = h / 2 - target.y * s;
    return { scale: s, ox, oy };
  }

  // ---- Rendering ----
  // Optional shared background image — same file as the player view uses.
  const bgImage = (() => {
    const img = new Image();
    img.src = '/static/background.png';
    img.onerror = () => { img._failed = true; };
    return img;
  })();

  function drawBackground(camera, w, h) {
    ctx.fillStyle = '#03040a';
    ctx.fillRect(0, 0, w, h);
    // Arena floor
    const { ox, oy, scale } = camera;
    ctx.fillStyle = 'rgba(20, 24, 50, 0.85)';
    ctx.fillRect(ox, oy, world.width * scale, world.height * scale);
    // Background image (washed-out for spectator clarity).
    if (bgImage && !bgImage._failed && bgImage.complete && bgImage.naturalWidth > 0) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(ox, oy, world.width * scale, world.height * scale);
      ctx.clip();
      ctx.globalAlpha = 0.72;
      ctx.drawImage(bgImage, ox, oy, world.width * scale, world.height * scale);
      ctx.globalAlpha = 1;
      ctx.fillStyle = 'rgba(8, 10, 24, 0.42)';
      ctx.fillRect(ox, oy, world.width * scale, world.height * scale);
      ctx.restore();
    }
    // Soft grid
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    const step = 80 * scale;
    if (step >= 6) {
      for (let x = ox; x <= ox + world.width * scale; x += step) {
        ctx.beginPath(); ctx.moveTo(x, oy); ctx.lineTo(x, oy + world.height * scale); ctx.stroke();
      }
      for (let y = oy; y <= oy + world.height * scale; y += step) {
        ctx.beginPath(); ctx.moveTo(ox, y); ctx.lineTo(ox + world.width * scale, y); ctx.stroke();
      }
    }
    // Boundary
    ctx.strokeStyle = 'rgba(255, 177, 59, 0.85)';
    ctx.lineWidth = 2;
    ctx.strokeRect(ox + 1, oy + 1, world.width * scale - 2, world.height * scale - 2);
  }

  function drawScene(camera, w, h, opts) {
    opts = opts || {};
    const { ox, oy, scale } = camera;
    drawBackground(camera, w, h);

    // Areas
    for (const a of snapshot.areas || []) {
      ctx.fillStyle = a.color;
      ctx.globalAlpha = 0.18;
      ctx.beginPath();
      ctx.arc(ox + a.x * scale, oy + a.y * scale, a.radius * scale, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 0.8;
      ctx.strokeStyle = a.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(ox + a.x * scale, oy + a.y * scale, a.radius * scale, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // CTF: capture zones + flags
    if (snapshot.mode === 'ctf') {
      const tnow = performance.now() / 1000;
      for (const z of (snapshot.captureZones || [])) {
        const color = z.team === 1 ? '#5dd6ff' : '#ff7a7a';
        const cx = ox + z.x * scale, cy = oy + z.y * scale;
        const r = (z.radius || 90) * scale;
        const active = z.carrierPid && z.progress > 0;
        const pulse = active ? 0.55 + 0.35 * Math.sin(tnow * 6) : 0.35;
        ctx.save();
        ctx.strokeStyle = color;
        ctx.globalAlpha = pulse;
        ctx.lineWidth = active ? 4 : 3;
        ctx.setLineDash(active ? [] : [6, 6]);
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([]);
        if (active) {
          ctx.globalAlpha = 0.18;
          ctx.fillStyle = color;
          ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
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
      for (const f of (snapshot.flags || [])) {
        const color = f.team === 1 ? '#5dd6ff' : '#ff7a7a';
        const fx = ox + f.x * scale, fy = oy + f.y * scale;
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

    // Melee fx
    for (const m of snapshot.meleeFx || []) {
      const a = Math.atan2(m.facingY, m.facingX);
      const half = (m.arcDeg * Math.PI / 180) / 2;
      ctx.fillStyle = m.color;
      ctx.globalAlpha = 0.35;
      ctx.beginPath();
      ctx.moveTo(ox + m.x * scale, oy + m.y * scale);
      ctx.arc(ox + m.x * scale, oy + m.y * scale, m.range * scale, a - half, a + half);
      ctx.closePath();
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    // Projectiles
    for (const pr of snapshot.projectiles || []) {
      ctx.save();
      ctx.shadowColor = pr.color;
      ctx.shadowBlur = 14;
      ctx.fillStyle = pr.color;
      ctx.beginPath();
      ctx.arc(ox + pr.x * scale, oy + pr.y * scale, pr.radius * scale, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.beginPath();
      ctx.arc(ox + pr.x * scale, oy + pr.y * scale, pr.radius * 0.45 * scale, 0, Math.PI * 2);
      ctx.fill();
    }

    // Players (skip dead and eliminated — they shouldn't render anywhere)
    const now = performance.now();
    for (const p of snapshot.players || []) {
      if (!p.alive || p.eliminated) continue;
      const r = (p.size / 2) * scale * 1.8;
      const px = ox + p.x * scale;
      const py = oy + p.y * scale;
      ctx.globalAlpha = 1;

      // Highlight ring for the focused player
      if (opts.highlightPid && p.pid === opts.highlightPid) {
        ctx.strokeStyle = '#ffe066';
        ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(px, py, r + 11, 0, Math.PI * 2); ctx.stroke();
      }

      // Shadow
      ctx.fillStyle = 'rgba(0,0,0,0.35)';
      ctx.beginPath(); ctx.ellipse(px, py + r * 0.55, r * 0.85, r * 0.32, 0, 0, Math.PI * 2); ctx.fill();

      // Team ring
      if (p.team === 1 || p.team === 2) {
        ctx.strokeStyle = p.team === 1 ? '#5dd6ff' : '#ff7a7a';
        ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(px, py, r + 9, 0, Math.PI * 2); ctx.stroke();
      }
      // Shielded aura
      if (p.status && p.status.shielded) {
        ctx.save();
        ctx.shadowColor = '#a0e6ff';
        ctx.shadowBlur = 12;
        ctx.strokeStyle = 'rgba(160,230,255,0.9)';
        ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(px, py, r + 6, 0, Math.PI * 2); ctx.stroke();
        ctx.restore();
      }

      // Body — sprite or coloured disc
      let drewSprite = false;
      const anim = (playerAnim[p.pid] = playerAnim[p.pid] || {
        state: 'idle', frame: 0, lastT: now, lastDx: 0, lastDy: 0,
      });
      const dx = p.x - (anim.lastX != null ? anim.lastX : p.x);
      const dy = p.y - (anim.lastY != null ? anim.lastY : p.y);
      anim.lastDx = dx; anim.lastDy = dy;
      anim.lastX = p.x; anim.lastY = p.y;
      if (p.sprites) {
        let state = null;
        const moving = (dx * dx + dy * dy) > 4;
        if (moving && p.sprites.walk) state = 'walk';
        else if (p.sprites.idle) state = 'idle';
        else if (p.sprites.walk) state = 'walk';
        const frames = state ? p.sprites[state] : null;
        if (frames && frames.length) {
          if (anim.state !== state) { anim.state = state; anim.frame = 0; anim.lastT = now; }
          if (now - anim.lastT > 160) { anim.lastT = now; anim.frame = (anim.frame + 1) % frames.length; }
          const img = getSprite(frames[anim.frame % frames.length]);
          if (img) {
            const draw = r * 2.4;
            ctx.save();
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
        ctx.fillStyle = p.color || '#888';
        ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.18)';
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.stroke();
      }

      // Facing barrel
      ctx.strokeStyle = 'rgba(255,255,255,0.85)';
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(px + p.facingX * r * 0.4, py + p.facingY * r * 0.4);
      ctx.lineTo(px + p.facingX * (r + 10), py + p.facingY * (r + 10));
      ctx.stroke();
      ctx.lineCap = 'butt';

      ctx.globalAlpha = 1;

      // Name + HP only when zoom is reasonable.
      if (scale > 0.45) {
        ctx.font = '600 12px -apple-system,BlinkMacSystemFont,sans-serif';
        ctx.textAlign = 'center';
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillText(p.username, px + 1, py - r - 13);
        ctx.fillStyle = '#e7e9f3';
        ctx.fillText(p.username, px, py - r - 14);

        const wbar = Math.max(40, r * 2.4);
        const hpRatio = Math.max(0, p.health) / Math.max(1, p.maxHealth || 100);
        ctx.fillStyle = 'rgba(0,0,0,0.55)';
        ctx.fillRect(px - wbar / 2 - 1, py - r - 28, wbar + 2, 6);
        ctx.fillStyle = hpRatio > 0.4 ? '#51d88a' : (hpRatio > 0.2 ? '#ffb13b' : '#ff5a5a');
        ctx.fillRect(px - wbar / 2, py - r - 27, wbar * hpRatio, 4);
      }
    }
  }

  // ---- Frame loop ----
  function viewportSize() {
    const r = stage.getBoundingClientRect();
    return { w: r.width, h: r.height };
  }
  function focusedPlayer() {
    if (pinnedPid) {
      const p = (snapshot.players || []).find(x => x.pid === pinnedPid);
      if (p && p.alive && !p.eliminated) return p;
      pinnedPid = null;
    }
    const lb = leaderboard().filter(p => p.alive && !p.eliminated);
    return lb[0] || null;
  }
  function frame() {
    const { w, h } = viewportSize();
    ctx.clearRect(0, 0, w, h);
    const effectiveMode = pinnedPid ? 'follow' : mode;
    if (effectiveMode === 'quad') {
      const lb = leaderboard().filter(p => p.alive && !p.eliminated).slice(0, 4);
      const cells = [
        { x: 0, y: 0 }, { x: w / 2, y: 0 },
        { x: 0, y: h / 2 }, { x: w / 2, y: h / 2 },
      ];
      for (let i = 0; i < 4; i++) {
        const cw = w / 2, ch = h / 2;
        const c = cells[i];
        ctx.save();
        ctx.beginPath(); ctx.rect(c.x, c.y, cw, ch); ctx.clip();
        ctx.translate(c.x, c.y);
        const target = lb[i];
        let cam;
        if (target) {
          cam = followCamera(cw, ch, target, 1.0);
          drawScene(cam, cw, ch, { highlightPid: target.pid });
          // Player label per cell — with team badge in team / ctf modes.
          const teamColor = target.team === 1 ? '#5dd6ff'
                          : target.team === 2 ? '#ff7a7a' : null;
          const teamLabel = target.team === 1 ? 'BLUE'
                          : target.team === 2 ? 'RED' : null;
          ctx.fillStyle = 'rgba(0,0,0,0.6)';
          ctx.fillRect(8, 8, teamLabel ? 260 : 220, 26);
          // Team badge swatch
          if (teamColor) {
            ctx.fillStyle = teamColor;
            ctx.fillRect(14, 14, 14, 14);
            ctx.fillStyle = '#000';
            ctx.font = '700 10px -apple-system,sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(teamLabel === 'BLUE' ? 'B' : 'R', 21, 25);
          }
          ctx.fillStyle = '#fff';
          ctx.font = '600 13px -apple-system,sans-serif';
          ctx.textAlign = 'left';
          const labelX = teamColor ? 36 : 16;
          ctx.fillText(`${i + 1}. ${target.username}  ${target.kills}/${target.deaths}`, labelX, 26);
          // Flag-carrier mark.
          if (target.hasFlag) {
            ctx.fillStyle = target.hasFlag === 1 ? '#5dd6ff' : '#ff7a7a';
            ctx.font = '700 13px -apple-system,sans-serif';
            ctx.fillText('⚑', (teamColor ? 260 : 220) - 6, 26);
          }
        } else {
          cam = fitCamera(cw, ch);
          drawScene(cam, cw, ch, {});
          ctx.fillStyle = '#888';
          ctx.font = '500 13px -apple-system,sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText('(no player)', cw / 2, ch / 2);
        }
        ctx.restore();
        // Cell border
        ctx.strokeStyle = 'rgba(255,255,255,0.08)';
        ctx.lineWidth = 1;
        ctx.strokeRect(c.x + 0.5, c.y + 0.5, cw - 1, ch - 1);
      }
    } else if (effectiveMode === 'follow') {
      const target = focusedPlayer();
      const cam = target ? followCamera(w, h, target, 1.0) : fitCamera(w, h);
      drawScene(cam, w, h, target ? { highlightPid: target.pid } : {});
    } else {
      // arena
      const cam = fitCamera(w, h);
      drawScene(cam, w, h, {});
    }
    requestAnimationFrame(frame);
  }

  // ---- Mode controls ----
  function updateMode() {
    let label;
    if (pinnedPid) {
      const p = (snapshot.players || []).find(x => x.pid === pinnedPid);
      label = p ? `FOLLOW · ${p.username}` : 'FOLLOW';
    } else if (mode === 'arena') label = 'ARENA';
    else if (mode === 'quad') label = 'QUAD';
    else label = 'FOLLOW · LEADER';
    modePill.textContent = label;
    updateSidebar();
  }
  function cyclePlayer(dir) {
    const ps = leaderboard();
    if (!ps.length) return;
    let idx = pinnedPid ? ps.findIndex(p => p.pid === pinnedPid) : -1;
    idx = (idx + dir + ps.length) % ps.length;
    pinnedPid = ps[idx].pid;
    updateMode();
  }
  window.addEventListener('keydown', (e) => {
    if (e.key === '1') { mode = 'arena'; pinnedPid = null; updateMode(); }
    else if (e.key === '2') { mode = 'quad'; pinnedPid = null; updateMode(); }
    else if (e.key === '3') { mode = 'follow'; pinnedPid = null; updateMode(); }
    else if (e.key === '[') cyclePlayer(-1);
    else if (e.key === ']') cyclePlayer(1);
    else if (e.key === 'h' || e.key === 'H') {
      helpEl.style.display = (helpEl.style.display === 'none') ? '' : 'none';
    } else if (e.key === 'Escape') { pinnedPid = null; updateMode(); }
  });

  // ---- Boot ----
  resize();
  updateMode();
  connect();
  requestAnimationFrame(frame);
})();
