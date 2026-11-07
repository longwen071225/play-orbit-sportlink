import { useRef } from "react";
import "./LetterSwap3D.css";

export default function LetterSwap3D({ text = "", back = "", className = "" }) {
  const rootRef = useRef(null);
  const backs = Array.from(back);

  const reset = () => {
    const root = rootRef.current;
    if (!root) return;
    root.querySelectorAll(".ls3d-letter").forEach((el) => {
      el.style.setProperty("--flip", "0deg");
    });
  };

  const handleMove = (event) => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const root = rootRef.current;
    if (!root) return;
    root.querySelectorAll(".ls3d-letter").forEach((el) => {
      const rect = el.getBoundingClientRect();
      const center = rect.left + rect.width / 2;
      const middle = rect.top + rect.height / 2;
      const reach = Math.max(56, rect.width * 1.8);
      const distance = Math.hypot(
        event.clientX - center,
        event.clientY - middle,
      );
      const strength = Math.max(0, 1 - distance / reach);
      el.style.setProperty("--flip", strength > 0.42 ? "180deg" : "0deg");
    });
  };

  return (
    <span
      ref={rootRef}
      className={`ls3d ${className}`.trim()}
      aria-label={text}
      onPointerMove={handleMove}
      onPointerLeave={reset}
    >
      <span className="sr-only">{text}</span>
      {text.split(" ").map((word, wordIndex, words) => (
        <span
          className="ls3d-word"
          key={`${word}-${wordIndex}`}
          aria-hidden="true"
        >
          {Array.from(word).map((char, charIndex) => {
            const index =
              words
                .slice(0, wordIndex)
                .reduce((sum, item) => sum + item.length + 1, 0) + charIndex;
            const backChar = backs[index];
            return (
              <span className="ls3d-letter" key={`${char}-${index}`}>
                <span className="ls3d-inner">
                  <span className="ls3d-face ls3d-front">{char}</span>
                  <span className="ls3d-face ls3d-back">
                    {backChar && backChar !== " " ? backChar : char}
                  </span>
                </span>
              </span>
            );
          })}
        </span>
      ))}
    </span>
  );
}
