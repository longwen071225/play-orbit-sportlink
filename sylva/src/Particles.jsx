import { useEffect, useRef, useState } from 'react';
import './Particles.css';

const Particles = ({
  particleCount = 120,
  particleColors = ['#86A94C', '#B5D66E', '#9FC9BA', '#FFC600'],
  speed = 0.6,
  glow = 0.8,
  twinkle = 0.7,
  connections = true,
  hoverEffect = 'parallax',
  lightMode = true,
  opacity = 0.75,
  className = '',
  style = {}
}) => {
  const canvasRef = useRef(null);
  const animationRef = useRef(null);
  const particlesRef = useRef([]);
  const mouseRef = useRef({ x: 0, y: 0, active: 0 });
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: true });
    let width = canvas.offsetWidth;
    let height = canvas.offsetHeight;

    const resize = () => {
      width = canvas.offsetWidth || 800;
      height = canvas.offsetHeight || 600;
      canvas.width = width;
      canvas.height = height;
      setDimensions({ width, height });
    };

    resize();
    window.addEventListener('resize', resize);

    // Initialize particles
    const colors = particleColors;
    const particles = [];
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        size: Math.random() * 3.5 + 1.2,
        speedX: (Math.random() - 0.5) * speed * 0.6,
        speedY: (Math.random() - 0.5) * speed * 0.6,
        color: colors[Math.floor(Math.random() * colors.length)],
        alpha: Math.random() * 0.6 + 0.4,
        twinkleSpeed: Math.random() * 0.04 + 0.02,
        twinklePhase: Math.random() * Math.PI * 2,
        connectionStrength: Math.random()
      });
    }
    particlesRef.current = particles;

    let frame = 0;
    const animate = () => {
      ctx.clearRect(0, 0, width, height);
      const mouse = mouseRef.current;
      const time = frame * 0.016;

      // Update and draw particles
      for (let p of particles) {
        p.x += p.speedX;
        p.y += p.speedY;

        // Bounce off edges
        if (p.x < 0 || p.x > width) p.speedX *= -1;
        if (p.y < 0 || p.y > height) p.speedY *= -1;

        // Gentle mouse influence
        if (mouse.active > 0.1) {
          const dx = mouse.x - p.x;
          const dy = mouse.y - p.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 180 && dist > 0.1) {
            const force = (180 - dist) / 180 * 0.8 * mouse.active;
            p.x -= dx / dist * force * 0.6;
            p.y -= dy / dist * force * 0.6;
          }
        }

        // Twinkle
        const twinkle = Math.sin(time * p.twinkleSpeed + p.twinklePhase) * 0.5 + 0.5;
        const alpha = p.alpha * (0.6 + twinkle * twinkle * 0.4);

        ctx.save();
        ctx.globalAlpha = alpha * opacity;
        ctx.fillStyle = p.color;
        ctx.shadowBlur = glow * 12;
        ctx.shadowColor = p.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * (0.8 + twinkle * 0.6), 0, Math.PI * 2);
        ctx.fill();

        // Extra sparkle
        if (twinkle > 0.85) {
          ctx.shadowBlur = 25;
          ctx.fillRect(p.x - 0.8, p.y - 0.8, 1.6, 1.6);
        }
        ctx.restore();
      }

      // Connections (constellation lines)
      if (connections) {
        ctx.strokeStyle = lightMode ? 'rgba(134, 169, 76, 0.13)' : 'rgba(181, 214, 110, 0.18)';
        ctx.lineWidth = 0.9;
        for (let i = 0; i < particles.length; i++) {
          const p1 = particles[i];
          for (let j = i + 1; j < particles.length; j++) {
            const p2 = particles[j];
            const dx = p1.x - p2.x;
            const dy = p1.y - p2.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            if (distance < 110) {
              const alpha = (1 - distance / 110) * 0.25 * p1.connectionStrength;
              ctx.globalAlpha = alpha * opacity;
              ctx.beginPath();
              ctx.moveTo(p1.x, p1.y);
              ctx.lineTo(p2.x, p2.y);
              ctx.stroke();
            }
          }
        }
        ctx.globalAlpha = 1.0;
      }

      frame++;
      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    const handleMouseMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      mouseRef.current.x = e.clientX - rect.left;
      mouseRef.current.y = e.clientY - rect.top;
      mouseRef.current.active = 1.0;
    };

    const handleMouseLeave = () => {
      mouseRef.current.active = 0;
    };

    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      cancelAnimationFrame(animationRef.current);
      window.removeEventListener('resize', resize);
      canvas.removeEventListener('mousemove', handleMouseMove);
      canvas.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, [particleCount, particleColors, speed, glow, twinkle, connections, hoverEffect, lightMode, opacity]);

  return (
    <canvas
      ref={canvasRef}
      className={`particles-canvas ${className}`}
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 1,
        pointerEvents: 'auto',
        mixBlendMode: lightMode ? 'multiply' : 'screen',
        ...style
      }}
      aria-hidden="true"
    />
  );
};

export default Particles;
