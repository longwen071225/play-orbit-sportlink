import { useEffect, useRef } from 'react';
import './Rolodex.css';

const FACES = ['front', 'bottom', 'back', 'top'];

const Rolodex = ({ items = [], size = 50, className = '' }) => {
  const cubeRef = useRef(null);

  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced && cubeRef.current) {
      cubeRef.current.style.animation = 'none';
      cubeRef.current.style.transform = 'rotateX(0deg)';
    }
  }, []);

  const faces = FACES.map((f, i) => items[i % items.length] || {});

  return (
    <div className={`rolodex ${className}`} style={{ '--rolo-size': `${size}vh` }}>
      <div className="rolodex__scene">
        <div className="rolodex__cube" ref={cubeRef}>
          {faces.map((item, i) => (
            <figure key={FACES[i]} className={`rolodex__face rolodex__face--${FACES[i]}`}>
              {item.src && <img src={item.src} alt={item.alt || item.title || ''} loading="lazy" />}
              {item.title && <figcaption>{item.title}</figcaption>}
            </figure>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Rolodex;
