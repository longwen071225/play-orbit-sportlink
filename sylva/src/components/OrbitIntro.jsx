import { useEffect, useState } from "react";
import { Orbit } from "lucide-react";
import "./OrbitIntro.css";

const WORD = "PLAY ORBIT";

export default function OrbitIntro() {
  const [phase, setPhase] = useState("play");

  useEffect(() => {
    const skipParam = new URLSearchParams(location.search).get("intro") === "0";
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (skipParam || reduce) {
      setPhase("gone");
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    let finished = false;

    const finish = () => {
      if (finished) return;
      finished = true;
      setPhase("gone");
      document.body.style.overflow = previousOverflow;
    };

    const out = window.setTimeout(() => setPhase("out"), 2050);
    const done = window.setTimeout(finish, 2750);
    const skip = () => {
      window.clearTimeout(out);
      window.clearTimeout(done);
      finish();
    };

    window.addEventListener("keydown", skip);
    window.addEventListener("pointerdown", skip);

    return () => {
      window.clearTimeout(out);
      window.clearTimeout(done);
      window.removeEventListener("keydown", skip);
      window.removeEventListener("pointerdown", skip);
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  if (phase === "gone") return null;

  return (
    <div className={`orbit-intro orbit-intro--${phase}`} aria-hidden="true">
      <div className="orbit-intro__glow" />
      <div className="orbit-intro__inner">
        <span className="orbit-intro__mark">
          <Orbit size={34} strokeWidth={1.3} />
        </span>
        <div className="orbit-intro__word">
          {WORD.split("").map((char, index) => (
            <span
              key={`${char}-${index}`}
              style={{ animationDelay: `${180 + index * 52}ms` }}
            >
              {char === " " ? "\u00A0" : char}
            </span>
          ))}
        </div>
        <span className="orbit-intro__sub">
          跃星 · 让每一次运动，都有星光回应
        </span>
        <span className="orbit-intro__line" />
      </div>
    </div>
  );
}
