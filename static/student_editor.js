// Student editor: run Python in Pyodide, validate the resulting manifest
// with the server, then store the session and jump to the arena.

(function () {
  const codeEl = document.getElementById('code');
  const outEl = document.getElementById('output');
  const runBtn = document.getElementById('runBtn');
  const joinBtn = document.getElementById('joinBtn');
  // (Students start from a blank editor and write build_character() themselves.)
  const usernameEl = document.getElementById('username');

  let validatedManifest = null;

  // Restore previous editor state if any.
  const prev = sessionStorage.getItem('iog.editor');
  if (prev) {
    try {
      const p = JSON.parse(prev);
      if (p.code) codeEl.value = p.code;
      if (p.username) usernameEl.value = p.username;
    } catch (e) { /* ignore */ }
  }
  // Detect old JavaScript code from previous sessions and clear it so the
  // editor starts blank.
  function looksLikeJs(src) {
    return /\bfunction\s+buildCharacter\s*\(/.test(src)
        || /\bvar\s+\w+\s*=/.test(src)
        || /=>/.test(src);
  }
  if (codeEl.value && looksLikeJs(codeEl.value) && !/\bdef\s+build_character\s*\(/.test(codeEl.value)) {
    codeEl.value = '';
  }

  function persist() {
    try {
      sessionStorage.setItem('iog.editor', JSON.stringify({
        code: codeEl.value,
        username: usernameEl.value,
      }));
    } catch (e) {}
  }
  codeEl.addEventListener('input', persist);
  usernameEl.addEventListener('input', persist);

  // ---- Sprite import widget ------------------------------------------------
  // Simplified flow: student exports a .c file from PiskelApp and uploads it
  // here. We always insert as the "walk" animation — no slot picker, no
  // PNG/GIF support.
  const spriteFile = document.getElementById('spriteFile');
  const spriteOut = document.getElementById('spriteOut');
  const spritePreview = document.getElementById('spritePreview');
  const spriteCopyBtn = document.getElementById('spriteCopyBtn');
  const spriteInsertBtn = document.getElementById('spriteInsertBtn');
  const SPRITE_SLOT = 'walk';
  let lastSnippet = '';
  let lastFrames = []; // array of data URIs

  function showPreview(uris) {
    if (!spritePreview) return;
    spritePreview.innerHTML = '';
    if (!uris.length) { spritePreview.hidden = true; return; }
    spritePreview.hidden = false;
    for (const u of uris) {
      const img = document.createElement('img');
      img.src = u;
      img.className = 'sprite-thumb';
      img.style.imageRendering = 'pixelated';
      spritePreview.appendChild(img);
    }
  }
  function buildPythonSnippet(uris) {
    const lines = uris.map(u => `        "${u}",`).join('\n');
    return `# Add inside your build_character() return dict:
"sprites": {
    "${SPRITE_SLOT}": [
${lines}
    ],
},`;
  }
  function setSnippet(uris) {
    lastFrames = uris.slice();
    lastSnippet = buildPythonSnippet(uris);
    spriteOut.hidden = false;
    spriteOut.textContent = lastSnippet;
    showPreview(uris);
    spriteCopyBtn.disabled = false;
    if (spriteInsertBtn) spriteInsertBtn.disabled = false;
  }

  // Parse a Piskel-exported .c file. Returns { width, height, frames: [dataURI...] }.
  function parsePiskelC(text) {
    // Piskel uses either IMAGE_WIDTH/HEIGHT/FRAME_COUNT or
    // <NAME>_FRAME_WIDTH / <NAME>_FRAME_HEIGHT / <NAME>_FRAME_COUNT
    // (the latter even when <NAME> contains hyphens, which is technically
    // invalid C but the exporter writes it anyway).
    const wM = text.match(/(?:IMAGE_WIDTH|FRAME_WIDTH)\s+(\d+)/);
    const hM = text.match(/(?:IMAGE_HEIGHT|FRAME_HEIGHT)\s+(\d+)/);
    const fM = text.match(/FRAME_COUNT\s+(\d+)/);
    if (!wM || !hM) throw new Error('not a Piskel .c file (missing FRAME_WIDTH/HEIGHT or IMAGE_WIDTH/HEIGHT)');
    const width = parseInt(wM[1], 10);
    const height = parseInt(hM[1], 10);
    const frameCount = fM ? parseInt(fM[1], 10) : 1;
    // Pull all 0x... values in document order.
    const hex = text.match(/0x[0-9a-fA-F]+/g) || [];
    const expected = width * height * frameCount;
    if (hex.length < expected) {
      throw new Error(`expected ${expected} pixels but found ${hex.length}`);
    }
    const frames = [];
    for (let f = 0; f < frameCount; f++) {
      const cnv = document.createElement('canvas');
      cnv.width = width; cnv.height = height;
      const c = cnv.getContext('2d');
      const imgData = c.createImageData(width, height);
      const data = imgData.data;
      const base = f * width * height;
      for (let i = 0; i < width * height; i++) {
        const v = parseInt(hex[base + i], 16);
        // Piskel stores pixels as little-endian uint32; in source the value
        // reads 0xAABBGGRR, so byte-0 of memory (red channel) is the LOW byte.
        const r = v & 0xff;
        const g = (v >> 8) & 0xff;
        const b = (v >> 16) & 0xff;
        const a = (v >> 24) & 0xff;
        const j = i * 4;
        data[j] = r; data[j+1] = g; data[j+2] = b; data[j+3] = a;
      }
      c.putImageData(imgData, 0, 0);
      frames.push(cnv.toDataURL('image/png'));
    }
    return { width, height, frames };
  }

  if (spriteFile) {
    spriteFile.addEventListener('change', async () => {
      const files = Array.from(spriteFile.files || []);
      if (!files.length) return;
      try {
        const cFile = files.find(f => f.name.toLowerCase().endsWith('.c')) || files[0];
        if (!cFile.name.toLowerCase().endsWith('.c')) {
          throw new Error('Please upload a Piskel .c export.');
        }
        const text = await cFile.text();
        const { frames } = parsePiskelC(text);
        if (frames.length === 0) throw new Error('no frames in .c file');
        const trimmed = frames.slice(0, 4);
        const total = trimmed.reduce((n, u) => n + u.length, 0);
        if (total > 64 * 1024) {
          throw new Error(`frames total ${(total/1024).toFixed(1)} KB; keep your Piskel canvas small (max 64 KB).`);
        }
        setSnippet(trimmed);
        if (frames.length > 4) {
          spriteOut.textContent += `\n\n# Note: your .c had ${frames.length} frames; only the first 4 were kept.`;
        }
      } catch (e) {
        spriteOut.hidden = false;
        spriteOut.textContent = 'Error: ' + (e.message || e);
        showPreview([]);
        spriteCopyBtn.disabled = true;
        if (spriteInsertBtn) spriteInsertBtn.disabled = true;
      }
    });
    spriteCopyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(lastSnippet);
        const orig = spriteCopyBtn.textContent;
        spriteCopyBtn.textContent = '✓ Copied!';
        setTimeout(() => { spriteCopyBtn.textContent = orig; }, 1200);
      } catch (e) {
        spriteOut.textContent += '\n\n(Could not access clipboard — select & copy manually.)';
      }
    });
    if (spriteInsertBtn) {
      spriteInsertBtn.addEventListener('click', () => {
        if (!lastFrames.length) return;
        // Python-aware insertion: look for an existing "sprites": { ... } dict
        // inside the build_character() return value, OR insert one before the
        // closing brace of the LAST return dict.
        const code = codeEl.value;
        const slot = SPRITE_SLOT;
        const slotBlock =
`        "${slot}": [\n` +
          lastFrames.map(u => `            "${u}",`).join('\n') +
`\n        ],`;
        let next;
        const slotRe = new RegExp(`("${slot}"\\s*:\\s*\\[)[\\s\\S]*?(\\])`, 'm');
        if (/"sprites"\s*:\s*\{/.test(code)) {
          if (slotRe.test(code)) {
            // Replace the array contents.
            const inner = lastFrames.map(u => `            "${u}",`).join('\n');
            next = code.replace(slotRe, `$1\n${inner}\n        $2`);
          } else {
            // Add a new slot inside the existing sprites dict.
            next = code.replace(/("sprites"\s*:\s*\{)/, `$1\n${slotBlock}`);
          }
        } else {
          // Inject a fresh sprites entry before the LAST `}` that closes a
          // return dict. We look for `return {` then find its matching close.
          const retIdx = code.search(/return\s*\{/);
          if (retIdx === -1) {
            spriteOut.textContent += '\n\n# Could not find a return dict to insert into. Paste manually.';
            return;
          }
          // Find the matching closing brace by simple counting.
          let i = code.indexOf('{', retIdx);
          let depth = 0, end = -1;
          for (; i < code.length; i++) {
            const ch = code[i];
            if (ch === '{') depth++;
            else if (ch === '}') { depth--; if (depth === 0) { end = i; break; } }
          }
          if (end === -1) {
            spriteOut.textContent += '\n\n# Could not find the closing } of return. Paste manually.';
            return;
          }
          // Insert before the closing brace, with a comma if needed.
          const before = code.slice(0, end).replace(/[\s]+$/, '');
          const needsComma = !/[\{,]\s*$/.test(before);
          const insertion = `${needsComma ? ',' : ''}\n    "sprites": {\n${slotBlock}\n    },\n`;
          next = before + insertion + code.slice(end);
        }
        codeEl.value = next;
        persist();
        spriteInsertBtn.textContent = '✓ Inserted!';
        setTimeout(() => { spriteInsertBtn.textContent = '↳ Insert into editor'; }, 1400);
      });
    }
  }
  function readAsDataURL(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(new Error('read failed'));
      r.readAsDataURL(file);
    });
  }

  async function loadFile(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error('failed to load ' + url);
    return await r.text();
  }

  const resetBtn = document.getElementById('resetBtn');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      if (codeEl.value.trim() && !confirm('Clear the editor?')) return;
      codeEl.value = '';
      persist();
      outEl.textContent = 'Editor cleared. Write your build_character() function and click "Run & Validate".';
      joinBtn.disabled = true;
      validatedManifest = null;
    });
  }

  // .py file upload
  const pyFile = document.getElementById('pyFile');
  if (pyFile) {
    pyFile.addEventListener('change', async () => {
      const f = pyFile.files && pyFile.files[0];
      if (!f) return;
      if (f.size > 200 * 1024) {
        outEl.textContent = 'Error: ' + f.name + ' is over 200 KB.';
        return;
      }
      const text = await f.text();
      codeEl.value = text;
      persist();
      outEl.textContent = 'Loaded ' + f.name + '. Click "Run & Validate".';
      joinBtn.disabled = true;
      validatedManifest = null;
      pyFile.value = '';  // allow re-uploading the same filename
    });
  }

  // Initial state: blank editor. Show a hint in the status area.
  if (!codeEl.value.trim()) {
    outEl.textContent = 'Write a build_character() function, then click "Run & Validate".';
  }

  // Run the student's Python in Pyodide. Pyodide runs entirely in the
  // browser tab (sandboxed by the browser) so untrusted code can't reach
  // the network or page DOM beyond what we expose.
  let pyodidePromise = null;
  const pyStatus = document.getElementById('pyStatus');
  function setPyStatus(text, cls) {
    if (!pyStatus) return;
    pyStatus.textContent = text;
    pyStatus.className = 'py-status ' + (cls || '');
  }
  function loadPyodideOnce() {
    if (pyodidePromise) return pyodidePromise;
    setPyStatus('⊙ loading Python…', 'loading');
    pyodidePromise = (async () => {
      const py = await loadPyodide({
        indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.2/full/',
      });
      setPyStatus('● Python ready', 'ready');
      return py;
    })().catch(err => {
      setPyStatus('⚠ Python failed to load', 'err');
      pyodidePromise = null;
      throw err;
    });
    return pyodidePromise;
  }
  // Kick off the download as soon as the page loads so it's warm by the
  // time the student presses Run.
  loadPyodideOnce().catch(() => {});

  async function runInPyodide(code) {
    const py = await loadPyodideOnce();
    // Friendly pre-check: most common student mistake is pasting only the
    // `return { ... }` block without the `def build_character():` wrapper.
    if (!/\bdef\s+build_character\s*\(/.test(code)) {
      throw new Error(
        'Your code is missing the first line. It must start with:\n' +
        '    def build_character():\n' +
        'Everything else should be indented inside that function.'
      );
    }
    // Fresh namespace each run.
    const ns = py.toPy({});
    try {
      try {
        await py.runPythonAsync(code, { globals: ns });
      } catch (e) {
        const msg = (e && e.message) ? e.message : String(e);
        if (/'return' outside function/.test(msg)) {
          throw new Error(
            "Python says: 'return' outside function.\n" +
            "Your `return { ... }` block needs to be INSIDE `def build_character():`.\n" +
            "Make sure the very first line of your code is:  def build_character():\n" +
            "and everything below it is indented (4 spaces)."
          );
        }
        throw e;
      }
      const builder = ns.get('build_character');
      if (!builder) {
        throw new Error('You must define a function called build_character().');
      }
      let resultProxy;
      try {
        resultProxy = builder();
      } finally {
        builder.destroy && builder.destroy();
      }
      // Convert PyProxy -> JS plain object via JSON to avoid Map/PyProxy issues.
      const jsonStr = py.runPython(
        'import json\njson.dumps(_iog_result, default=str)',
        { globals: py.toPy({ _iog_result: resultProxy }) }
      );
      resultProxy && resultProxy.destroy && resultProxy.destroy();
      return JSON.parse(jsonStr);
    } finally {
      ns.destroy && ns.destroy();
    }
  }

  runBtn.addEventListener('click', async () => {
    outEl.textContent = 'Running…';
    joinBtn.disabled = true;
    validatedManifest = null;
    let manifest;
    try {
      manifest = await runInPyodide(codeEl.value);
    } catch (e) {
      outEl.textContent = 'Error: ' + (e && e.message ? e.message : e);
      return;
    }
    // Server-side validate.
    let r;
    try {
      r = await fetch('/api/validate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(manifest),
      });
    } catch (e) {
      outEl.textContent = 'Network error: ' + e.message;
      return;
    }
    const j = await r.json();
    if (!r.ok || !j.ok) {
      outEl.textContent = 'Validation failed: ' + (j.error || r.statusText);
      if (j.report) renderReport(j.report);
      return;
    }
    validatedManifest = j.manifest;
    outEl.textContent = 'OK! Validated character:\n' + JSON.stringify(j.manifest, null, 2);
    if (j.report) renderReport(j.report);
    joinBtn.disabled = false;
  });

  function renderReport(rep) {
    const root = document.getElementById('report');
    root.hidden = false;
    const fill = document.getElementById('budgetFill');
    const pct = Math.min(100, (rep.total / rep.budget) * 100);
    fill.style.width = pct + '%';
    fill.style.background = rep.ok
      ? 'linear-gradient(90deg, #51d88a, #5dd6ff)'
      : 'linear-gradient(90deg, #ff5a5a, #ffb13b)';
    document.getElementById('budgetSummary').textContent =
      `${rep.total} / ${rep.budget} pts used (${rep.remaining} remaining)`
      + (rep.ok ? '' : '  — over budget!');
    const sUL = document.getElementById('statCosts');
    sUL.innerHTML = '';
    Object.entries(rep.stats).forEach(([k, v]) => {
      const li = document.createElement('li');
      li.textContent = `${k}: ${v} pts`;
      sUL.appendChild(li);
    });
    const pUL = document.getElementById('powerCosts');
    pUL.innerHTML = '';
    rep.powers.forEach(p => {
      const li = document.createElement('li');
      li.textContent = `${p.name} (${p.kind}, cd ${p.cooldownMs}ms): ${p.cost} pts`;
      pUL.appendChild(li);
    });
    const wUL = document.getElementById('warnings');
    wUL.innerHTML = '';
    if (rep.warnings.length === 0) {
      const li = document.createElement('li');
      li.textContent = 'no warnings';
      li.style.color = 'var(--ok)';
      wUL.appendChild(li);
    } else {
      rep.warnings.forEach(w => {
        const li = document.createElement('li');
        li.textContent = w;
        li.style.color = 'var(--accent)';
        wUL.appendChild(li);
      });
    }
    const mUL = document.getElementById('metrics');
    mUL.innerHTML = '';
    Object.entries(rep.metrics).forEach(([k, v]) => {
      const li = document.createElement('li');
      li.textContent = `${k}: ${v}`;
      mUL.appendChild(li);
    });
  }

  joinBtn.addEventListener('click', () => {
    const username = (usernameEl.value || '').trim();
    if (!username) { outEl.textContent = 'Please enter a name first.'; return; }
    if (!validatedManifest) { outEl.textContent = 'Run & Validate first.'; return; }
    sessionStorage.setItem('iog.session', JSON.stringify({
      username, manifest: validatedManifest,
    }));
    location.href = '/game';
  });
})();
