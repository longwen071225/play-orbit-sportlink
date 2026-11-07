import { memo, useEffect, useRef } from 'react';
import { Mail } from 'lucide-react';
import './ProfileCard.css';

const THEMES = {
  dark: {
    '--pc-frame': 'rgba(38, 35, 46, 0.66)',
    '--pc-frame-edge': 'rgba(255, 255, 255, 0.08)',
    '--pc-frame-highlight': 'rgba(255, 255, 255, 0.07)',
    '--pc-frame-shadow': '0 22px 44px -20px rgba(0,0,0,0.8), 0 6px 16px -8px rgba(0,0,0,0.5)',
    '--pc-tile': 'linear-gradient(180deg, #3a3644 0%, #27242f 100%)',
    '--pc-tile-edge': 'rgba(255,255,255,0.07)',
    '--pc-tile-highlight': 'rgba(255,255,255,0.12)',
    '--pc-tile-shadow': '0 4px 10px -4px rgba(0,0,0,0.7)',
    '--pc-ink': '#f4f4f5',
    '--pc-muted': 'rgba(244,244,245,0.6)',
    '--pc-hover': 'brightness(1.12)',
    '--pc-press': 'brightness(0.8)',
    '--pc-shade': 'rgba(0,0,0,0.4)'
  },
  light: {
    '--pc-frame': 'rgba(255, 255, 255, 0.72)',
    '--pc-frame-edge': 'rgba(24, 24, 27, 0.07)',
    '--pc-frame-highlight': 'rgba(255, 255, 255, 0.95)',
    '--pc-frame-shadow': '0 22px 44px -22px rgba(60,80,40,0.22), 0 6px 16px -10px rgba(60,80,40,0.14)',
    '--pc-tile': 'linear-gradient(180deg, #ffffff 0%, #f4f7ee 100%)',
    '--pc-tile-edge': 'rgba(60, 80, 40, 0.1)',
    '--pc-tile-highlight': 'rgba(255, 255, 255, 1)',
    '--pc-tile-shadow': '0 4px 10px -5px rgba(60,80,40,0.18)',
    '--pc-ink': '#26321c',
    '--pc-muted': 'rgba(38, 50, 28, 0.6)',
    '--pc-hover': 'brightness(0.97)',
    '--pc-press': 'brightness(0.92)',
    '--pc-shade': 'rgba(60, 80, 40, 0.12)'
  }
};

const FOILS = {
  dark: { '--pc-blend': 'color-dodge', '--pc-holo-filter': 'hue-rotate(0deg)', '--pc-sheen': 'rgba(255,255,255,0.16)' },
  light: { '--pc-blend': 'multiply', '--pc-holo-filter': 'invert(1) hue-rotate(180deg)', '--pc-sheen': 'rgba(255,255,255,0)' }
};

const GRAIN = `url("data:image/svg+xml,${encodeURIComponent(
  "<svg xmlns='http://www.w3.org/2000/svg' width='500' height='500'><filter id='g' x='0' y='0' width='100%' height='100%' color-interpolation-filters='sRGB'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0.55 0 0 0 -0.24 0.55 0 0 0 -0.24 0.55 0 0 0 -0.24 0 0 0 0 1'/></filter><rect width='100%' height='100%' filter='url(#g)'/></svg>"
)}")`;

const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

const ProfileCard = ({
  avatarUrl = '',
  iconUrl,
  miniAvatarUrl,
  name = '',
  title = '',
  handle = '',
  status = '',
  statusColor = '#22c55e',
  contactText = 'Contact',
  showUserInfo = true,
  onContactClick,
  theme = 'dark',
  backdropColor,
  radius = 16,
  holo = 0.8,
  glare = 0.5,
  enableTilt = true,
  tiltStrength = 12,
  parallax = 8,
  intro = true,
  className = ''
}) => {
  const rootRef = useRef(null);
  const engineRef = useRef(null);
  const settingsRef = useRef({ enableTilt, tiltStrength, parallax, intro });
  settingsRef.current = { enableTilt, tiltStrength, parallax, intro };

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const size = { width: root.offsetWidth, height: root.offsetHeight };
    const x = { p: 0, v: 0, target: 0 };
    const y = { p: 0, v: 0, target: 0 };
    const light = { p: 0, target: 0 };
    let raf = 0, last = 0, slowUntil = 0, touchId = null;

    const write = () => {
      const { enableTilt: tiltOn, tiltStrength: strength, parallax: depth } = settingsRef.current;
      const angle = tiltOn && !reduced ? strength : 0;
      const tilt = Math.min(1, Math.hypot(x.p, y.p));
      const st = root.style;
      st.setProperty('--pc-light-x', `${((x.p + 1) * 0.5 * size.width).toFixed(1)}px`);
      st.setProperty('--pc-light-y', `${((y.p + 1) * 0.5 * size.height).toFixed(1)}px`);
      st.setProperty('--pc-pointer-x', `${((x.p + 1) * 50).toFixed(2)}%`);
      st.setProperty('--pc-pointer-y', `${((y.p + 1) * 50).toFixed(2)}%`);
      st.setProperty('--pc-band-x', `${(50 + x.p * 15).toFixed(2)}%`);
      st.setProperty('--pc-band-y', `${(50 + y.p * 15).toFixed(2)}%`);
      st.setProperty('--pc-rotate-x', `${(y.p * angle).toFixed(3)}deg`);
      st.setProperty('--pc-rotate-y', `${(-x.p * angle).toFixed(3)}deg`);
      st.setProperty('--pc-shift-x', `${(x.p * (reduced ? 0 : depth)).toFixed(2)}px`);
      st.setProperty('--pc-shift-y', `${(y.p * (reduced ? 0 : depth)).toFixed(2)}px`);
      st.setProperty('--pc-reach', tilt.toFixed(4));
      st.setProperty('--pc-tilt', (tilt * light.p).toFixed(4));
      st.setProperty('--pc-active', light.p.toFixed(4));
    };

    const frame = now => {
      const dt = Math.min(0.05, (now - last) / 1000 || 0);
      last = now;
      const slow = now < slowUntil;
      const stiffness = slow ? 24 : 120;
      const damping = slow ? 9 : 16;
      const steps = Math.max(1, Math.ceil(dt / (1 / 120)));
      const h = dt / steps;
      for (let i = 0; i < steps; i++) {
        for (const a of [x, y]) {
          a.v += (stiffness * (a.target - a.p) - damping * a.v) * h;
          a.p += a.v * h;
        }
      }
      const tau = light.target > light.p ? 0.18 : slow ? 0.9 : 0.45;
      light.p += (light.target - light.p) * (1 - Math.exp(-dt / tau));
      write();
      const moving =
        Math.abs(x.target - x.p) > 0.0005 || Math.abs(y.target - y.p) > 0.0005 ||
        Math.abs(x.v) > 0.0005 || Math.abs(y.v) > 0.0005 ||
        Math.abs(light.target - light.p) > 0.002;
      if (moving) raf = requestAnimationFrame(frame);
      else { x.p = x.target; y.p = y.target; light.p = light.target; write(); raf = 0; }
    };

    const wake = () => { if (raf) return; last = performance.now(); raf = requestAnimationFrame(frame); };
    const aim = (nx, ny, on = true) => {
      x.target = clamp(nx, -1, 1); y.target = clamp(ny, -1, 1);
      light.target = on ? 1 : 0; slowUntil = 0; wake();
    };
    const aimAt = e => {
      const r = root.getBoundingClientRect();
      if (!r.width || !r.height) return;
      aim(((e.clientX - r.left) / r.width) * 2 - 1, ((e.clientY - r.top) / r.height) * 2 - 1);
    };
    const release = () => aim(0, 0, false);
    const onEnter = e => { if (e.pointerType === 'mouse') aimAt(e); };
    const onMove = e => { if (e.pointerType === 'mouse' || e.pointerId === touchId) aimAt(e); };
    const onLeave = e => { if (e.pointerType === 'mouse') release(); };
    const onDown = e => { if (e.pointerType === 'mouse') return; touchId = e.pointerId; aimAt(e); };
    const onUp = e => { if (e.pointerId !== touchId) return; touchId = null; release(); };

    root.addEventListener('pointerenter', onEnter);
    root.addEventListener('pointermove', onMove);
    root.addEventListener('pointerleave', onLeave);
    root.addEventListener('pointerdown', onDown);
    root.addEventListener('pointerup', onUp);
    root.addEventListener('pointercancel', onUp);

    const observer = new ResizeObserver(() => {
      size.width = root.offsetWidth; size.height = root.offsetHeight; write();
    });
    observer.observe(root);
    engineRef.current = { aim, release, write };

    if (settingsRef.current.intro && !reduced) {
      x.p = 0.62; y.p = -0.55; light.p = 1;
      slowUntil = performance.now() + 1400;
      write(); wake();
    } else write();

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      root.removeEventListener('pointerenter', onEnter);
      root.removeEventListener('pointermove', onMove);
      root.removeEventListener('pointerleave', onLeave);
      root.removeEventListener('pointerdown', onDown);
      root.removeEventListener('pointerup', onUp);
      root.removeEventListener('pointercancel', onUp);
      engineRef.current = null;
    };
  }, []);

  useEffect(() => { engineRef.current?.write(); }, [enableTilt, tiltStrength, parallax]);

  const palette = theme === 'light' ? 'light' : 'dark';
  const backdrop = backdropColor
    ? `linear-gradient(180deg, color-mix(in srgb, ${backdropColor}, #ffffff 12%) 0%, color-mix(in srgb, ${backdropColor}, #000000 18%) 100%)`
    : 'var(--pc-tile)';

  return (
    <div
      ref={rootRef}
      className={`profile-card ${className}`.trim()}
      style={{
        ...THEMES[palette], ...FOILS[palette === 'dark' ? 'dark' : 'light'],
        '--pc-radius': `${Math.max(0, radius)}px`,
        '--pc-backdrop': backdrop,
        '--pc-holo': clamp(holo, 0, 1),
        '--pc-glare': clamp(glare, 0, 1),
        '--pc-parallax': `${Math.max(0, parallax)}px`,
        '--pc-status': statusColor,
        '--pc-grain': GRAIN,
        '--pc-pattern': iconUrl ? `url("${iconUrl}")` : 'linear-gradient(#000, #000)',
        '--pc-pattern-size': iconUrl ? '180% auto' : '100% 100%',
        '--pc-holo-gain': iconUrl ? 1.25 : 0.75,
        '--pc-holo-detail': iconUrl && palette === 'dark' ? 1 : 0
      }}
    >
      <div className="profile-card__body">
        <div className="profile-card__tile">
          <span className="profile-card__sheen" />
          <span className="profile-card__holo">
            <span className="profile-card__holo-glow" />
            <span className="profile-card__holo-shift" />
          </span>
          {avatarUrl && (
            <img className="profile-card__photo" src={avatarUrl} alt={name || ''} loading="lazy" draggable={false} />
          )}
          {(name || title) && (
            <>
              <span className="profile-card__scrim" />
              <div className="profile-card__info">
                {name && <h3 className="profile-card__name">{name}</h3>}
                {title && <p className="profile-card__title">{title}</p>}
              </div>
            </>
          )}
          <span className="profile-card__tile-rim" />
        </div>
        {showUserInfo && (
          <div className="profile-card__footer">
            {miniAvatarUrl && (
              <span className="profile-card__avatar">
                <img src={miniAvatarUrl} alt="" loading="lazy" draggable={false} />
              </span>
            )}
            <div className="profile-card__meta">
              {handle && <span className="profile-card__handle">@{handle}</span>}
              {status && <span className="profile-card__status">{status}</span>}
            </div>
            {contactText && (
              <button type="button" className="profile-card__contact" onClick={onContactClick}
                aria-label={name ? `${contactText} ${name}` : contactText}>
                <Mail size={16} strokeWidth={1.8} />
                {contactText}
              </button>
            )}
          </div>
        )}
        <span className="profile-card__glare" />
        <span className="profile-card__shade" />
        <span className="profile-card__rim" />
      </div>
    </div>
  );
};

export default memo(ProfileCard);
