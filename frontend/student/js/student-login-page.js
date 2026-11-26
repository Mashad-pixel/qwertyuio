
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const $ = s => document.querySelector(s);
  const root = document.documentElement;
  const svg = $('#scene'), linksG = $('#links'), handle = $('#handle'), pull = $('#pull');
  const card = $('#login');
  const S = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0.4 : 1;

  // Chain geometry in SVG units
  const N = 14, SEG = 10, TOP = { x: 238, y: 266 };
  const LEN = (N - 1) * SEG, MAX_REACH = LEN * 1.2;
  const restX = TOP.x, restY = TOP.y + LEN;
  const THRESH = 20;           // distance the chain must be pulled to count as a pluck
  const G = 0.12, DAMP = 0.99; // chain gravity and velocity retention
  const K_GRAB = 0.16, D_GRAB = 0.82;  // handle follows pointer
  const K_REL = 0.06, D_REL = 0.965;   // handle springs back with overshoot
  const X = new Float64Array(N), Y = new Float64Array(N), PX = new Float64Array(N), PY = new Float64Array(N);
  for (let i = 0; i < N; i++) { X[i] = PX[i] = restX; Y[i] = PY[i] = TOP.y + i * SEG; }

  const links = [];
  for (let i = 0; i < N - 1; i++) {
    const e = document.createElementNS(NS, 'ellipse');
    e.setAttribute('rx', '3.6'); e.setAttribute('ry', '6.2');
    linksG.appendChild(e); links.push(e);
  }

  // Lamp and card tweens (no start delay)
  const ease = {
    sine: t => -(Math.cos(Math.PI * t) - 1) / 2,
    out3: t => 1 - (1 - t) ** 3,
    out2: t => 1 - (1 - t) * (1 - t),
    in3: t => t * t * t
  };
  const lightT = { cur: 0, from: 0, to: 0, t0: 0, end: 0, ease: ease.sine };
  const cardT = { cur: 0, from: 0, to: 0, t0: 0, end: 0, ease: ease.sine };
  function startTween(T, to, dur, fn) {
    T.from = T.cur; T.to = to; T.t0 = performance.now(); T.end = T.t0 + dur * S; T.ease = fn;
  }
  function tick(T, now) {
    if (now >= T.end) T.cur = T.to;
    else if (now <= T.t0) T.cur = T.from;
    else T.cur = T.from + (T.to - T.from) * T.ease((now - T.t0) / (T.end - T.t0));
    return T.cur;
  }

  // State
  let on = false, cooldownUntil = 0;
  let grabbing = false, grabId = null, grabOX = 0, grabOY = 0, downX = 0, downY = 0, downT = 0, maxDown = 0;
  let tgtX = restX, tgtY = restY;
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  let stretch = 0;             // smoothly eases the chain longer while it is pulled

  function svgPt(e) {
    const p = svg.createSVGPoint();
    p.x = e.clientX; p.y = e.clientY;
    return p.matrixTransform(svg.getScreenCTM().inverse());
  }

  // Switch the lamp immediately, with a mechanical kick on the chain
  function toggle(force) {
    const now = performance.now();
    if (typeof force === 'boolean') { if (force === on) return; }
    else if (now < cooldownUntil) return;
    cooldownUntil = now + 300;
    on = !on;
    if (!on && force === undefined) setTimeout(() => window.__reset && window.__reset(), 600);
    PY[N - 1] = Y[N - 1] + 1.5;
    if (on) {
      startTween(lightT, 1, 900, ease.sine);
      startTween(cardT, 1, 700, ease.out3);
    } else {
      startTween(lightT, 0, 600, ease.out2);
      startTween(cardT, 0, 500, ease.in3);
    }
    handle.setAttribute('aria-pressed', String(on));
    handle.setAttribute('aria-label', on ? 'Pull chain to switch the lamp off' : 'Pull chain to switch the lamp on');
  }

  // Verlet chain with a spring-driven handle that follows the pointer in any direction
  function physics() {
    for (let i = 1; i < N; i++) {
      const last = i === N - 1;
      let vx = (X[i] - PX[i]) * (last ? (grabbing ? D_GRAB : D_REL) : DAMP);
      let vy = (Y[i] - PY[i]) * (last ? (grabbing ? D_GRAB : D_REL) : DAMP);
      PX[i] = X[i]; PY[i] = Y[i];
      let ax = 0, ay = G;
      if (last) {
        const k = grabbing ? K_GRAB : K_REL;
        ax = k * (tgtX - X[i]);
        ay = k * (tgtY - Y[i]);
      }
      X[i] += vx + ax; Y[i] += vy + ay;
    }
    stretch += ((grabbing ? 0.2 : 0) - stretch) * 0.1;
    const seg = SEG * (1 + stretch);
    for (let it = 0; it < 8; it++) {
      X[0] = TOP.x; Y[0] = TOP.y;
      for (let i = 0; i < N - 1; i++) {
        const dx = X[i + 1] - X[i], dy = Y[i + 1] - Y[i];
        const d = Math.hypot(dx, dy) || 1e-6;
        const diff = (d - seg) / d;
        if (i === 0) { X[i + 1] -= dx * diff; Y[i + 1] -= dy * diff; }
        else {
          const hx = dx * diff * 0.5, hy = dy * diff * 0.5;
          X[i] += hx; Y[i] += hy; X[i + 1] -= hx; Y[i + 1] -= hy;
        }
      }
    }
    if (grabbing) maxDown = Math.max(maxDown, Math.hypot(X[N - 1] - restX, Y[N - 1] - restY));
  }

  let lastL = -1, lastC = -1, lastVis = null;
  function render(now) {
    const l = tick(lightT, now), c = tick(cardT, now);
    if (Math.abs(l - lastL) > 0.0005) { root.style.setProperty('--l', l.toFixed(4)); lastL = l; }
    if (Math.abs(c - lastC) > 0.0005) { root.style.setProperty('--c', c.toFixed(4)); lastC = c; }
    const vis = c > 0.004;
    if (vis !== lastVis) { card.style.visibility = vis ? 'visible' : 'hidden'; lastVis = vis; }
    card.inert = !on;

    for (let i = 0; i < N - 1; i++) {
      const mx = (X[i] + X[i + 1]) / 2, my = (Y[i] + Y[i + 1]) / 2;
      const ang = Math.atan2(X[i + 1] - X[i], Y[i + 1] - Y[i]) * 180 / Math.PI;
      links[i].setAttribute('transform',
        `translate(${mx.toFixed(2)} ${my.toFixed(2)}) rotate(${(-ang + (i % 2 ? 90 : 0)).toFixed(2)})`);
    }
    const hang = Math.atan2(X[N - 1] - X[N - 2], Y[N - 1] - Y[N - 2]) * 180 / Math.PI;
    handle.setAttribute('transform', `translate(${X[N - 1].toFixed(2)} ${Y[N - 1].toFixed(2)})`);
    pull.setAttribute('transform', `rotate(${(-hang).toFixed(2)})`);
  }

  // Pointer: grab, move in any direction, release to pluck
  handle.addEventListener('pointerdown', e => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    e.preventDefault();
    grabbing = true; grabId = e.pointerId;
    handle.setPointerCapture(e.pointerId);
    const p = svgPt(e);
    grabOX = p.x - X[N - 1]; grabOY = p.y - Y[N - 1];
    downX = p.x; downY = p.y; downT = performance.now();
    maxDown = 0;
    handle.style.cursor = 'grabbing';
  });
  handle.addEventListener('pointermove', e => {
    if (!grabbing || e.pointerId !== grabId) return;
    const p = svgPt(e);
    let tx = p.x - grabOX, ty = p.y - grabOY;
    const dx = tx - TOP.x, dy = ty - TOP.y, d = Math.hypot(dx, dy);
    if (d > MAX_REACH) { tx = TOP.x + dx * MAX_REACH / d; ty = TOP.y + dy * MAX_REACH / d; }
    tgtX = tx; tgtY = ty;
  });
  const release = e => {
    if (!grabbing || e.pointerId !== grabId) return;
    const p = svgPt(e);
    const moved = Math.hypot(p.x - downX, p.y - downY);
    const quick = performance.now() - downT < 250 && moved < 6;
    grabbing = false; grabId = null;
    handle.style.cursor = 'grab';
    tgtX = restX; tgtY = restY;
    if (maxDown >= THRESH || quick) toggle();
    maxDown = 0;
  };
  handle.addEventListener('pointerup', release);
  handle.addEventListener('pointercancel', release);
  handle.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) { e.preventDefault(); toggle(); }
  });

  // Login form (real backend)
  const email = $('#email'), pass = $('#password'), msg = $('#form-msg'), eye = $('#toggle-pass');
  let lbusy = false;
  $('#f-login').addEventListener('submit', async e => {
    e.preventDefault(); if (lbusy) return; msg.textContent = '';
    const id = parseId(email.value);
    if (!id) { msg.textContent = 'Enter a valid email address or phone number.'; email.focus(); return; }
    if (id.type !== 'email') { msg.textContent = 'Use your account email to sign in.'; email.focus(); return; }
    if (pass.value.length < 8) { msg.textContent = 'Use at least 8 characters for your password.'; pass.focus(); return; }
    lbusy = true; const b = e.submitter; if (b) b.disabled = true;
    try {
      const response = await trayAuth.login(id.value, pass.value);
      if (String(response?.data?.role || '').toUpperCase() !== 'STUDENT') {
        await trayAuth.logout();
        msg.textContent = 'This is a staff account. Use the staff sign-in page.';
        return;
      }
      msg.textContent = 'Signed in as ' + response.data.name + '.';
      pass.value = '';
      const returnPages = { 'checkout.html': './checkout.html', 'cart.html': './cart.html' };
      window.location.href = returnPages[new URLSearchParams(window.location.search).get('next')] || '../index.html';
    } catch (error) {
      msg.textContent = error.status === 429 ? 'Too many attempts. Wait a few minutes and try again.' : (error.message || 'Unable to log in');
    } finally {
      lbusy = false; if (b) b.disabled = false;
    }
  });
  eye.addEventListener('click', () => {
    const show = pass.type === 'password';
    pass.type = show ? 'text' : 'password';
    eye.setAttribute('aria-pressed', String(show));
    eye.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  });
    card.querySelectorAll('[data-social]').forEach(b => b.addEventListener('click', () => {
    msg.textContent = `${b.dataset.social} sign-in is not connected in this preview.`;
  }));

  // ===== Sign-up & recovery (inside the same card) =====
  const F=(id,l,p,t='text',eye=0)=>`<label class="field" for="${id}">${l}${eye?`<div class="input-wrap"><input id="${id}" type="${t}" placeholder="${p}" autocomplete="off"><button type="button" class="eye" data-for="${id}" aria-label="Show password" aria-pressed="false"></button></div>`:`<input id="${id}" type="${t}" placeholder="${p}" autocomplete="off">`}<span class="hint" id="h-${id}"></span></label>`;
  const BTN=t=>`<button class="btn-primary" type="submit"><span class="t">${t}</span><span class="sp"></span></button>`;
  const TA=(id,l,p)=>`<label class="field" for="${id}">${l}<textarea id="${id}" placeholder="${p}" maxlength="1000"></textarea><span class="hint" id="h-${id}"></span></label>`;
  card.insertAdjacentHTML('beforeend',`
  <div class="view" id="v-forgot"><form id="f-forgot" novalidate><h1 class="sm">Forgot password?</h1><p class="sub">We’ll send a 6-digit code to the email address on your account.</p>
   ${F('fg-id','Email address','you@example.com')}${BTN('Continue')}<p class="msg" id="fg-msg" role="alert"></p>
   <p class="foot"><a href="#" data-view="v-login">Back to Login</a></p><p class="foot" style="margin-top:8px"><a href="#" data-view="v-alt">Can’t access your registered email or mobile number?</a></p></form></div>
  <div class="view" id="v-newpw"><form id="f-newpw" novalidate><h1 class="sm">Set a new password.</h1><p class="sub">Choose one you haven’t used before.</p>
   ${F('np1','New password','At least 8 characters','password',1)}${F('np2','Confirm new password','Re-enter your password','password',1)}
   <ul class="rq" id="rq"><li data-r="len">At least 8 characters</li><li data-r="l">A letter</li><li data-r="n">A number</li><li data-r="m">Both passwords match</li></ul>${BTN('Reset password')}<p class="msg" id="np-msg" role="alert"></p></form></div>
  <div class="view" id="v-alt"><button class="back" type="button" data-view="v-forgot">← Back</button><h1 class="sm">Recover your account.</h1><p class="sub">Choose how you’d like to prove it’s you.</p>
   <button class="oc" data-view="v-code">Use a backup recovery code<small>One-time code you saved earlier</small></button>
   <button class="oc" data-view="v-support">Contact support<small>Send a recovery request for manual review</small></button></div>
  <div class="view" id="v-code"><form id="f-code" novalidate><button class="back" type="button" data-view="v-alt">← Back</button><h1 class="sm">Backup code.</h1><p class="sub">Each code works only once.</p>
   ${F('rc-id','Email address','you@example.com')}${F('rc-code','Recovery code','XXXX-XXXX-XXXX')}${BTN('Continue')}<p class="msg" id="rc-msg" role="alert"></p></form></div>
  <div class="view" id="v-support"><form id="f-support" novalidate><button class="back" type="button" data-view="v-alt">← Back</button><h1 class="sm">Contact support.</h1><p class="sub">Submitting this doesn’t change your account. We verify ownership first.</p>
   ${F('sp-name','Full name','Your full name')}${F('sp-id','Registered email or mobile number','you@example.com or 98765 43210')}${F('sp-mail','Contact email for updates','Where we can reach you')}
   ${F('sp-created','Approx. account creation date','e.g. March 2025')}${F('sp-last','Approx. last successful login','e.g. last month')}${TA('sp-reason','Why did you lose access?','Tell us what happened')}${TA('sp-extra','Anything else that can help (optional)','Devices used, past payments, etc.')}
   <p class="warn">Never share your password, OTP, UPI PIN or banking details.</p>${BTN('Submit request')}<p class="msg" id="sp-msg" role="alert"></p></form></div>`);
  const $$ = q => [...document.querySelectorAll(q)];
  const goView = id => { $$('.view').forEach(v => v.classList.toggle('on', v.id === id)); card.scrollTop = 0; msg.textContent = '';
    const f = $('#' + id).querySelector('input'); if (f && id !== 'v-verify' && on) setTimeout(() => f.focus({ preventScroll: true }), 60); };
  $$('[data-view]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); goView(a.dataset.view); }));

  // Goes through the shared API client, so the CSRF token is sent and the server's message is shown.
  // Successful replies are flattened so callers can read fields such as resetToken and ref directly.
  const post = async (url, body) => {
    try {
      // The page passes full /api paths; the shared client already adds /api, so strip it once.
      const j = await trayApi.post(url.replace(/^\/api/, ''), body);
      return { ok: true, ...j, ...((j && j.data) || {}) };
    } catch (e) {
      if (typeof e.status !== 'number') return { error: 'Can’t reach the server. Check your connection.' };
      return { error: e.message || 'Something went wrong. Please try again.' };
    } };

  const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  function parseId(v) { v = v.trim(); if (EMAIL.test(v)) return { type: 'email', value: v.toLowerCase() };
    if (/^[+()\d\s-]+$/.test(v)) { let d = v.replace(/\D/g, ''); if (d.length === 12 && d.startsWith('91')) d = d.slice(2); if (d.length === 11 && d[0] === '0') d = d.slice(1);
      if (/^[6-9]\d{9}$/.test(d)) return { type: 'mobile', value: '+91' + d }; } return null; }
  const EYE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
  $$('.eye[data-for]').forEach(b => { b.innerHTML = EYE; b.addEventListener('click', () => { const i = $('#' + b.dataset.for), sh = i.type === 'password';
    i.type = sh ? 'text' : 'password'; b.setAttribute('aria-pressed', sh); b.setAttribute('aria-label', sh ? 'Hide password' : 'Show password'); }); });
  const setH = (k, t, c) => { const h = $('#h-' + k); h.textContent = t || ''; h.className = 'hint' + (c ? ' ' + c : ''); };
  const bad = (el, v) => el.setAttribute('aria-invalid', v ? 'true' : 'false');
  $('#r-pw').addEventListener('input', e => { const p = e.target.value; let s = 0;
    if (p.length >= 8) s++; if (p.length >= 12) s++; if (/[a-z]/.test(p) && /[A-Z]/.test(p)) s++; if (/\d/.test(p)) s++; if (/[^\w\s]/.test(p)) s++;
    const b = $('#bar'); b.style.width = (p ? Math.max(15, s * 20) : 0) + '%'; b.style.background = s < 3 ? '#f08a6c' : s < 4 ? '#e8b77a' : '#9fd8a8'; });
  $('#r-id').addEventListener('input', e => { const v = e.target.value.trim(); if (!v) return setH('id', '');
    const p = parseId(v); setH('id', p ? (p.type === 'email' ? 'Email detected. We’ll send a verification code.' : 'Mobile number detected. We’ll send an SMS code.') : '', p ? 'ok' : ''); });
  [['r-terms', 'c-terms'], ['r-priv', 'c-priv']].forEach(([i, c]) => $('#' + i).addEventListener('change', () => $('#' + c).classList.remove('bad')));

  function validate() {
    let ok = true, first = null; const fail = (el, k, t) => { setH(k, t, 'e'); bad(el, true); ok = false; first = first || el; };
    const n = $('#r-name'), i = $('#r-id'), p = $('#r-pw'), p2 = $('#r-pw2');
    [n, i, p, p2].forEach(x => bad(x, false)); setH('name', ''); setH('pw2', '');
    const nm = n.value.trim().replace(/\s+/g, ' ');
    if (!nm) fail(n, 'name', 'Please tell us your name.'); else if (nm.length < 2 || nm.length > 80 || /[<>{}\d]/.test(nm)) fail(n, 'name', 'Please enter your real name (letters only).');
    if (!i.value.trim()) fail(i, 'id', 'Enter an email address or mobile number.'); else if (!parseId(i.value)) fail(i, 'id', 'That isn’t a valid email or 10-digit Indian mobile number.');
    if (p.value.length < 8 || !/[A-Za-z]/.test(p.value) || !/\d/.test(p.value)) fail(p, 'pw', 'Use 8+ characters with at least one letter and one number.'); else setH('pw', 'Looks good.', 'ok');
    if (!p2.value) fail(p2, 'pw2', 'Please confirm your password.'); else if (p2.value !== p.value) fail(p2, 'pw2', 'Passwords don’t match yet.');
    let consent = true; [['r-terms', 'c-terms'], ['r-priv', 'c-priv']].forEach(([a, c]) => { const b = !$('#' + a).checked; $('#' + c).classList.toggle('bad', b); if (b) { consent = false; ok = false; } });
    const m = $('#r-msg');
    if (!ok) { m.textContent = first ? 'Please fix the highlighted fields.' : 'Please accept the Terms and Privacy Policy to continue.';
      if (first && !consent) m.textContent += ' Both consent boxes are required.';
      const f = $('#f-reg'); f.classList.remove('shake'); void f.offsetWidth; f.classList.add('shake'); first && first.focus(); } else m.textContent = '';
    return ok ? { name: nm, id: parseId(i.value), password: p.value } : null;
  }

  let cur = null, busy = false, flow = 'register', resetTok = null, tm;
  const E = id => document.getElementById(id);
  const load = (b, v) => { b.classList.toggle('load', v); b.disabled = v; };
  const shake = id => { const f = E(id); f.classList.remove('shake'); void f.offsetWidth; f.classList.add('shake'); };
  const hint = (id, t, c) => { const h = E('h-' + id); h.textContent = t || ''; h.className = 'hint' + (c ? ' ' + c : ''); };
  const done = (t, p) => { E('okh').textContent = t; E('okp').textContent = p; goView('v-ok'); };
  const submitting = (form, fn) => E(form).addEventListener('submit', async e => { e.preventDefault(); if (busy) return;
    const b = E(form).querySelector('.btn-primary'); await fn(b, v => { busy = true; load(b, true); return () => { busy = false; load(b, false); }; }); });

  // Register
  E('f-reg').addEventListener('submit', async e => { e.preventDefault(); if (busy) return; const v = validate(); if (!v) return;
    if (v.id.type !== 'email') { E('r-msg').textContent = 'Use an email address to create your account.'; return; }
    busy = true; load(E('r-go'), true);
    try {
      await trayApi.post('/auth/register', { name: v.name, email: v.id.value, password: v.password });
      const returnPages = { 'checkout.html': './checkout.html', 'cart.html': './cart.html' };
      window.location.href = returnPages[new URLSearchParams(window.location.search).get('next')] || '../index.html';
    } catch (error) {
      E('r-msg').textContent = error.status === 429 ? 'Too many registration attempts. Please try again later.' : (error.message || 'Could not create the account.');
    } finally {
      busy = false; load(E('r-go'), false);
    }
  });

  // Forgot password
  E('f-forgot').addEventListener('submit', async e => { e.preventDefault(); if (busy) return; const m = E('fg-msg'); m.textContent = '';
    const id = parseId(E('fg-id').value); if (!id) { m.textContent = 'Enter a valid email address or 10-digit Indian mobile number.'; return shake('f-forgot'); }
    const b = E('f-forgot').querySelector('.btn-primary'); busy = true; load(b, true);
    const r = await post('/api/forgot/start', { identifier: id.value }); busy = false; load(b, false);
    if (r.error) { m.textContent = r.error; return; } startVerify('forgot', id); });

  // Shared OTP screen
  const mask = c => c.type === 'email' ? c.value.replace(/^(.).*(@.*)$/, '$1•••$2') : c.value.replace(/(\+91)(\d{2})\d{5}(\d{3})/, '$1 $2•••••$3');
  function startVerify(f, id) { flow = f; cur = id;
    E('vsub').textContent = (f === 'forgot' ? 'If an account matches ' : 'We sent a 6-digit code to ') + mask(id) + (f === 'forgot' ? ', we’ve sent a 6-digit code.' : '.') + ' It expires in 5 minutes.';
    buildOtp(); goView('v-verify'); E('otp').children[0].focus(); cool(); }
  function buildOtp() { const o = E('otp'); o.innerHTML = ''; E('vmsg').textContent = '';
    for (let i = 0; i < 6; i++) { const x = document.createElement('input'); x.type = 'text'; x.inputMode = 'numeric'; x.maxLength = 1; x.autocomplete = i ? 'off' : 'one-time-code'; x.setAttribute('aria-label', 'Digit ' + (i + 1)); o.appendChild(x); }
    const ins = [...o.children];
    ins.forEach((x, i) => { x.oninput = () => { x.value = x.value.replace(/\D/g, ''); if (x.value && ins[i + 1]) ins[i + 1].focus(); if (ins.every(y => y.value)) submitOtp(); };
      x.onkeydown = e => { if (e.key === 'Backspace' && !x.value && ins[i - 1]) ins[i - 1].focus(); };
      x.onpaste = e => { e.preventDefault(); const t = (e.clipboardData.getData('text') || '').replace(/\D/g, '').slice(0, 6); [...t].forEach((c, j) => ins[j].value = c); ins[Math.min(t.length, 5)].focus(); if (t.length === 6) submitOtp(); }; }); }
  async function submitOtp() { if (busy) return; const c = [...E('otp').children].map(x => x.value).join('');
    if (c.length < 6) { E('vmsg').textContent = 'Enter all 6 digits.'; return; }
    busy = true; load(E('vbtn'), true); const r = await post('/api/' + flow + '/verify', { identifier: cur.value, otp: c }); busy = false; load(E('vbtn'), false);
    if (r.ok) { if (flow === 'register') { window.__reset(); done('Welcome.', 'Your account is verified and ready.'); } else { resetTok = r.resetToken; goView('v-newpw'); } return; }
    E('vmsg').textContent = r.error; [...E('otp').children].forEach(x => x.value = ''); E('otp').children[0].focus(); shake('otp'); }
  E('vbtn').addEventListener('click', submitOtp);
  E('back').addEventListener('click', () => goView(flow === 'register' ? 'v-reg' : 'v-forgot'));
  function cool() { let n = 30; const b = E('resend'); b.disabled = true; clearInterval(tm); E('rs').textContent = 'Resend in 30s.';
    tm = setInterval(() => { n--; E('rs').textContent = n > 0 ? 'Resend in ' + n + 's.' : 'Didn’t get it?'; if (n <= 0) { clearInterval(tm); b.disabled = false; } }, 1000); }
  E('resend').addEventListener('click', async () => { const r = await post('/api/' + flow + '/resend', { identifier: cur.value });
    if (r.error) { E('vmsg').textContent = r.error; return; } buildOtp(); E('otp').children[0].focus(); E('vmsg').textContent = 'A new code has been sent.'; cool(); });

  // New password
  const pwOk = () => { const a = E('np1').value, b = E('np2').value, st = { len: a.length >= 8, l: /[A-Za-z]/.test(a), n: /\d/.test(a), m: !!a && a === b };
    $$('#rq li').forEach(li => li.classList.toggle('y', st[li.dataset.r])); return st.len && st.l && st.n && st.m; };
  ['np1', 'np2'].forEach(i => E(i).addEventListener('input', pwOk));
  E('f-newpw').addEventListener('submit', async e => { e.preventDefault(); if (busy) return; const m = E('np-msg'); m.textContent = '';
    if (!pwOk()) { m.textContent = 'Please meet all the requirements below.'; return shake('f-newpw'); }
    const b = E('f-newpw').querySelector('.btn-primary'); busy = true; load(b, true);
    const r = await post('/api/forgot/reset', { resetToken: resetTok, password: E('np1').value }); busy = false; load(b, false);
    if (r.error) { m.textContent = r.error; return; }
    window.__reset(); done('Password updated.', 'You’ve been signed out everywhere. Please log in with your new password.'); });

  // Backup code
  E('f-code').addEventListener('submit', async e => { e.preventDefault(); if (busy) return; const m = E('rc-msg'); m.textContent = '';
    const id = parseId(E('rc-id').value), code = E('rc-code').value.trim();
    if (!id || code.length < 10) { m.textContent = 'Enter your email or mobile number and your full recovery code.'; return shake('f-code'); }
    const b = E('f-code').querySelector('.btn-primary'); busy = true; load(b, true);
    const r = await post('/api/recovery/code', { identifier: id.value, code }); busy = false; load(b, false);
    if (r.error) { m.textContent = r.error; return; } resetTok = r.resetToken; goView('v-newpw'); });

  // Support request
  E('f-support').addEventListener('submit', async e => { e.preventDefault(); if (busy) return; const m = E('sp-msg'); m.textContent = '';
    const id = parseId(E('sp-id').value), name = E('sp-name').value.trim(), mail = E('sp-mail').value.trim(), why = E('sp-reason').value.trim();
    if (name.length < 2 || !id || !EMAIL.test(mail) || why.length < 10) { m.textContent = 'Please fill in your name, account, a valid contact email and a short reason.'; return shake('f-support'); }
    const b = E('f-support').querySelector('.btn-primary'); busy = true; load(b, true);
    const r = await post('/api/recovery/request', { name, identifier: id.value, contactEmail: mail, createdEst: E('sp-created').value, lastLoginEst: E('sp-last').value, reason: why, extra: E('sp-extra').value });
    busy = false; load(b, false); if (r.error) { m.textContent = r.error; return; }
    window.__reset(); done('Request received.', 'Reference ' + r.ref + '. We’ll review it and email you. Nothing changes on your account until ownership is verified.'); });

  // Reset state when the lamp is pulled off
  window.__reset = () => { $$('.card input:not([type=checkbox])').forEach(i => i.value = ''); $$('.card textarea').forEach(t => t.value = ''); $$('.card input[type=checkbox]').forEach(i => i.checked = false);
    $$('.hint').forEach(x => x.textContent = ''); $$('.msg').forEach(x => x.textContent = ''); $$('#rq li').forEach(li => li.classList.remove('y')); $('#bar').style.width = 0;
    E('h-pw').textContent = 'Use 8+ characters with a letter and a number.'; resetTok = null; cur = null; clearInterval(tm); if (!E('v-ok').classList.contains('on')) goView('v-login'); };

  // Lamp goes off whenever the person leaves the page
  const leave = () => { if (on) toggle(false); };
  document.addEventListener('visibilitychange', () => { if (document.hidden) leave(); });
  addEventListener('pagehide', leave); addEventListener('blur', leave);

  // Reset link from email (?reset=TOKEN): light the lamp and open the new-password view
  const rt = new URLSearchParams(location.search).get('reset');
  if (rt) { history.replaceState(null, '', location.pathname); resetTok = rt; setTimeout(() => { toggle(true); goView('v-newpw'); }, 400); }

  // Fixed-step physics at 60 Hz, render every frame
  const STEP = 1000 / 60;
  let last = performance.now(), acc = 0;
  function loop(now) {
    acc += Math.min(now - last, 80);
    last = now;
    while (acc >= STEP) { physics(); acc -= STEP; }
    render(now);
    requestAnimationFrame(loop);
  }
  render(performance.now());
  requestAnimationFrame(loop);
})();
