import { useEffect, useRef, useState } from 'react';
import './FlexCarousel.css';

const wrap = (v, size) => ((((v + size / 2) % size) + size) % size) - size / 2;
const clamp01 = v => Math.min(Math.max(v, 0), 1);
const easeOut = v => 1 - Math.pow(1 - clamp01(v), 3);
const easeInOut = v => { const t = clamp01(v); return t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t+2, 3)/2; };

const FlexCarousel = ({
  items = [],
  cardHeight = 0.62,
  gap = 18,
  radius = 18,
  bend = 0.55,         // how far the row flexes vertically at the edges
  curl = 'twist',      // twist | rise | fall
  squeeze = 0.25,      // shrink while moving fast
  intro = 'rise',
  focusOnClick = true,
  captions = true,
  autoplay = false,
  interval = 4,
  className = '',
  onChange,
  onSelect,
}) => {
  const ref = useRef(null);
  const canvasRef = useRef(null);
  const [active, setActive] = useState(0);
  const state = useRef({
    pos: 0, vel: 0, goal: 0, mode: 'spring',
    dragging: false, startX: 0, startPos: 0, samples: [],
    energy: 0, focusT: 0, focusTarget: 0, focusIndex: -1,
    introT: 0, introDone: intro === 'none',
    images: [], ready: false, hover: -1,
    autoplayAt: 0, interactedAt: -1e9,
  });

  useEffect(() => {
    const container = ref.current;
    const canvas = canvasRef.current;
    if (!container || !canvas || !items.length) return;
    const ctx = canvas.getContext('2d');
    const s = state.current;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    let W = 1, H = 1, dpr = Math.min(window.devicePixelRatio || 1, 2);
    let raf = 0, last = performance.now(), alive = true;
    // start centered on the first card
    {
      const cardH = Math.max(24, cardHeight * 1);
      // positions are relative to center; goal 0 already centers centers[0]? centers[0] = widths[0]/2
    }

    // load images
    let loaded = 0;
    s.images = items.map((it, i) => {
      const img = new Image();
      img.decoding = 'async';
      img.onload = () => { loaded++; if (loaded === items.length) { s.ready = true; s.introAt = performance.now(); } };
      img.onerror = () => { loaded++; if (loaded === items.length) { s.ready = true; s.introAt = performance.now(); } };
      img.src = it.src;
      return img;
    });

    const metrics = () => {
      const cardH = Math.max(24, cardHeight * H);
      const n = items.length;
      const widths = items.map((_, i) => {
        const img = s.images[i];
        const aspect = img && img.naturalWidth ? img.naturalWidth / img.naturalHeight : 0.8;
        return aspect * cardH;
      });
      const centers = [];
      let cur = 0;
      for (let i = 0; i < n; i++) { centers.push(cur + widths[i]/2); cur += widths[i] + gap; }
      return { cardH, widths, centers, loop: Math.max(cur, 1), n };
    };

    const nearest = (m, at) => {
      let best = 0, bd = Infinity;
      for (let i = 0; i < m.n; i++) {
        const d = Math.abs(wrap(m.centers[i] - at, m.loop));
        if (d < bd) { bd = d; best = i; }
      }
      return best;
    };
    const snap = (m, at) => at + wrap(m.centers[nearest(m, at)] - at, m.loop);

    const resize = () => {
      W = Math.max(1, container.clientWidth);
      H = Math.max(1, container.clientHeight);
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = W * dpr; canvas.height = H * dpr;
      canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    };
    const ro = new ResizeObserver(resize); ro.observe(container); resize();

    const local = e => { const r = container.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };

    const step = (m, d) => {
      let at = snap(m, s.goal); let idx = nearest(m, at);
      for (let k = 0; k < Math.abs(d); k++) {
        const next = (idx + (d > 0 ? 1 : m.n - 1)) % m.n;
        at += d > 0 ? m.widths[idx]/2 + gap + m.widths[next]/2 : -(m.widths[next]/2 + gap + m.widths[idx]/2);
        idx = next;
      }
      s.goal = at; s.mode = 'spring';
    };

    // pointer
    const down = e => {
      const [x, y] = local(e);
      s.downX = x; s.downY = y; s.dragging = false; s.down = true;
      s.startPos = s.pos; s.samples = [{x, t: performance.now()}];
      s.interactedAt = performance.now();
      if (Math.abs(s.vel) > 40) { s.goal = s.pos; s.vel = 0; }
    };
    const move = e => {
      const [x] = local(e);
      s.pointerX = x;
      if (!s.down) return;
      const dx = x - s.downX;
      if (!s.dragging && Math.abs(dx) > 6) { s.dragging = true; s.downX = x; s.startPos = s.pos; closeFocus(); }
      if (s.dragging) {
        s.pos = s.startPos - (x - s.downX);
        s.goal = s.pos; s.vel = 0;
        const now = performance.now();
        s.samples.push({x, t: now});
        while (s.samples.length > 2 && now - s.samples[0].t > 100) s.samples.shift();
      }
    };
    const up = e => {
      if (!s.down) return; s.down = false;
      const m = metrics();
      s.interactedAt = performance.now();
      if (s.dragging) {
        s.dragging = false;
        const now = performance.now();
        const f = s.samples[0], l = s.samples[s.samples.length - 1];
        let v = 0;
        if (f && l && l.t > f.t && now - l.t < 70) v = -((l.x - f.x) / (l.t - f.t)) * 1000;
        s.vel = v;
        s.goal = snap(m, s.pos + v * 0.3);
        if (Math.abs(v) > 400 && Math.abs(s.goal - s.pos) < 1) step(m, v > 0 ? 1 : -1);
        s.mode = 'spring';
        return;
      }
      if (closeFocus()) return;
      const [x, y] = local(e);
      const hit = hitTest(m, x, y);
      if (hit < 0) return;
      if (hit === nearest(m, s.pos) && Math.abs(s.goal - s.pos) < 2) {
        onSelect?.(hit, items[hit]);
        if (focusOnClick) openFocus(hit);
      } else {
        s.goal = snap(m, s.pos + (m.centers[hit] - s.pos - W/2));
        s.goal = snap(m, s.pos + wrap(m.centers[hit] - s.pos, m.loop));
        s.mode = 'spring';
      }
    };
    const wheel = e => {
      if (e.ctrlKey) return;
      const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      if (Math.abs(d) < 1) return;
      e.preventDefault();
      s.interactedAt = performance.now();
      closeFocus();
      s.goal += Math.max(-120, Math.min(120, d)) * 1.2;
      s.mode = 'wheel'; s.wheelAt = performance.now();
    };
    const key = e => {
      const m = metrics();
      if (e.key === 'ArrowRight') { e.preventDefault(); closeFocus(); step(m, 1); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); closeFocus(); step(m, -1); }
      else if (e.key === 'Escape') { if (closeFocus()) e.preventDefault(); }
      else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        if (closeFocus()) return;
        const i = nearest(m, s.pos);
        onSelect?.(i, items[i]);
        if (focusOnClick) openFocus(i);
      }
    };
    const openFocus = i => { s.focusIndex = i; s.focusTarget = 1; };
    const closeFocus = () => { if (s.focusTarget === 0) return false; s.focusTarget = 0; return true; };

    const hitTest = (m, x, y) => {
      for (let i = 0; i < m.n; i++) {
        const rel = wrap(m.centers[i] - s.pos, m.loop);
        const cx = W/2 + rel;
        const cy = H/2 + curveY(rel);
        const w = m.widths[i], h = m.cardH;
        if (x >= cx - w/2 && x <= cx + w/2 && y >= cy - h/2 && y <= cy + h/2) return i;
      }
      return -1;
    };

    const curveY = rel => {
      const t = clamp01(Math.abs(rel) / (W * 0.55));
      const dir = curl === 'rise' ? -1 : curl === 'fall' ? 1 : (rel < 0 ? 1 : -1);
      return dir * bend * H * 0.32 * t * t;
    };

    container.addEventListener('pointerdown', down);
    container.addEventListener('pointermove', move);
    container.addEventListener('pointerup', up);
    container.addEventListener('pointerleave', () => { s.pointerX = -999; });
    container.addEventListener('wheel', wheel, { passive: false });
    container.addEventListener('keydown', key);

    const frame = now => {
      if (!alive) return;
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      const m = metrics();
      if (m.n === 0) return;

      if (s.mode === 'wheel' && now - s.wheelAt > 150) { s.goal = snap(m, s.goal); s.mode = 'spring'; }
      if (!s.dragging) {
        const k = s.mode === 'wheel' ? 80 : 55;
        const c = 2 * Math.sqrt(k);
        const acc = k * (s.goal - s.pos) - c * s.vel;
        s.vel += acc * dt; s.pos += s.vel * dt;
        if (Math.abs(s.goal - s.pos) < 0.05 && Math.abs(s.vel) < 0.5) { s.pos = s.goal; s.vel = 0; }
      }
      // keep goal snapped near valid range so first card centers on load
      if (!s.initialized) {
        s.initialized = true;
        s.goal = snap(m, 0);
        s.pos = s.goal;
      }
      if (Math.abs(s.pos) > m.loop * 8) { const sh = Math.round(s.pos / m.loop) * m.loop; s.pos -= sh; s.goal -= sh; }

      // intro
      if (!s.introDone && s.ready) {
        if (s.introT >= 1) s.introDone = true;
        else s.introT = Math.min(1, s.introT + dt / 1.8);
      }

      // energy for squeeze
      const travel = Math.abs(s.vel);
      const eT = reduced ? 0 : Math.min(travel / 2600, 1);
      s.energy += (eT - s.energy) * (1 - Math.exp(-dt / (eT > s.energy ? 0.07 : 0.35)));

      // focus spring
      const fk = 64;
      s.focusV = (s.focusV || 0) + (fk * (s.focusTarget - s.focusT) - 2*Math.sqrt(fk)*(s.focusV||0)) * dt;
      s.focusT += (s.focusV||0) * dt;
      if (Math.abs(s.focusTarget - s.focusT) < 0.001 && Math.abs(s.focusV||0) < 0.001) { s.focusT = s.focusTarget; s.focusV = 0; }

      const cur = nearest(m, s.pos);
      if (cur !== s.activeIndex) { s.activeIndex = cur; setActive(cur); onChange?.(cur, items[cur]); }

      // autoplay
      if (autoplay && !reduced && s.introDone && s.focusT < 0.01 && !s.down && now - s.interactedAt > 3000 && now - s.autoplayAt > interval * 1000) {
        s.autoplayAt = now; step(m, 1);
      }

      // draw
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      const shrink = 1 - clamp01(squeeze) * s.energy;
      const focusEase = easeInOut(s.focusT);
      const introEase = easeOut(s.introT);

      const draws = [];
      for (let i = 0; i < m.n; i++) {
        const rel = wrap(m.centers[i] - s.pos, m.loop);
        if (Math.abs(rel) - m.widths[i]/2 > W + 60) continue;
        const introDelay = Math.min(Math.abs(rel) / (W * 0.7), 1) * 0.35;
        const local = s.introDone ? 1 : clamp01((s.introT - introDelay) / 0.6);
        const iEase = easeOut(local);
        let x = W/2 + rel;
        let y = H/2 + curveY(rel) + (1 - iEase) * H * 0.5;
        let scale = shrink * (0.6 + 0.4 * iEase);
        let alpha = iEase;
        if (focusEase > 0) {
          if (i === s.focusIndex) {
            const fs = Math.max(1, Math.min(1.5, (H * 0.86) / m.cardH, (W * 0.9) / m.widths[i]));
            scale *= 1 + (fs - 1) * focusEase;
            y = H/2 + curveY(rel) * (1 - focusEase);
          } else {
            const part = easeInOut(focusEase * 1.3 - Math.min(Math.abs(rel)/W,1) * 0.3);
            x += Math.sign(rel) * part * W * 0.7;
            alpha *= 1 - part;
          }
        }
        if (alpha <= 0.005) continue;
        draws.push({ i, x, y, w: m.widths[i]*scale, h: m.cardH*scale, alpha, rel });
      }
      draws.sort((a, b) => Math.abs(b.rel) - Math.abs(a.rel));

      for (const d of draws) {
        const img = s.images[d.i];
        ctx.save();
        ctx.globalAlpha = d.alpha;
        const rx = d.x - d.w/2, ry = d.y - d.h/2;
        const rr = Math.min(radius, d.w/2, d.h/2);
        ctx.beginPath();
        ctx.moveTo(rx + rr, ry);
        ctx.arcTo(rx + d.w, ry, rx + d.w, ry + d.h, rr);
        ctx.arcTo(rx + d.w, ry + d.h, rx, ry + d.h, rr);
        ctx.arcTo(rx, ry + d.h, rx, ry, rr);
        ctx.arcTo(rx, ry, rx + d.w, ry, rr);
        ctx.closePath();
        if (img && img.naturalWidth) {
          ctx.clip();
          const ia = img.naturalWidth / img.naturalHeight, ca = d.w / d.h;
          let sw = img.naturalWidth, sh = img.naturalHeight, sx = 0, sy = 0;
          if (ia > ca) { sw = sh * ca; sx = (img.naturalWidth - sw) / 2; }
          else { sh = sw / ca; sy = (img.naturalHeight - sh) / 2; }
          ctx.drawImage(img, sx, sy, sw, sh, rx, ry, d.w, d.h);
        } else {
          ctx.fillStyle = '#dfe6d2';
          ctx.fill();
        }
        ctx.restore();
      }
    };
    raf = requestAnimationFrame(frame);

    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      container.removeEventListener('pointerdown', down);
      container.removeEventListener('pointermove', move);
      container.removeEventListener('pointerup', up);
      container.removeEventListener('wheel', wheel);
      container.removeEventListener('keydown', key);
    };
  }, [items, cardHeight, gap, radius, bend, curl, squeeze, intro, focusOnClick, autoplay, interval]);

  const current = items[active];
  return (
    <div
      ref={ref}
      className={`flex-carousel ${className}`}
      role="region"
      aria-roledescription="carousel"
      aria-label="运动分类"
      tabIndex={0}
    >
      <canvas ref={canvasRef} aria-hidden="true" />
      {captions && current && (
        <div className="flex-carousel__caption" aria-hidden="true">
          <span key={active} className="flex-carousel__title">
            {current.title}
            {current.subtitle && <span className="flex-carousel__subtitle">{current.subtitle}</span>}
          </span>
          <span className="flex-carousel__count">
            {String(active + 1).padStart(2, '0')} / {String(items.length).padStart(2, '0')}
          </span>
        </div>
      )}
    </div>
  );
};

export default FlexCarousel;
