import {
  createContext,
  lazy,
  Suspense,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  ArrowUpRight,
  ArrowRight,
  ArrowLeft,
  ChevronDown,
  Check,
  CheckCircle2,
  X,
  Search,
  Sparkles,
  Orbit,
  CalendarDays,
  MapPin,
  ShieldCheck,
  UserRound,
  LogOut,
  Menu,
  BookOpen,
  Plus,
  Users,
  MessageCircle,
  Star,
  RefreshCw,
  AlertCircle,
  LoaderCircle,
  Pause,
  Play,
  Camera,
} from "lucide-react";
import { api } from "./api.js";
const Universe = lazy(() => import("./Universe.jsx"));
import FlexCarousel from "./components/FlexCarousel.jsx";
import ProfileCard from "./components/ProfileCard.jsx";
import ScrollExpand from "./components/ScrollExpand.jsx";
import OrbitIntro from "./components/OrbitIntro.jsx";
import LetterSwap3D from "./components/LetterSwap3D.jsx";
const Context = createContext(null);
const useApp = () => useContext(Context);
function canLeave() {
  return window.dispatchEvent(
    new Event("orbit:before-navigate", { cancelable: true }),
  );
}
function navigate(to) {
  if (!canLeave()) return;
  history.pushState({}, "", to);
  dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo({ top: 0, behavior: "instant" });
}
function Link({
  to,
  children,
  className = "",
  protect = false,
  onClick,
  ...props
}) {
  const app = useApp();
  return (
    <a
      href={to}
      className={className}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        onClick?.(e);
        if (protect && !app.state.loggedIn)
          navigate("/login?next=" + encodeURIComponent(to));
        else navigate(to);
      }}
      {...props}
    >
      {children}
    </a>
  );
}
const Arrow = () => <ArrowUpRight size={18} />;
const money = (n) =>
  new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
  }).format(n);
const formatDate = (date) =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    timeZone: "Asia/Shanghai",
  }).format(new Date(date + "T12:00:00+08:00"));
function futureDates() {
  return Array.from({ length: 10 }, (_, i) => {
    const d = new Date(Date.now() + (i + 1) * 86400000);
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(d);
  });
}
const sports = [
  {
    name: "篮球",
    en: "BASKETBALL",
    image: "basketball.jpg",
    desc: "从第一次投篮，到爱上球场。",
  },
  {
    name: "游泳",
    en: "SWIMMING",
    image: "swimming.jpg",
    desc: "在水的世界，发现新的勇气。",
  },
  {
    name: "足球",
    en: "FOOTBALL",
    image: "football.jpg",
    desc: "一起奔跑，也一起成长。",
  },
  {
    name: "体能",
    en: "MOVEMENT",
    image: "training.jpg",
    desc: "探索身体，收获小小进步。",
  },
  {
    name: "骑行",
    en: "CYCLING",
    image: "cycling.jpg",
    desc: "追着风，找到自己的节奏。",
  },
  {
    name: "田径",
    en: "ATHLETICS",
    image: "athletics.jpg",
    desc: "从起跑线出发，跑出自己的速度。",
  },
];
const articles = [
  {
    title: "从“要我运动”，到“我想试试”",
    tag: "运动启蒙",
    image: "basketball.jpg",
    time: "3 分钟阅读",
    text: "把选择权交给孩子，是开始运动的一小步。一起观察不同的运动场景，问问孩子最想尝试什么。第一节体验课可以只设一个目标：找到一件让自己开心的小事。比起完成了几个动作，更值得聊聊的是“今天哪个瞬间最好玩”。",
  },
  {
    title: "第一次入水，先和水交朋友",
    tag: "游泳入门",
    image: "swimming.jpg",
    time: "4 分钟阅读",
    text: "先熟悉场地和教练，再慢慢尝试呼吸与水感练习。让孩子知道可以随时表达感受，所有水中练习都应在具备资质的教练及监护人看护下进行。放下进度期待，把安全与舒适放在第一位。",
  },
  {
    title: "课后的十分钟，留给一起回味",
    tag: "家庭陪伴",
    image: "football.jpg",
    time: "2 分钟阅读",
    text: "不急着问学会了什么，可以先聊聊今天认识了谁、最想再尝试什么。记录一句孩子自己的话，把运动变成可以分享的回忆。下一次练习遵循教练安排，在轻松、安全的环境中进行。",
  },
];
function Empty({ title, text, children }) {
  return (
    <div className="empty-state">
      <Orbit size={36} strokeWidth={1} />
      <h3>{title}</h3>
      <p>{text}</p>
      {children}
    </div>
  );
}
function Busy({ text = "正在准备你的运动旅程…" }) {
  return (
    <div className="busy">
      <LoaderCircle className="spin" size={25} />
      <span>{text}</span>
    </div>
  );
}
function SectionHead({ eyebrow, title, children }) {
  return (
    <div className="section-head">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {children}
    </div>
  );
}
function Modal({ title, children, onClose, drawer = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    el.showModal();
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={drawer ? "dialog drawer" : "dialog"}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      aria-label={title}
    >
      <div className="dialog-inner">
        <div className="dialog-head">
          <span className="eyebrow">{title}</span>
          <button
            className="icon-button"
            aria-label="关闭详情"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
function AcidEffects() {
  return (
    <>
      <svg className="effect-defs" aria-hidden="true">
        <defs>
          <filter id="acid-grain">
            <feTurbulence
              type="fractalNoise"
              baseFrequency=".72"
              numOctaves="3"
              stitchTiles="stitch"
            />
          </filter>
          <filter id="acid-wave" x="-10%" y="-10%" width="120%" height="120%">
            <feTurbulence
              type="fractalNoise"
              baseFrequency=".006 .014"
              numOctaves="2"
              seed="3"
              result="noise"
            />
            <feDisplacementMap
              in="SourceGraphic"
              in2="noise"
              scale="5"
              xChannelSelector="R"
              yChannelSelector="B"
            />
          </filter>
        </defs>
      </svg>
      <svg className="acid-noise" aria-hidden="true">
        <rect width="100%" height="100%" filter="url(#acid-grain)" />
      </svg>
      <span className="acid-side-label" aria-hidden="true">
        NO LIMITS / JUST PLAY — EST. 2026
      </span>
    </>
  );
}
function Header() {
  const { state, child, route, act, motionPaused, toggleMotion } = useApp();
  const [open, setOpen] = useState(false),
    [childrenOpen, setChildrenOpen] = useState(false);
  useEffect(() => {
    setOpen(false);
    setChildrenOpen(false);
  }, [route]);
  const links = [
    ["/", "发现"],
    ["/coaches", "找教练"],
    ["/agent", "AI 运动顾问"],
    ["/universe", "成长星图"],
  ];
  const navRef = useRef(null);
  const [hovered, setHovered] = useState(-1);
  const [pill, setPill] = useState(null);
  const activeIndex = links.findIndex(([to]) => route.split("?")[0] === to);

  const syncPill = () => {
    const nav = navRef.current;
    if (!nav) return;
    const items = nav.querySelectorAll("a");
    const target = items[hovered >= 0 ? hovered : activeIndex];
    if (!target) {
      setPill(null);
      return;
    }
    const navBox = nav.getBoundingClientRect();
    const box = target.getBoundingClientRect();
    setPill({ left: box.left - navBox.left, width: box.width });
  };

  useEffect(() => {
    syncPill();
  }, [activeIndex, hovered, route]);

  useEffect(() => {
    const nav = navRef.current;
    const sync = () => syncPill();
    const observer = new ResizeObserver(sync);
    if (nav) {
      observer.observe(nav);
      nav.querySelectorAll("a").forEach((link) => observer.observe(link));
    }
    window.addEventListener("resize", sync);
    document.fonts?.ready.then(sync);
    document.fonts?.addEventListener?.("loadingdone", sync);
    const early = window.setTimeout(sync, 120);
    const settled = window.setTimeout(sync, 500);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", sync);
      document.fonts?.removeEventListener?.("loadingdone", sync);
      window.clearTimeout(early);
      window.clearTimeout(settled);
    };
  }, [activeIndex, hovered]);

  return (
    <>
      <header className="header nav-header">
        <div className="nav-pill">
          <Link to="/" className="brand">
            <Orbit size={31} strokeWidth={1.25} />
            <span className="brand-name">
              跃星<small>PLAY ORBIT</small>
            </span>
            <span className="brand-live" aria-hidden="true" />
          </Link>
          <nav
            className="desktop-nav"
            aria-label="主导航"
            ref={navRef}
            onMouseLeave={() => setHovered(-1)}
          >
            <span
              className="nav-indicator"
              aria-hidden="true"
              style={
                pill
                  ? {
                      transform: `translateX(${pill.left}px)`,
                      width: `${pill.width}px`,
                    }
                  : { opacity: 0 }
              }
            />
            {links.map(([to, label], index) => {
              const isActive = route.split("?")[0] === to;
              const isLit = hovered >= 0 ? hovered === index : isActive;
              return (
                <Link
                  key={to}
                  to={to}
                  protect={to === "/agent" || to === "/universe"}
                  onMouseEnter={() => setHovered(index)}
                  onFocus={() => setHovered(index)}
                  onBlur={() => setHovered(-1)}
                  className={
                    "nav-link" +
                    (isActive ? " is-current" : "") +
                    (isLit ? " is-lit" : "")
                  }
                >
                  {label}
                  {to === "/universe" && state.events?.length > 0 && (
                    <i className="notification-dot" />
                  )}
                </Link>
              );
            })}
          </nav>
          <div className="header-actions">
            <button
              className="motion-toggle"
              aria-label={motionPaused ? "启用装饰动效" : "暂停装饰动效"}
              aria-pressed={motionPaused}
              onClick={toggleMotion}
            >
              {motionPaused ? <Play size={15} /> : <Pause size={15} />}
              <span>{motionPaused ? "动效已暂停" : "暂停动效"}</span>
            </button>
            {state.loggedIn ? (
              <>
                <div className="child-menu">
                  <button
                    className="child-trigger"
                    aria-expanded={childrenOpen}
                    onClick={() => setChildrenOpen(!childrenOpen)}
                  >
                    <span className="avatar small">{child?.avatar}</span>
                    <span>{child?.name}</span>
                    <ChevronDown size={14} />
                  </button>
                  {childrenOpen && (
                    <div className="dropdown">
                      {state.children.map((c) => (
                        <button
                          key={c.id}
                          onClick={async () => {
                            if (c.id !== child.id)
                              await act("/active-child", {
                                method: "PUT",
                                body: { childId: c.id },
                              }).catch(() => {});
                            setChildrenOpen(false);
                          }}
                        >
                          <span className="avatar small">{c.avatar}</span>
                          {c.name}
                          <small>{c.age} 岁</small>
                          {c.id === child.id && <Check size={15} />}
                        </button>
                      ))}
                      <Link to="/profile">
                        儿童档案
                        <Arrow />
                      </Link>
                      <button
                        onClick={async () => {
                          if (!canLeave()) return;
                          try {
                            await act("/logout", { method: "POST" });
                            location.assign("/");
                          } catch {}
                        }}
                      >
                        <LogOut size={16} />
                        退出演示家庭
                      </button>
                    </div>
                  )}
                </div>
                <Link to="/orders" className="header-course">
                  我的课程
                  <Arrow size={15} />
                </Link>
              </>
            ) : (
              <Link to="/login" className="button small-button">
                开始探索
                <Arrow />
              </Link>
            )}
            <button
              className="menu-button icon-button"
              aria-label="打开导航菜单"
              onClick={() => setOpen(!open)}
            >
              {open ? <X /> : <Menu />}
            </button>
          </div>
        </div>
      </header>
      {open && (
        <nav className="mobile-menu" aria-label="展开导航">
          {links.map(([to, label]) => (
            <Link
              key={to}
              to={to}
              protect={to === "/agent" || to === "/universe"}
            >
              {label}
              <Arrow />
            </Link>
          ))}
          <Link to="/profile" protect>
            儿童档案
            <Arrow />
          </Link>
          <Link to="/orders" protect>
            我的课程
            <Arrow />
          </Link>
        </nav>
      )}
    </>
  );
}
function Footer() {
  return (
    <footer className="footer">
      <div className="footer-top">
        <Link to="/" className="brand">
          <Orbit size={32} />
          <span className="brand-name">
            跃星<small>PLAY ORBIT</small>
          </span>
        </Link>
        <p>
          给每一份热爱，
          <br />
          一个自由生长的宇宙。
        </p>
        <div>
          <Link to="/coaches">
            发现教练
            <Arrow />
          </Link>
          <Link to="/profile" protect>
            孩子的运动手册
            <Arrow />
          </Link>
          <Link to="/tasks" protect>
            家庭练习
            <Arrow />
          </Link>
        </div>
        <div className="footer-links">
          <span className="footer-label">平台功能</span>
          {[
            ["教练 / 管理端", "/coach-app"],
            ["AI 运动陪练", "/motion-coach"],
            ["演示控制台", "/demo"],
            ["API 文档", "/docs"],
          ].map(([label, path]) => (
            <a key={path} href={path} target="_blank" rel="noreferrer">
              {label}
              <Arrow />
            </a>
          ))}
        </div>
      </div>
      <div className="footer-bottom">
        <span>© 2026 PLAY ORBIT · MADE FOR LITTLE BIG DREAMS.</span>
        <span>人物、课程、资质与评价均为演示资料</span>
        <a href="/demo" target="_blank" rel="noreferrer">
          演示控制台 ↗
        </a>
      </div>
    </footer>
  );
}
function CoachCard({ coach, reason }) {
  return (
    <article className="coach-card">
      <Link to={"/coaches/" + coach.id} className="coach-image">
        <img
          src={"/images/" + coach.image}
          alt={`${coach.name}教练的演示肖像`}
          loading="lazy"
        />
        <span className="image-tag">
          {coach.sport} / {coach.age}
        </span>
        <span className="image-arrow">
          <Arrow />
        </span>
      </Link>
      <div className="coach-meta">
        <h3>
          <Link to={"/coaches/" + coach.id}>
            {coach.name}
            <small>{coach.english}</small>
          </Link>
        </h3>
        <span>{coach.experience} 年教学经验*</span>
      </div>
      <p>{coach.tag}</p>
      {reason && (
        <p className="recommend-reason">
          <Sparkles size={13} />
          {reason}
        </p>
      )}
      <div className="coach-bottom">
        <span>
          {money(coach.price)} <small>/ 45 分钟</small>
        </span>
        <Link to={"/coaches/" + coach.id}>
          查看课程
          <ArrowRight size={15} />
        </Link>
      </div>
    </article>
  );
}
function Reveal({ children, className = "" }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add("is-visible");
          observer.disconnect();
        }
      },
      { threshold: 0.22 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={ref} className={`reveal ${className}`.trim()}>
      {children}
    </div>
  );
}
function Home() {
  const { state, child, act, notify } = useApp();
  const [detail, setDetail] = useState(null);
  const [showDemo, setShowDemo] = useState(true);
  useEffect(() => {
    const onScroll = () => setShowDemo(window.scrollY < 220);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const startDemo = async () => {
    try {
      await act("/login", { method: "POST" });
      navigate("/agent?demo=1");
    } catch (error) {
      notify(error.message);
    }
  };
  const example = [
    { id: "example-1", title: "第一次勇敢上场", sport: "篮球" },
    { id: "example-2", title: "平衡小达人", sport: "体能" },
    { id: "example-3", title: "第一次团队配合", sport: "足球" },
  ];
  return (
    <>
      <ScrollExpand
        useWindowScroll
        mediaType="video"
        src="/videos/hero.mp4"
        poster="/images/hero-poster.jpg"
        title={<LetterSwap3D text="PLAY BEYOND" back="PLAY ORBIT" />}
        scrollHint="SCROLL · 向下滚动，展开宇宙"
        startWidth={46}
        startHeight={60}
        startRadius={28}
        endRadius={0}
        mediaZoom={1.3}
        scrollDistance={0.82}
        holdDistance={0.12}
        smoothing={0.12}
        overlayScrim={0.7}
        className="home-scroll-expand"
      >
        <div className="scroll-hero-content">
          <span className="eyebrow">
            <Sparkles size={15} /> NEXT GENERATION / SPORTS & GROWTH
          </span>
          <h1>
            让每一次运动，
            <br />
            <em>都有星光回应。</em>
          </h1>
          <p>
            发现喜欢的运动，遇见懂孩子的教练。
            <br />
            让每一次勇敢尝试，成为成长宇宙里的一颗星。
          </p>
          <div className="scroll-hero-actions">
            <Link to="/agent" protect className="button">
              问问 AI 运动顾问
              <Arrow />
            </Link>
            <Link to="/universe" protect className="scroll-hero-link">
              探索成长星图
              <Arrow />
            </Link>
          </div>
          <span className="scroll-hero-note">
            [ LOCAL EXPERIENCE / 演示数据 ]
          </span>
        </div>
      </ScrollExpand>
      <button
        className={`hero-demo-cta${showDemo ? "" : " is-hidden"}`}
        onClick={startDemo}
      >
        <span className="hero-demo-dot" />
        一键示例 · 走一遍完整流程
        <ArrowUpRight size={16} />
      </button>
      <section className="home-universe-section">
        <div className="wrap">
          <div className="universe-stage-head">
            <span className="eyebrow">PERSONAL GROWTH UNIVERSE</span>
            <h2>
              {state.loggedIn
                ? `${child?.name}的个人成长宇宙。`
                : "每个孩子，都有一座个人成长宇宙。"}
            </h2>
            <p>每一次尝试，都会在自己的宇宙里点亮一颗星。</p>
          </div>
          <Reveal className="universe-reveal">
            <div className="hero-universe universe-stage">
              <Suspense fallback={<Busy text="正在展开成长宇宙…" />}>
                <Universe
                  compact
                  childName={child?.name || "小小探索者"}
                  stars={state.loggedIn ? state.stars : example}
                  onSelect={() =>
                    state.loggedIn
                      ? navigate("/universe")
                      : navigate("/login?next=/universe")
                  }
                />
              </Suspense>
            </div>
          </Reveal>
        </div>
      </section>
      <div className="belief-strip wrap">
        <span>从一小步，走向无限可能。</span>
        <span>
          <ShieldCheck size={18} />
          看见每个孩子的节奏
        </span>
        <span>
          <Users size={18} />
          找到适合的运动伙伴
        </span>
        <span>
          <Orbit size={18} />
          把成长连成一片星海
        </span>
      </div>
      <section className="section wrap">
        <SectionHead
          eyebrow="01 / FIND THEIR THING"
          title={<>热爱，从好奇开始。</>}
        >
          <Link to="/coaches" className="text-link">
            探索所有运动
            <Arrow />
          </Link>
        </SectionHead>
        <div className="sport-carousel-wrap">
          <FlexCarousel
            items={sports.map((s) => ({
              src: "/images/" + s.image,
              title: s.name + " · " + s.en,
              subtitle: s.desc,
              alt: s.name + "运动场景",
            }))}
            cardHeight={0.6}
            gap={22}
            radius={20}
            bend={0.5}
            curl="twist"
            squeeze={0.25}
            intro="rise"
            captions
            onSelect={(i) =>
              navigate("/coaches?sport=" + encodeURIComponent(sports[i].name))
            }
          />
        </div>
      </section>
      <section className="section coach-section">
        <div className="wrap">
          <SectionHead
            eyebrow="02 / THE RIGHT PERSON, THE RIGHT START"
            title="陪伴比指令，更有力量。"
          >
            <Link to="/coaches" className="text-link">
              认识更多教练
              <Arrow />
            </Link>
          </SectionHead>
          <div className="coach-grid">
            {state.coaches.slice(0, 3).map((coach) => (
              <ProfileCard
                key={coach.id}
                avatarUrl={"/images/" + coach.image}
                name={coach.name}
                title={`${coach.sport} / ${coach.age} · ${coach.experience}年经验`}
                handle={coach.english.toLowerCase().replace(/\s+/g, "")}
                status={`¥${coach.price}/45分钟`}
                statusColor="#9cbf5e"
                contactText="查看课程"
                theme="light"
                holo={0.85}
                glare={0.45}
                tiltStrength={11}
                parallax={7}
                radius={20}
                intro
                onContactClick={() => navigate("/coaches/" + coach.id)}
              />
            ))}
          </div>
          <p className="data-note">
            * 教练人物、经验和课程均为合成演示资料，不代表真实服务。
          </p>
        </div>
      </section>
      <section className="growth-story section wrap">
        <div className="story-photo">
          <img
            src="/images/growth-medal.jpg"
            alt="一枚记录成长的奖牌"
            loading="lazy"
          />
          <span className="image-tag">SMALL STEPS. REAL GROWTH.</span>
        </div>
        <div className="story-copy">
          <span className="eyebrow">03 / EVERY EFFORT COUNTS</span>
          <h2>
            成长不是一场比较。
            <br />
            是每次，多一点勇敢。
          </h2>
          <p>
            第一次走上球场，第一次主动传球，
            <br />
            或是今天比昨天更愿意再试一次。
            <br />
            这些值得被记住的小事，都在这里闪耀。
          </p>
          <Link to="/universe" protect className="text-link">
            打开孩子的成长宇宙
            <Arrow />
          </Link>
        </div>
      </section>
      <section className="section wrap">
        <SectionHead eyebrow="04 / FIELD NOTES" title="运动之外，也一起成长。">
          <Link to="/videos" className="text-link">
            运动灵感
            <Arrow />
          </Link>
        </SectionHead>
        <div className="article-grid">
          {articles.map((a, i) => (
            <button
              className="article-card"
              key={a.title}
              onClick={() => setDetail(i)}
            >
              <div>
                <img src={"/images/" + a.image} alt="" loading="lazy" />
                <span className="article-read">
                  <BookOpen size={20} />
                </span>
              </div>
              <span className="eyebrow">
                {a.tag} · {a.time}
              </span>
              <h3>{a.title}</h3>
            </button>
          ))}
        </div>
      </section>
      {detail !== null && (
        <ArticleModal
          article={articles[detail]}
          onClose={() => setDetail(null)}
        />
      )}
      <Pricing />
    </>
  );
}

function Pricing() {
  const [sessions, setSessions] = useState(8);
  const [openPlan, setOpenPlan] = useState(null);
  const tiers = [
    {
      name: "体验",
      en: "START",
      price: 198,
      unit: "/ 单次",
      note: "先见一面，再决定。",
      fit: "适合第一次接触运动、需要建立安全感的孩子。",
      rhythm: "1 次 · 45 分钟",
      features: ["1 次体验课", "运动兴趣测评", "教练沟通反馈"],
      featured: false,
    },
    {
      name: "成长",
      en: "GROWTH",
      price: 1680,
      unit: "/ 10 次",
      note: "把喜欢，慢慢变成习惯。",
      fit: "适合已经找到兴趣，准备持续练习的孩子。",
      rhythm: "10 次 · 每周 2–3 次",
      features: [
        "10 次系统课程",
        "成长星图点亮",
        "每课成长记录",
        "家庭练习任务",
      ],
      featured: true,
    },
    {
      name: "陪伴",
      en: "ORBIT",
      price: 3980,
      unit: "/ 30 次",
      note: "长期同行，稳稳成长。",
      fit: "适合有长期目标、需要阶段评估的家庭。",
      rhythm: "30 次 · 每周 2–3 次",
      features: [
        "30 次长期陪伴",
        "专属成长规划",
        "阶段能力报告",
        "亲子运动指导",
      ],
      featured: false,
    },
  ];
  const perClass = 168;
  const estimate = sessions * perClass;
  return (
    <section className="pricing-section">
      <div className="pricing-glow" aria-hidden="true" />
      <div className="wrap">
        <SectionHead eyebrow="05 / PLANS" title="按节奏，选择陪伴方式。">
          <span className="text-link">演示价格 · 非真实支付</span>
        </SectionHead>
        <Reveal className="pricing-reveal">
          <div className="pricing-grid">
            {tiers.map((t) => (
              <article
                key={t.en}
                className={`pricing-card ${t.featured ? "featured" : "glass"}${
                  openPlan === t.en ? " is-open" : ""
                }`}
              >
                {t.featured && <span className="plan-flag">推荐</span>}
                <span className="pricing-en mono">{t.en}</span>
                <h3>{t.name}</h3>
                <p className="pricing-note">{t.note}</p>
                <p className="pricing-price">
                  ¥{t.price.toLocaleString()}
                  <small>{t.unit}</small>
                </p>
                <Link
                  to="/coaches"
                  className={t.featured ? "button" : "button secondary"}
                >
                  {t.featured ? "开始体验" : "了解详情"}
                  <ArrowRight size={15} />
                </Link>
                <ul className="pricing-features">
                  {t.features.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
                <button
                  className="plan-toggle"
                  aria-expanded={openPlan === t.en}
                  onClick={() => setOpenPlan(openPlan === t.en ? null : t.en)}
                >
                  {openPlan === t.en ? "收起方案" : "展开方案"}
                  <ChevronDown size={14} />
                </button>
                <div className="plan-detail">
                  <p>{t.fit}</p>
                  <span>{t.rhythm}</span>
                </div>
              </article>
            ))}
          </div>
        </Reveal>
        <div className="pricing-calc">
          <div className="calc-copy">
            <span className="eyebrow">ESTIMATE</span>
            <h4>想上几次课？</h4>
            <p>拖动看看大概预算（按 ¥{perClass}/课估算，演示数据）。</p>
          </div>
          <div className="calc-body">
            <input
              type="range"
              min="4"
              max="40"
              step="2"
              value={sessions}
              onChange={(e) => setSessions(Number(e.target.value))}
              aria-label="课程次数"
            />
            <div className="calc-result">
              <strong>{sessions} 次课</strong>
              <span>约 ¥{estimate.toLocaleString()}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
function Login() {
  const { state, act } = useApp();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const next = new URLSearchParams(location.search).get("next") || "/agent";
  return (
    <section className="auth-page wrap">
      <div className="auth-photo">
        <img src="/images/basketball.jpg" alt="篮球场上的一次尝试" />
        <div>
          <span className="eyebrow">WELCOME TO PLAY ORBIT</span>
          <h2>
            一小步，
            <br />
            也是一颗星。
          </h2>
        </div>
      </div>
      <div className="auth-form">
        <span className="eyebrow">YOUR JOURNEY STARTS HERE</span>
        <h1>你好，运动伙伴。</h1>
        <p>和孩子一起，发现属于你们的运动宇宙。</p>
        <div className="demo-box">
          <Orbit size={23} />
          <div>
            <strong>探索演示家庭</strong>
            <p>
              小宇 · 8 岁 / 朵朵 · 6 岁<br />
              无需手机号，不涉及真实支付。
            </p>
          </div>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button
          disabled={busy}
          className="button wide"
          onClick={async () => {
            setBusy(true);
            try {
              if (!state.loggedIn) await act("/login", { method: "POST" });
              navigate("/children/select?next=" + encodeURIComponent(next));
            } catch (e) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? (
            <LoaderCircle className="spin" size={18} />
          ) : (
            <>
              进入演示家庭
              <Arrow />
            </>
          )}
        </button>
        <p className="data-note">
          这是本地体验账号。课程、教练与儿童资料均为演示数据；会话及操作通过本地
          API 持久化。
        </p>
        <Link to="/" className="text-link">
          先逛一逛
          <Arrow />
        </Link>
      </div>
    </section>
  );
}
function Children() {
  const { state, act } = useApp();
  const [selected, setSelected] = useState(state.activeChildId),
    [busy, setBusy] = useState(false),
    [adding, setAdding] = useState(false),
    [creating, setCreating] = useState(false),
    [formError, setFormError] = useState(""),
    [form, setForm] = useState({
      nickname: "",
      age: "",
      interests: "",
      goals: "",
    });
  const next = new URLSearchParams(location.search).get("next") || "/";
  const createChild = async () => {
    const nickname = form.nickname.trim();
    const age = Number(form.age);
    if (!nickname) return setFormError("请填写孩子昵称");
    if (!age || age < 3 || age > 18)
      return setFormError("请填写 3–18 岁的年龄");
    setCreating(true);
    setFormError("");
    try {
      const result = await act("/children", {
        method: "POST",
        body: {
          nickname,
          age,
          sportsInterests: form.interests.split(/[、,，\s]+/).filter(Boolean),
          trainingGoals: form.goals.split(/[、,，\s]+/).filter(Boolean),
        },
      });
      if (result.created?.id) setSelected(result.created.id);
      setAdding(false);
      setForm({ nickname: "", age: "", interests: "", goals: "" });
    } catch (error) {
      setFormError(error.message);
    } finally {
      setCreating(false);
    }
  };
  return (
    <section className="select-child wrap">
      <span className="eyebrow">ONE FAMILY. DIFFERENT UNIVERSES.</span>
      <h1>今天，陪谁一起探索？</h1>
      <p>每个孩子的兴趣、课程与成长，都有自己的轨道。</p>
      <div className="children-grid">
        {state.children.map((c) => (
          <button
            key={c.id}
            className={`child-card ${selected === c.id ? "selected" : ""}`}
            onClick={() => setSelected(c.id)}
          >
            <span className="avatar large" style={{ background: c.color }}>
              {c.avatar}
            </span>
            <h2>
              {c.name}
              <small>{c.age} 岁</small>
            </h2>
            <p>{c.sports.join(" · ")}</p>
            <span className="selection-check">
              {selected === c.id ? <Check size={18} /> : <Plus size={18} />}
            </span>
          </button>
        ))}
        <button
          className="child-card child-add"
          onClick={() => setAdding(true)}
        >
          <Plus size={22} />
          添加孩子
        </button>
      </div>
      <button
        className="button"
        disabled={busy || !selected}
        onClick={async () => {
          setBusy(true);
          try {
            await act("/active-child", {
              method: "PUT",
              body: { childId: selected },
            });
            navigate(
              next.startsWith("/") && !next.startsWith("//") ? next : "/",
            );
          } catch {
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "正在切换…" : "开始这段旅程"}
        <Arrow />
      </button>
      {adding && (
        <Modal title="新增儿童档案" onClose={() => setAdding(false)}>
          <div className="child-form">
            <label>
              昵称
              <input
                value={form.nickname}
                onChange={(e) => setForm({ ...form, nickname: e.target.value })}
                placeholder="如 小辰"
              />
            </label>
            <label>
              年龄
              <input
                type="number"
                min="3"
                max="18"
                value={form.age}
                onChange={(e) => setForm({ ...form, age: e.target.value })}
                placeholder="如 7"
              />
            </label>
            <label>
              运动兴趣
              <input
                value={form.interests}
                onChange={(e) =>
                  setForm({ ...form, interests: e.target.value })
                }
                placeholder="如 跳绳、平衡训练"
              />
              <small>用顿号或逗号分隔</small>
            </label>
            <label>
              训练目标
              <input
                value={form.goals}
                onChange={(e) => setForm({ ...form, goals: e.target.value })}
                placeholder="如 协调性、耐力"
              />
              <small>可留空</small>
            </label>
            {formError && (
              <p className="error" role="alert">
                {formError}
              </p>
            )}
            <button
              className="button"
              disabled={creating}
              onClick={createChild}
            >
              {creating ? "正在保存…" : "保存档案"}
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}
function Coaches() {
  const { state, child } = useApp();
  const initial = new URLSearchParams(location.search).get("sport") || "全部";
  const [sport, setSport] = useState(initial),
    [q, setQ] = useState(""),
    [age, setAge] = useState(false),
    [sort, setSort] = useState("recommended"),
    [area, setArea] = useState("全部地区"),
    [budget, setBudget] = useState("all");
  useEffect(() => setSport(initial), [initial]);
  const coaches = state.coaches
    .filter(
      (c) =>
        (sport === "全部" || c.sport === sport) &&
        (!q || [c.name, c.sport, c.tag, c.area].join("").includes(q)) &&
        (!age || !child || (child.age >= c.minAge && child.age <= c.maxAge)) &&
        (area === "全部地区" || c.area === area) &&
        (budget === "all" || c.price <= 200),
    )
    .sort((a, b) => (sort === "price" ? a.price - b.price : 0));
  const reset = () => {
    setQ("");
    setSport("全部");
    setAge(false);
    setArea("全部地区");
    setBudget("all");
  };
  return (
    <section className="page wrap">
      <div className="page-intro">
        <span className="eyebrow">GOOD COACHES. GREAT BEGINNINGS.</span>
        <h1>找到懂孩子的教练。</h1>
        <p>有耐心、有方法，也愿意陪孩子慢慢找到热爱。</p>
      </div>
      <div className="search-row">
        <div className="search-field">
          <Search size={20} />
          <input
            aria-label="搜索教练"
            placeholder="搜索教练、运动或教学特点"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          {q && (
            <button
              className="icon-button"
              aria-label="清空搜索"
              onClick={() => setQ("")}
            >
              <X size={16} />
            </button>
          )}
        </div>
        <select
          aria-label="排序"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="recommended">推荐排序</option>
          <option value="price">价格从低到高</option>
        </select>
      </div>
      <div className="filter-row">
        <div className="chips">
          {["全部", ...sports.map((s) => s.name)].map((s) => (
            <button
              key={s}
              onClick={() => setSport(s)}
              className={sport === s ? "chip selected" : "chip"}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="filter-selects">
          <select
            aria-label="地区"
            value={area}
            onChange={(e) => setArea(e.target.value)}
          >
            {["全部地区", "徐汇区", "浦东新区", "静安区"].map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
          <select
            aria-label="价格区间"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
          >
            <option value="all">全部价格</option>
            <option value="under200">¥200 以内</option>
          </select>
          {child && (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={age}
                onChange={(e) => setAge(e.target.checked)}
              />
              适合{child.name}
            </label>
          )}
        </div>
      </div>
      <div className="results-label">
        <span>找到 {coaches.length} 位运动伙伴</span>
        <span className="mono">MOVE WITH SOMEONE WHO CARES.</span>
      </div>
      {coaches.length ? (
        <div className="coach-grid listing">
          {coaches.map((c) => (
            <CoachCard key={c.id} coach={c} />
          ))}
        </div>
      ) : (
        <Empty title="换个条件，再找找看。" text="暂时没有符合这些条件的教练。">
          <button className="button" onClick={reset}>
            清空筛选
            <RefreshCw size={16} />
          </button>
        </Empty>
      )}
      <p className="data-note">
        本目录为合成演示内容。可预约时间以课程确认页的实时演示时段为准。
      </p>
    </section>
  );
}
function CoachDetail({ id }) {
  const { state } = useApp();
  const coach = state.coaches.find((c) => c.id === id);
  const [lesson, setLesson] = useState(0);
  if (!coach) return <NotFound />;
  const service = coach.services[lesson];
  return (
    <section className="page wrap">
      <Link to="/coaches" className="back-link">
        <ArrowLeft size={16} />
        所有教练
      </Link>
      <div className="coach-detail-hero">
        <div className="detail-portrait">
          <img
            src={"/images/" + coach.image}
            alt={`${coach.name}教练演示肖像`}
          />
          <span className="image-tag">
            {coach.sport} · {coach.age}
          </span>
        </div>
        <div className="detail-identity">
          <span className="eyebrow">MEET YOUR NEXT TEAMMATE</span>
          <h1>
            {coach.name}
            <small>{coach.english}</small>
          </h1>
          <h2>{coach.title}</h2>
          <p>{coach.bio}</p>
          <div className="detail-facts">
            <span>
              <strong>
                {coach.experience}
                <small>年</small>
              </strong>
              教学经验*
            </span>
            <span>
              <strong>{coach.age}</strong>适合年龄
            </span>
            <span>
              <strong>
                {service?.durationMinutes ?? "—"}<small>分钟</small>
              </strong>
              每次课程
            </span>
          </div>
          <div className="credential-row">
            {coach.badges.map((b) => (
              <span key={b}>
                <ShieldCheck size={16} />
                {b}*
              </span>
            ))}
          </div>
          <p className="data-note">* 经验、人物及资质为演示设定。</p>
        </div>
      </div>
      <div className="detail-content">
        <div>
          <span className="eyebrow">THE FIRST STEP</span>
          <h2>从一节喜欢的课开始。</h2>
          <div className="course-options">
            {coach.services.map((option, i) => (
              <button
                key={option.id}
                className={`course-option ${lesson === i ? "selected" : ""}`}
                onClick={() => setLesson(i)}
              >
                <span className="radio-mark">
                  {lesson === i && <Check size={12} />}
                </span>
                <div>
                  <h3>{option.title}</h3>
                  <p>
                    {option.ageMin}–{option.ageMax} 岁 · 1 对 1 · {option.durationMinutes} 分钟 · {coach.area}
                  </p>
                </div>
                <strong>{money(option.priceYuan)}</strong>
              </button>
            ))}
          </div>
          <div className="teaching-note">
            <h3>课堂上，我们更在意什么？</h3>
            <p>
              尊重孩子的感受，关注每一次主动尝试。课程从热身和兴趣游戏开始，按当天的状态安排练习，课后留下具体的训练反馈。
            </p>
            <h3>预约前的小提醒</h3>
            <p>
              请准备舒适的运动服和饮用水。预约后与教练沟通孩子的基础和需求；如身体不适，请暂停训练并先咨询专业人员。
            </p>
          </div>
        </div>
        {service && <aside className="booking-aside">
          <span className="eyebrow">MAKE THE FIRST MOVE</span>
          <h3>{service.title}</h3>
          <p>
            {coach.name} · {coach.sport}
          </p>
          <div className="price-big">
            {money(service.priceYuan)}
            <small>/ {service.durationMinutes} 分钟</small>
          </div>
          <ul className="clean-list">
            <li>
              <UserRound size={17} />
              {service.ageMin}–{service.ageMax} 岁 · 专属 1 对 1
            </li>
            <li>
              <MapPin size={17} />
              上海 · {coach.area}
            </li>
            <li>
              <CalendarDays size={17} />
              选择未来 10 天的演示时段
            </li>
          </ul>
          <Link
            to={`/booking?coach=${coach.id}&lesson=${lesson}`}
            protect
            className="button wide"
          >
            选择课程与时间
            <Arrow />
          </Link>
          <p className="data-note">
            本地演示预约，不产生真实收费。上课前可取消演示预约。
          </p>
        </aside>}
      </div>
    </section>
  );
}
function Booking() {
  const { state, child, act } = useApp();
  const params = new URLSearchParams(location.search);
  const coachId = params.get("coach") || state.coaches[0]?.id;
  const coach = state.coaches.find((c) => c.id === coachId);
  const [lesson, setLesson] = useState(Number(params.get("lesson")) || 0),
    [step, setStep] = useState(0),
    [date, setDate] = useState(futureDates()[0]),
    [time, setTime] = useState(""),
    [slots, setSlots] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [result, setResult] = useState(null);
  const service = coach?.services[lesson] || coach?.services[0];
  const duration = service?.durationMinutes;
  const choosingTime = step === 1;
  const bookingAttempt = useRef(null);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [step, result]);
  useEffect(() => {
    if (!coachId || !service?.id || !choosingTime) return;
    let active = true;
    setSlots(null);
    const query = new URLSearchParams({ coachId, date, durationMinutes: duration });
    api(`/availability?${query}`)
      .then((data) => {
        if (active) setSlots(data.slots);
      })
      .catch((e) => {
        if (!active) return;
        setSlots([]);
        setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [coachId, service?.id, choosingTime, date, duration]);
  if (!coach || !service) return <NotFound />;
  if (!child) return null;
  const ageEligible = child.age >= service.ageMin && child.age <= service.ageMax;
  if (result)
    return (
      <section className="confirmation wrap">
        <CheckCircle2 size={54} strokeWidth={1} />
        <span className="eyebrow">A NEW ADVENTURE AWAITS</span>
        <h1>下一次热爱，已约好。</h1>
        <p>
          {child.name}与{coach.name}教练的运动约定
        </p>
        <div className="confirmation-card">
          <h3>{result.lesson}</h3>
          <p>
            {formatDate(result.date)} · {result.time}–{result.endTime} ·
            上海时间
          </p>
          <p>上海 · {coach.area} · {result.durationMinutes} 分钟 / 1 对 1</p>
          <span className="mono break-word">
            预约号 {result.id}
          </span>
          <span className="status booked">待教练确认 · 演示未收费</span>
        </div>
        <div className="hero-actions">
          <Link to="/orders" className="button">
            查看我的课程
            <Arrow />
          </Link>
          <Link to="/agent" className="text-link">
            继续和顾问聊聊
            <Arrow />
          </Link>
        </div>
        <p className="data-note">
          课程由测试教练确认完成后，会在成长星图中生成一颗新星。
        </p>
      </section>
    );
  const submit = async () => {
    const selection = [child.id, service.id, date, time].join("|");
    if (bookingAttempt.current?.selection !== selection) {
      bookingAttempt.current = { selection, id: crypto.randomUUID() };
    }
    setBusy(true);
    setError("");
    try {
      const data = await act(
        "/bookings",
        {
          method: "POST",
          body: {
            childId: child.id,
            coachId: coach.id,
            serviceId: service.id,
            lesson: service.title,
            date,
            time,
            requestId: bookingAttempt.current.id,
          },
        },
        { silent: true },
      );
      setResult(data.order);
    } catch (e) {
      setError(e.message);
      if (e.status === 409) {
        setTime("");
        setStep(1);
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="page wrap booking-page">
      <Link to={"/coaches/" + coach.id} className="back-link">
        <ArrowLeft size={16} />
        返回教练详情
      </Link>
      <div className="page-intro">
        <span className="eyebrow">A SMALL STEP, A NEW START</span>
        <h1>给下一次尝试，留个时间。</h1>
      </div>
      <div className="booking-layout">
        <div>
          <div className="steps">
            {["课程与孩子", "选择时间", "确认预约"].map((s, i) => (
              <span
                key={s}
                className={step === i ? "active" : step > i ? "done" : ""}
              >
                <b>{step > i ? <Check size={14} /> : i + 1}</b>
                {s}
              </span>
            ))}
          </div>
          {step === 0 && (
            <div className="step-content">
              <h2>为 {child.name} 选择一段运动时间</h2>
              <div className="booking-child">
                <span className="avatar">{child.avatar}</span>
                <div>
                  <strong>
                    {child.name} · {child.age} 岁
                  </strong>
                  <p>{child.sports.join(" / ")}</p>
                </div>
                <Link
                  to={
                    "/children/select?next=" +
                    encodeURIComponent(location.pathname + location.search)
                  }
                  className="text-link"
                >
                  切换孩子
                </Link>
              </div>
              <div className="course-options">
                {coach.services.map((option, i) => (
                  <button
                    key={option.id}
                    className={`course-option ${option.id === service.id ? "selected" : ""}`}
                    onClick={() => {
                      setLesson(i);
                      setTime("");
                    }}
                  >
                    <span className="radio-mark">
                      {option.id === service.id && <Check size={12} />}
                    </span>
                    <div>
                      <h3>{option.title}</h3>
                      <p>{option.ageMin}–{option.ageMax} 岁 · {option.durationMinutes} 分钟 · 1 对 1</p>
                    </div>
                    <strong>{money(option.priceYuan)}</strong>
                  </button>
                ))}
              </div>
            </div>
          )}
          {step === 1 && (
            <div className="step-content">
              <h2>哪一天，适合一起动一动？</h2>
              <p>上海时间 UTC+8 · 可预约状态由演示服务实时校验</p>
              <div className="date-options">
                {futureDates().map((d) => (
                  <button
                    key={d}
                    className={date === d ? "selected" : ""}
                    onClick={() => {
                      setDate(d);
                      setTime("");
                      setError("");
                    }}
                  >
                    <span>
                      {new Intl.DateTimeFormat("zh-CN", {
                        weekday: "short",
                      }).format(new Date(d + "T12:00:00+08:00"))}
                    </span>
                    <strong>{d.slice(5).replace("-", "/")}</strong>
                  </button>
                ))}
              </div>
              <h3>选择时段</h3>
              {!slots ? (
                <Busy text="正在确认可约时间…" />
              ) : slots.length ? (
                <div className="time-options">
                  {slots.map((s) => (
                    <button
                      disabled={!s.available}
                      key={s.time}
                      className={s.time === time ? "selected" : ""}
                      onClick={() => setTime(s.time)}
                    >
                      {s.time}
                      <small>{s.available ? `${duration} 分钟` : "不可约"}</small>
                    </button>
                  ))}
                </div>
              ) : !error && <p>当天没有可约时段，请选择其他日期。</p>}
            </div>
          )}
          {step === 2 && (
            <div className="step-content">
              <h2>在出发之前，再确认一下。</h2>
              <dl className="review-list">
                <div>
                  <dt>孩子</dt>
                  <dd>
                    {child.name} · {child.age} 岁
                  </dd>
                </div>
                <div>
                  <dt>教练与课程</dt>
                  <dd>
                    {coach.name} · {service.title}
                  </dd>
                </div>
                <div>
                  <dt>时间</dt>
                  <dd>
                    {formatDate(date)} {time}–{endTime(time, duration)}
                    <small>Asia/Shanghai · UTC+8</small>
                  </dd>
                </div>
                <div>
                  <dt>地点</dt>
                  <dd>上海 · {coach.area}（演示场地）</dd>
                </div>
                <div>
                  <dt>费用</dt>
                  <dd>
                    {money(service.priceYuan)} / {duration} 分钟
                    <small>演示预约，不进行真实支付</small>
                  </dd>
                </div>
              </dl>
              <div className="info-box">
                <ShieldCheck size={20} />
                <p>
                  预约后可在“我的课程”查看或取消。只有在课程完成并形成训练记录后，才会点亮成长星星。
                </p>
              </div>
            </div>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="step-actions">
            {step > 0 && (
              <button
                className="button secondary"
                onClick={() => {
                  setStep(step - 1);
                  setError("");
                }}
              >
                上一步
              </button>
            )}
            <button
              className="button"
              disabled={
                busy ||
                !ageEligible ||
                (step === 1 && !slots?.some((slot) => slot.time === time && slot.available))
              }
              onClick={() => (step < 2 ? setStep(step + 1) : submit())}
            >
              {busy ? "正在确认预约结果…" : step === 2 ? "确认预约" : "下一步"}
              <ArrowRight size={17} />
            </button>
          </div>
          {!ageEligible && (
            <p className="error">本课程适合 {service.ageMin}–{service.ageMax} 岁，请选择其他课程。</p>
          )}
        </div>
        <aside className="booking-aside">
          <img
            className="summary-avatar"
            src={"/images/" + coach.image}
            alt=""
          />
          <span className="eyebrow">YOUR NEXT ADVENTURE</span>
          <h3>{service.title}</h3>
          <p>
            {coach.name} · {coach.sport}
          </p>
          <div className="price-big">
            {money(service.priceYuan)}
            <small>/ {duration} 分钟</small>
          </div>
          <p>
            {child.name} · {child.age} 岁<br />
            {step > 0 && time
              ? formatDate(date) + " " + time
              : "期待与你在球场相见。"}
          </p>
          <p className="data-note">所有课程和费用均为本地演示数据。</p>
        </aside>
      </div>
    </section>
  );
}
function endTime(t, duration) {
  const [h, m] = t.split(":").map(Number);
  const end = (h * 60 + m + duration) % 1440;
  return `${String(Math.floor(end / 60)).padStart(2, "0")}:${String(end % 60).padStart(2, "0")}`;
}
function Agent() {
  const { state, child, setState, notify } = useApp();
  const [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const control = useRef(null),
    epoch = useRef(child?.id);
  epoch.current = child?.id;
  useEffect(() => () => control.current?.abort(), [child?.id]);
  const send = async (text = input) => {
    if (!text.trim() || busy) return;
    const childId = child.id;
    control.current = new AbortController();
    setBusy(true);
    setError("");
    try {
      const data = await api("/chat", {
        method: "POST",
        signal: control.current.signal,
        body: { childId, message: text },
      });
      if (epoch.current === childId) {
        setState((s) => ({ ...s, messages: data.messages }));
        setInput("");
      }
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const messages = state.messages || [],
    last = [...messages].reverse().find((m) => m.role === "assistant");
  const demoStarted = useRef(false);
  useEffect(() => {
    const demo = new URLSearchParams(location.search).get("demo") === "1";
    if (!demo || messages.length) return;
    const timer = window.setTimeout(() => {
      if (demoStarted.current) return;
      demoStarted.current = true;
      send("孩子想体验篮球，怎样开始？");
    }, 420);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const recs = (last?.coachIds || [])
    .map((id) => state.coaches.find((c) => c.id === id))
    .filter(Boolean);
  return (
    <section className="page wrap agent-page">
      <div className="page-intro">
        <span className="eyebrow">
          A LITTLE GUIDANCE, A WORLD OF POSSIBILITIES
        </span>
        <h1>一起，找到运动的方向。</h1>
        <p>聊聊孩子的兴趣，让下一步更清楚。</p>
      </div>
      <div className="agent-layout">
        <div className="conversation">
          <div className="conversation-head">
            <span>
              <Sparkles size={19} /> AI 运动顾问
            </span>
            <span className="context-label">
              {child?.name} · {child?.age} 岁
            </span>
          </div>
          <div className="message-area" aria-live="polite">
            {!messages.length ? (
              <div className="agent-empty">
                <Orbit size={52} strokeWidth={1} />
                <h2>
                  {child?.name}的下一次热爱，
                  <br />
                  我们一起找。
                </h2>
                <p>
                  告诉我孩子的兴趣、想尝试的运动，
                  <br />
                  或是你还在犹豫的小问题。
                </p>
                <div className="suggestions">
                  {[
                    "孩子想体验篮球，怎样开始？",
                    "适合初学者的游泳课怎么选？",
                    "想让孩子更愿意参加团队运动",
                  ].map((s) => (
                    <button key={s} onClick={() => setInput(s)}>
                      {s}
                      <ArrowUpRight size={15} />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => (
                <div className={"message " + m.role} key={m.id}>
                  <span className="message-avatar">
                    {m.role === "user" ? child?.avatar : <Sparkles size={17} />}
                  </span>
                  <div>
                    <span className="message-role">
                      {m.role === "user" ? "家长" : "跃星运动顾问 · 规则演示"}
                    </span>
                    <p>{m.text}</p>
                    {m.coachIds?.map((id) => {
                      const c = state.coaches.find((c) => c.id === id);
                      return (
                        c && (
                          <Link
                            className="inline-recommendation"
                            to={"/coaches/" + c.id}
                            key={id}
                          >
                            <img src={"/images/" + c.image} alt="" />
                            <span>
                              <strong>
                                {c.name} · {c.sport}
                              </strong>
                              <small>
                                {c.age} · {money(c.price)}/45 分钟
                              </small>
                            </span>
                            <Arrow />
                          </Link>
                        )
                      );
                    })}
                  </div>
                </div>
              ))
            )}
            {busy && (
              <p className="generating">
                <LoaderCircle className="spin" size={15} />
                正在根据演示课程资料整理建议…
              </p>
            )}
          </div>
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <label className="sr-only" htmlFor="agent-question">
              向 AI 运动顾问提问
            </label>
            <textarea
              id="agent-question"
              value={input}
              maxLength={1000}
              placeholder={`关于${child?.name}的运动，你想聊些什么？`}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <div>
              <span>Enter 发送 · Shift + Enter 换行</span>
              {busy ? (
                <button
                  type="button"
                  onClick={() => {
                    control.current?.abort();
                    setBusy(false);
                  }}
                  className="send-button"
                  aria-label="停止生成"
                >
                  <X size={18} />
                </button>
              ) : (
                <button
                  className="send-button"
                  disabled={!input.trim()}
                  aria-label="发送问题"
                >
                  <ArrowUpRight size={21} />
                </button>
              )}
            </div>
          </form>
          {error && (
            <p className="error" role="alert">
              {error} <button onClick={() => send()}>重试</button>
            </p>
          )}
          <p className="data-note">
            当前为规则式演示顾问，未连接实时大模型。推荐来自演示教练目录；预约需要家长确认。
          </p>
        </div>
        <aside className="agent-sidebar">
          <a href="/motion-coach" className="motion-coach-card">
            <span className="motion-coach-icon">
              <Camera size={22} />
            </span>
            <span>
              <strong>AI 运动陪练</strong>
              <small>打开摄像头，实时动作计数与提醒</small>
            </span>
            <Arrow />
          </a>
          <span className="eyebrow">CURATED FOR YOUR CHILD</span>
          <h2>
            每一次推荐，
            <br />
            都有一点理由。
          </h2>
          <p>
            根据{child?.name}的年龄与运动兴趣，
            <br />
            从真实的演示目录中寻找伙伴。
          </p>
          {recs.length ? (
            recs.map((c) => (
              <CoachCard
                key={c.id}
                coach={c}
                reason={`课程覆盖${child?.age}岁，符合本轮运动兴趣`}
              />
            ))
          ) : (
            <div className="agent-tip">
              <BookOpen size={23} />
              <h3>先聊聊，再做选择。</h3>
              <p>发出第一个问题后，适合的教练会出现在这里。</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
const bookingStatusLabel = {
  PENDING: "待教练确认",
  ACCEPTED: "已接单",
  IN_PROGRESS: "上课中",
  COMPLETED: "已完成",
  REJECTED: "教练已拒绝",
  CANCELLED: "已取消",
};

function Orders() {
  const { state, act, child } = useApp();
  const [filter, setFilter] = useState("all"),
    [selected, setSelected] = useState(null),
    [cancelId, setCancelId] = useState(null);
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("order");
    if (id) setSelected(state.orders.find((o) => o.id === id) || null);
  }, []);
  const visible = state.orders.filter(
    (o) => filter === "all" || o.status === filter,
  );
  return (
    <section className="page wrap">
      <div className="page-intro">
        <span className="eyebrow">LITTLE PLANS, BIG POSSIBILITIES</span>
        <h1>{child?.name}的运动约定。</h1>
        <p>每一次期待，与每一段值得记住的成长。</p>
      </div>
      {state.events.length > 0 && (
        <Link to="/universe" className="new-star-banner">
          <Sparkles size={22} />
          <span>
            有 {state.events.length} 颗新星，正在等待你发现。
            <small>新的成长记录已经同步</small>
          </span>
          <Arrow />
        </Link>
      )}
      <div className="chips order-tabs">
        {[
          ["all", "全部课程"],
          ["booked", "即将上课"],
          ["completed", "已完成"],
          ["cancelled", "已取消"],
        ].map(([v, t]) => (
          <button
            key={v}
            className={"chip " + (filter === v ? "selected" : "")}
            onClick={() => setFilter(v)}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="order-list">
        {visible.length ? (
          visible.map((order) => {
            const c = state.coaches.find((c) => c.id === order.coachId);
            return (
              <article className="order-card" key={order.id}>
                <div className="order-date">
                  <strong>{order.date.slice(8)}</strong>
                  <span>{order.date.slice(0, 7).replace("-", " / ")}</span>
                </div>
                <img
                  className="order-image"
                  src={"/images/" + (c?.image || "coach-zhao.jpg")}
                  alt=""
                />
                <div className="order-info">
                  <span className="eyebrow">
                    {c ? `${c.sport} · ${c.name}教练` : "课程预约"}
                  </span>
                  <h3>{order.lesson}</h3>
                  <p>
                    {order.time}–{order.endTime} · {order.durationMinutes} 分钟
                    {c?.area && ` · ${c.area}`} · 上海时间
                  </p>
                  <small className="break-word">预约号 {order.id}</small>
                </div>
                <div className="order-actions">
                  <span className={"status " + order.status}>
                    {bookingStatusLabel[order.bookingStatus]}
                  </span>
                  <button
                    className="text-link"
                    onClick={() => setSelected(order)}
                  >
                    查看详情
                    <Arrow />
                  </button>
                  {["PENDING", "ACCEPTED"].includes(order.bookingStatus) && (
                    <button
                      className="subtle-button"
                      onClick={() => setCancelId(order.id)}
                    >
                      取消预约
                    </button>
                  )}
                </div>
              </article>
            );
          })
        ) : (
          <Empty
            title="下一次运动，还在等你安排。"
            text="为孩子找到一位合适的运动伙伴。"
          >
            <Link to="/coaches" className="button">
              探索教练
              <Arrow />
            </Link>
          </Empty>
        )}
      </div>
      {selected && (
        <OrderModal
          order={state.orders.find((o) => o.id === selected.id) || selected}
          onClose={() => setSelected(null)}
        />
      )}{" "}
      {cancelId && (
        <Modal title="取消演示预约" onClose={() => setCancelId(null)}>
          <h2>确认取消这次运动约定？</h2>
          <p>该时段会重新开放，不会产生取消费用。</p>
          <div className="hero-actions">
            <button
              className="button secondary"
              onClick={() => setCancelId(null)}
            >
              保留预约
            </button>
            <button
              className="button"
              onClick={async () => {
                try {
                  await act(`/bookings/${cancelId}/cancel`, { method: "POST" });
                  setCancelId(null);
                } catch {}
              }}
            >
              确认取消
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}
function OrderModal({ order, onClose }) {
  const { state } = useApp();
  const coach = state.coaches.find((c) => c.id === order.coachId),
    star = state.stars.find((s) => s.orderId === order.id),
    record = state.records?.find((r) => r.bookingId === order.id);
  return (
    <Modal title="课程记录 / COURSE RECORD" drawer onClose={onClose}>
      <span className={"status " + order.status}>
        {bookingStatusLabel[order.bookingStatus]}
      </span>
      <h2>{order.lesson}</h2>
      <p>
        {coach && `${coach.name} · ${coach.sport} · `}{formatDate(order.date)}
      </p>
      <dl className="review-list">
        <div>
          <dt>上课时间</dt>
          <dd>
            {order.time}–{order.endTime} · 上海时间
          </dd>
        </div>
        <div>
          <dt>课程费用</dt>
          <dd>
            {money(order.price)} / {order.durationMinutes} 分钟<small>本地演示，未真实收费</small>
          </dd>
        </div>
        <div>
          <dt>预约编号</dt>
          <dd className="break-word">{order.id}</dd>
        </div>
      </dl>
      {order.status === "completed" && (
        <>
          <h3>教练留下的成长观察</h3>
          {record ? (
            <>
              <p className="feedback-quote">
                {record.content || order.feedback}
              </p>
              {record.grade && (
                <dl className="review-list">
                  <div>
                    <dt>本次表现</dt>
                    <dd>{record.grade}</dd>
                  </div>
                </dl>
              )}
              {record.strengths && (
                <p>
                  <strong>优点：</strong>
                  {record.strengths}
                </p>
              )}
              {record.improvements && (
                <p>
                  <strong>待提升：</strong>
                  {record.improvements}
                </p>
              )}
              {record.homeSuggestion && (
                <p>
                  <strong>家庭建议：</strong>
                  {record.homeSuggestion}
                </p>
              )}
            </>
          ) : (
            <p className="feedback-quote">
              {order.feedback || "成长记录同步中，请稍后刷新。"}
            </p>
          )}
          {star ? (
            <Link
              to={"/universe?star=" + star.id}
              className="button"
              onClick={onClose}
            >
              在星图中查看
              <Arrow />
            </Link>
          ) : (
            <p>成长记录同步中，请稍后刷新。</p>
          )}
        </>
      )}
      {order.status === "booked" && (
        <div className="info-box">
          <CalendarDays size={20} />
          <p>期待下一次相见。课后由测试教练确认完成，再同步到成长星图。</p>
        </div>
      )}
    </Modal>
  );
}
function Profile() {
  const { child, state, act } = useApp();
  const [goal, setGoal] = useState(child.goal),
    [weekly, setWeekly] = useState(child.weeklyGoal),
    [busy, setBusy] = useState(false),
    [saved, setSaved] = useState(false);
  useEffect(() => {
    setGoal(child.goal);
    setWeekly(child.weeklyGoal);
    setSaved(false);
  }, [child.id]);
  const dirty = goal !== child.goal || Number(weekly) !== child.weeklyGoal;
  useEffect(() => {
    const f = (e) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    const navigation = (event) => {
      if (dirty && !window.confirm("运动目标还未保存，确定离开吗？"))
        event.preventDefault();
    };
    window.addEventListener("beforeunload", f);
    window.addEventListener("orbit:before-navigate", navigation);
    return () => {
      window.removeEventListener("beforeunload", f);
      window.removeEventListener("orbit:before-navigate", navigation);
    };
  }, [dirty]);
  return (
    <section className="page wrap">
      <div className="profile-hero">
        <div className="profile-id">
          <span
            className="avatar extra-large"
            style={{ background: child.color }}
          >
            {child.avatar}
          </span>
          <div>
            <span className="eyebrow">MY LITTLE EXPLORER</span>
            <h1>{child.name}的运动手册。</h1>
            <p>
              {child.age} 岁 · 喜欢 {child.sports.join("、")}
            </p>
          </div>
        </div>
        <Link to="/children/select?next=/profile" className="text-link">
          切换孩子
          <Arrow />
        </Link>
      </div>
      <div className="profile-layout">
        <div>
          <div className="profile-section">
            <span className="eyebrow">GROW AT YOUR OWN PACE</span>
            <h2>把愿望，写成一小步。</h2>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                try {
                  const data = await act("/profile", {
                    method: "PATCH",
                    body: { goal, weeklyGoal: Number(weekly) },
                  });
                  const updated = data.children.find(
                    (item) => item.id === child.id,
                  );
                  setGoal(updated.goal);
                  setWeekly(updated.weeklyGoal);
                  setSaved(true);
                } catch {
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label className="field-label" htmlFor="growth-goal">
                运动成长目标
              </label>
              <textarea
                id="growth-goal"
                value={goal}
                maxLength={100}
                required
                onChange={(e) => {
                  setGoal(e.target.value);
                  setSaved(false);
                }}
              />
              <div className="goal-bottom">
                <label>
                  每周想尝试{" "}
                  <select
                    aria-label="每周运动目标"
                    value={weekly}
                    onChange={(e) => {
                      setWeekly(e.target.value);
                      setSaved(false);
                    }}
                  >
                    {[1, 2, 3, 4, 5, 6, 7].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>{" "}
                  次
                </label>
                <button
                  className="button small-button"
                  disabled={busy || !dirty}
                >
                  {busy ? "保存中…" : saved ? "已保存" : "保存目标"}
                  <Check size={16} />
                </button>
              </div>
              <p className="data-note">
                按孩子的感受灵活调整。目标是一份期待，不是一项考核。
              </p>
            </form>
          </div>
          <div className="profile-section">
            <SectionHead
              eyebrow="MOMENTS WORTH KEEPING"
              title="那些小小的闪光时刻。"
            />
            <div className="record-list">
              {state.stars.length ? (
                state.stars.map((star) => (
                  <Link
                    to={"/universe?star=" + star.id}
                    className="record-item"
                    key={star.id}
                  >
                    <span className="record-icon">
                      <Star size={20} />
                    </span>
                    <div>
                      <span>
                        {star.date} · {star.sport}
                      </span>
                      <h3>{star.title}</h3>
                      <p>{star.description}</p>
                    </div>
                    <Arrow />
                  </Link>
                ))
              ) : (
                <Empty
                  title="第一段故事，正要开始。"
                  text="完成一节喜欢的课，留下第一条成长记录。"
                />
              )}
            </div>
          </div>
        </div>
        <aside className="profile-aside">
          <div className="profile-universe-preview">
            <Suspense fallback={<Busy />}>
              <Universe
                compact
                childName={child.name}
                stars={state.stars}
                onSelect={() => navigate("/universe")}
              />
            </Suspense>
          </div>
          <h3>一颗星，一次勇敢。</h3>
          <p>
            已经收藏 {state.stars.length} 个成长时刻，
            <br />
            每一颗都有自己的故事。
          </p>
          <Link to="/universe" className="button wide">
            打开成长星图
            <Arrow />
          </Link>
          <Link to="/orders" className="text-link">
            我的课程
            <Arrow />
          </Link>
          <Link to="/tasks" className="text-link">
            家庭练习
            <Arrow />
          </Link>
        </aside>
      </div>
    </section>
  );
}
function Growth() {
  const { state, child, route, refresh, notify } = useApp();
  const [sport, setSport] = useState("全部"),
    [mode, setMode] = useState("3d"),
    [selected, setSelected] = useState(null),
    [lighting, setLighting] = useState(null);
  const consumed = useRef(new Set()),
    linkedStar = useRef(null),
    ackPending = useRef(false);
  useEffect(() => {
    const id = new URLSearchParams(route.split("?")[1]).get("star");
    if (!id || id === linkedStar.current) return;
    const star = state.stars.find((s) => s.id === id);
    if (star) {
      linkedStar.current = id;
      setSelected(star);
    }
  }, [route, state.stars]);
  useEffect(() => {
    if (lighting) return;
    const event = state.events.find(
      (e) =>
        !consumed.current.has(e.eventId) &&
        state.stars.some((s) => s.id === e.nodeId),
    );
    if (event) {
      const star = state.stars.find((s) => s.id === event.nodeId);
      if (sport !== "全部" && sport !== star.sport) setSport("全部");
      setLighting(event);
    }
  }, [state.events, state.stars, sport, lighting]);
  const acknowledge = async () => {
    if (!lighting || ackPending.current) return;
    if (lighting.eventId) {
      ackPending.current = true;
      consumed.current.add(lighting.eventId);
      try {
        await api(`/growth-events/${lighting.eventId}/seen`, { method: "POST" });
        await refresh();
      } catch (error) {
        notify("星星已保存，点亮反馈将在下次进入时确认。");
      } finally {
        ackPending.current = false;
      }
    }
    setLighting(null);
  };
  const visible = state.stars
    .map((s, i) => ({ ...s, layoutIndex: i }))
    .filter((s) => sport === "全部" || s.sport === sport);
  const lightingVisible = visible.some((s) => s.id === lighting?.nodeId);
  useEffect(() => {
    if (lighting && (mode === "list" || !lightingVisible)) acknowledge();
  }, [mode, lighting, lightingVisible]);
  const records = state.records || [];
  const coachName = (id) => state.coaches.find((c) => c.id === id)?.name;
  const timeline = [
    ...visible.map((s) => ({
      kind: "star",
      date: s.date,
      id: s.id,
      title: s.title,
      sub: s.sport,
    })),
    ...records.map((r) => ({
      kind: "record",
      date: r.date,
      id: r.id,
      title: r.content.length > 24 ? r.content.slice(0, 24) + "…" : r.content,
      sub: coachName(r.coachId) || "训练记录",
    })),
  ].sort((a, b) => b.date.localeCompare(a.date));
  return (
    <section className="growth-page">
      <div className="wrap">
        <div className="growth-heading">
          <div>
            <span className="eyebrow">PERSONAL GROWTH UNIVERSE</span>
            <h1>{child.name}的个人成长宇宙。</h1>
            <p>完成训练后，你的星图就会点亮一颗新星。</p>
          </div>
          <div className="growth-mode">
            <button
              className={mode === "3d" ? "selected" : ""}
              onClick={() => setMode("3d")}
            >
              <Orbit size={16} />
              宇宙视图
            </button>
            <button
              className={mode === "list" ? "selected" : ""}
              onClick={() => setMode("list")}
            >
              <BookOpen size={16} />
              成长记录
            </button>
          </div>
        </div>
        <div className="growth-toolbar">
          <div className="chips">
            {["全部", ...new Set(state.stars.map((s) => s.sport))].map((s) => (
              <button
                key={s}
                className={"chip " + (sport === s ? "selected" : "")}
                onClick={() => setSport(s)}
              >
                {s}
              </button>
            ))}
          </div>
          <span>
            {state.stars.length} 颗成长星 ·{" "}
            {new Set(state.stars.map((s) => s.sport)).size} 个运动领域
          </span>
        </div>
        {lighting && mode === "3d" && lightingVisible && (
          <div className="lighting-banner" role="status">
            <Sparkles size={20} />
            <span>{lighting.eventId ? "一颗新星正在点亮。" : "正在重播这颗星的点亮动画。"}</span>
            <button onClick={acknowledge}>跳过动画，直接探索</button>
          </div>
        )}
        {mode === "3d" ? (
          <div className="full-universe">
            <Suspense fallback={<Busy text="正在展开你的运动宇宙…" />}>
              <Universe
                key={child.id}
                childName={child.name}
                stars={visible}
                onSelect={setSelected}
                newStarId={lighting?.nodeId}
                selectedId={selected?.id}
                onLit={acknowledge}
              />
            </Suspense>
          </div>
        ) : records.length ? (
          <div className="growth-records">
            {records.map((r) => (
              <article className="record-item record-detail" key={r.id}>
                <BookOpen size={24} />
                <div>
                  <span>
                    {r.date} · {coachName(r.coachId) || "训练记录"}
                  </span>
                  <p>{r.content}</p>
                  {r.strengths && <small>优点：{r.strengths}</small>}
                  {r.improvements && <small>待提升：{r.improvements}</small>}
                  {r.homeSuggestion && (
                    <small>家庭建议：{r.homeSuggestion}</small>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            title="第一颗星，等着你来点亮。"
            text="从一节喜欢的运动课开始。"
          >
            <Link to="/coaches" className="button">
              找一位教练
              <Arrow />
            </Link>
          </Empty>
        )}
        <div className="space-legend">
          <span>
            <Star size={13} />
            亮绿星：可查看成长记录
          </span>
          <span>
            <Orbit size={14} />
            亮色连线：同一运动领域
          </span>
          <span>淡色星群仅为背景装饰</span>
        </div>
        <div className="growth-timeline">
          <div>
            <span className="eyebrow">YOUR GROWTH, CONNECTED</span>
            <h2>回望，每一小步。</h2>
          </div>
          <div className="timeline-items">
            {timeline.length ? (
              timeline.map((item) => (
                <button
                  key={`${item.kind}-${item.id}`}
                  onClick={() => {
                    if (item.kind === "star") {
                      setSelected(state.stars.find((s) => s.id === item.id));
                    }
                  }}
                  className={item.id === lighting?.nodeId ? "new" : ""}
                >
                  <span className="timeline-date">
                    {item.date.replaceAll("-", " / ")}
                  </span>
                  <span className="timeline-mark">
                    {item.kind === "star" ? (
                      <Star size={16} />
                    ) : (
                      <BookOpen size={16} />
                    )}
                  </span>
                  <strong>{item.title}</strong>
                  <small>{item.sub}</small>
                </button>
              ))
            ) : (
              <p>这里会串起孩子未来的运动故事。</p>
            )}
          </div>
        </div>
      </div>
      {selected && (
        <StarModal
          star={selected}
          onClose={() => setSelected(null)}
          onReplay={() => {
            setSelected(null);
            setMode("3d");
            if (sport !== "全部" && sport !== selected.sport) setSport("全部");
            setLighting({ nodeId: selected.id });
          }}
        />
      )}
    </section>
  );
}
function StarModal({ star, onClose, onReplay }) {
  const { state, child } = useApp();
  const coach = state.coaches.find((c) => c.id === star.coachId),
    order = state.orders.find((o) => o.id === star.orderId),
    record = state.records.find((r) => r.id === star.recordId || (order && r.bookingId === order.id)),
    duration = star.durationMinutes || record?.durationMinutes || order?.durationMinutes;
  return (
    <Modal title="A MOMENT WORTH KEEPING" drawer onClose={onClose}>
      <span className="gold-star">
        <Star size={34} strokeWidth={1} />
      </span>
      <span className="eyebrow">{star.sport} · 已点亮</span>
      <h2>{star.title}</h2>
      <p className="star-detail-intro">{child.name}又完成了一次新的尝试。</p>
      <dl className="review-list">
        <div>
          <dt>训练日期</dt>
          <dd>{formatDate(star.date)}</dd>
        </div>
        {coach && <div>
          <dt>陪伴教练</dt>
          <dd>{coach.name}</dd>
        </div>}
        {duration > 0 && <div>
          <dt>训练时长</dt>
          <dd>{duration} 分钟</dd>
        </div>}
      </dl>
      <h3>这颗星的故事</h3>
      <p className="feedback-quote">{star.description}</p>
      {order && (
        <>
          {record?.content && <>
            <h3>教练观察</h3>
            <p>{record.content}</p>
          </>}
          <Link
            to={"/orders?order=" + order.id}
            className="button"
            onClick={onClose}
          >
            查看对应课程
            <Arrow />
          </Link>
        </>
      )}
      <button className="text-link replay-link" onClick={onReplay}>
        <RefreshCw size={15} />
        再次播放点亮
      </button>
      <p className="data-note">重播只播放视觉反馈，不会新增星星或训练记录。</p>
    </Modal>
  );
}
function Tasks() {
  const { state, child, act } = useApp();
  return (
    <section className="page wrap">
      <div className="page-intro">
        <span className="eyebrow">A LITTLE PRACTICE, A LITTLE CLOSER</span>
        <h1>今天，一起动一小步。</h1>
        <p>把课堂里的小尝试，变成家庭中的小快乐。</p>
      </div>
      <div className="task-grid">
        {state.tasks.length ? (
          state.tasks.map((task) => (
            <article className="task-card" key={task.id}>
              <span
                className={"status " + (task.done ? "completed" : "booked")}
              >
                {task.done ? "家长已记录" : "待练习"}
              </span>
              <h2>{task.title}</h2>
              <p>{task.description}</p>
              <span className="eyebrow">
                来自 {state.coaches.find((c) => c.id === task.coachId)?.name}{" "}
                教练
              </span>
              <button
                className={"button " + (task.done ? "secondary" : "")}
                onClick={() =>
                  act("/tasks/" + task.id, {
                    method: "PATCH",
                    body: { done: !task.done },
                  }).catch(() => {})
                }
              >
                {task.done ? "撤回记录" : "和孩子完成，记录一下"}
                <Check size={17} />
              </button>
              <p className="data-note">
                这是家长练习记录，不代表教练已审核；不会自动生成课程成长星。
              </p>
            </article>
          ))
        ) : (
          <Empty
            title="今天，留一点自由玩耍的时间。"
            text="教练安排练习后，会出现在这里。"
          />
        )}
      </div>
    </section>
  );
}
function ArticleModal({ article, onClose }) {
  return (
    <Modal title={article.tag + " / FIELD NOTES"} onClose={onClose}>
      <img
        className="article-cover"
        src={"/images/" + article.image}
        alt="运动场景"
      />
      <span className="eyebrow">{article.time}</span>
      <h2>{article.title}</h2>
      <p className="article-body">{article.text}</p>
      <p className="data-note">
        演示科普内容。动作与训练节奏请以专业教练指导为准。
      </p>
    </Modal>
  );
}
function Videos() {
  const { state } = useApp();
  const [tab, setTab] = useState("videos");
  const videos = state.videos || [];
  const exercises = state.exercises || [];
  return (
    <section className="page wrap">
      <div className="page-intro">
        <span className="eyebrow">THE MORE YOU KNOW, THE MORE YOU GROW</span>
        <h1>为下一次运动，添一点灵感。</h1>
        <p>体育知识、动作要点，与日常陪伴的小方法。</p>
      </div>
      <div className="chips">
        <button
          className={"chip " + (tab === "videos" ? "selected" : "")}
          onClick={() => setTab("videos")}
        >
          教学视频
        </button>
        <button
          className={"chip " + (tab === "exercises" ? "selected" : "")}
          onClick={() => setTab("exercises")}
        >
          动作库
        </button>
      </div>
      {tab === "videos" ? (
        <>
          <div className="info-box">
            <Play size={20} />
            <p>
              动作教学条目来自后端知识库。视频播放素材尚未上传，当前以条目形式展示。
            </p>
          </div>
          <div className="video-grid">
            {videos.map((video) => (
              <article className="video-card" key={video.id}>
                <div className="video-cover">
                  <Play size={24} />
                </div>
                <span className="eyebrow">{video.category}</span>
                <h3>{video.title}</h3>
                <span className="text-link">适合 {video.age}</span>
              </article>
            ))}
          </div>
        </>
      ) : (
        <div className="exercise-grid">
          {exercises.map((exercise) => (
            <details className="exercise-card" key={exercise.id}>
              <summary>
                <div>
                  <span className="eyebrow">
                    {exercise.category} · {exercise.difficulty}
                  </span>
                  <h3>{exercise.name}</h3>
                </div>
                <small>{exercise.age}</small>
              </summary>
              <p className="exercise-goal">目标：{exercise.goal}</p>
              {exercise.instructions.length > 0 && (
                <ol>
                  {exercise.instructions.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              )}
              {exercise.mistakes.length > 0 && (
                <p className="exercise-mistakes">
                  常见误区：{exercise.mistakes.join("；")}
                </p>
              )}
              {exercise.safety && (
                <p className="exercise-safety">安全提示：{exercise.safety}</p>
              )}
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
function Operator() {
  const [code, setCode] = useState(""),
    [data, setData] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const load = () =>
    api("/demo/orders")
      .then(setData)
      .catch(() => {});
  useEffect(() => {
    load();
  }, []);
  return (
    <section className="page wrap">
      <div className="page-intro">
        <span className="eyebrow">LOCAL TEST ENVIRONMENT ONLY</span>
        <h1>测试教练工作台。</h1>
        <p>仅用于黑客松：在这里确认测试课程完成，向家长端同步成长事件。</p>
      </div>
      {!data ? (
        <form
          className="operator-login"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              await api("/demo/login", { method: "POST", body: { code } });
              await load();
              setError("");
            } catch (e) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label htmlFor="operator-code">本地测试口令</label>
          <input
            id="operator-code"
            type="password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
          <p className="data-note">
            口令配置见项目 README；此入口不用于生产环境。
          </p>
          <button className="button" disabled={busy}>
            进入测试工作台
            <Arrow />
          </button>
        </form>
      ) : (
        <>
          <button className="text-link" onClick={load}>
            <RefreshCw size={16} />
            刷新测试预约
          </button>
          <div className="order-list">
            {data.orders
              .filter((o) => o.status === "booked")
              .map((o) => (
                <article className="order-card" key={o.id}>
                  <div className="order-info">
                    <span className="eyebrow">
                      {data.children.find((c) => c.id === o.childId)?.name} ·{" "}
                      {o.date} {o.time}
                    </span>
                    <h3>{o.lesson}</h3>
                    <p>
                      教练 {data.coaches.find((c) => c.id === o.coachId)?.name}{" "}
                      · 预约 {o.id.slice(0, 8)}
                    </p>
                  </div>
                  <button
                    className="button"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        await api(`/bookings/${o.id}/complete`, {
                          method: "POST",
                          body: {},
                        });
                        await load();
                        setError("");
                      } catch (e) {
                        setError(e.message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    确认测试课程完成
                    <Check size={17} />
                  </button>
                </article>
              ))}
          </div>
          {!data.orders.some((o) => o.status === "booked") && (
            <Empty
              title="目前没有待确认的测试课程。"
              text="先在家长端完成一笔预约，再回到这里刷新。"
            />
          )}
          <Link to="/orders" className="button secondary">
            回到家长端查看课程
            <Arrow />
          </Link>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
function NotFound() {
  return (
    <section className="page wrap">
      <Empty
        title="这条轨道，还没被发现。"
        text="回到首页，继续探索孩子的运动宇宙。"
      >
        <Link to="/" className="button">
          回到首页
          <Arrow />
        </Link>
      </Empty>
    </section>
  );
}
export function App() {
  const [state, setState] = useState({
      coaches: [],
      children: [],
      orders: [],
      stars: [],
      tasks: [],
      messages: [],
      events: [],
      records: [],
      videos: [],
      exercises: [],
      loggedIn: false,
    }),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [route, setRoute] = useState(location.pathname + location.search),
    [toast, setToast] = useState(""),
    [switching, setSwitching] = useState(false);
  const [motionPaused, setMotionPaused] = useState(
    () => sessionStorage.getItem("orbit-motion") === "paused",
  );
  useEffect(() => {
    document.documentElement.dataset.motion = motionPaused
      ? "paused"
      : "running";
    sessionStorage.setItem("orbit-motion", motionPaused ? "paused" : "running");
  }, [motionPaused]);
  const toggleMotion = () => setMotionPaused((value) => !value);
  const epoch = useRef(0),
    toastTimer = useRef(null);
  const notify = (text) => {
    setToast(text);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 4500);
  };
  const refresh = async () => {
    const version = epoch.current;
    try {
      const data = await api("/state");
      if (version === epoch.current) {
        setState(data);
        setError("");
      }
      return data;
    } catch (e) {
      setError(e.message);
      throw e;
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    refresh().catch(() => {});
    const f = () => setRoute(location.pathname + location.search);
    addEventListener("popstate", f);
    return () => {
      removeEventListener("popstate", f);
      clearTimeout(toastTimer.current);
    };
  }, []);
  useEffect(() => {
    if (!state.loggedIn) return;
    const timer = setInterval(() => {
      if (!document.hidden) refresh().catch(() => {});
    }, 5000);
    const focus = () => refresh().catch(() => {});
    window.addEventListener("focus", focus);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", focus);
    };
  }, [state.loggedIn]);
  const act = async (path, options = {}, settings = {}) => {
    if (path === "/active-child" && !canLeave())
      throw new Error("已保留当前孩子");
    epoch.current++;
    if (path === "/active-child") setSwitching(true);
    try {
      const data = await api(path, options);
      if (data.coaches) setState(data);
      return data;
    } catch (e) {
      if (!settings.silent) notify(e.message);
      throw e;
    } finally {
      if (path === "/active-child") setSwitching(false);
    }
  };
  const child = state.children.find((c) => c.id === state.activeChildId),
    pathname = route.split("?")[0];
  useEffect(() => {
    if (state.loggedIn) refresh().catch(() => {});
  }, [pathname]);
  useEffect(() => {
    const names = {
      "/": "发现",
      "/coaches": "找教练",
      "/agent": "AI 运动顾问",
      "/universe": "成长星图",
      "/profile": "儿童档案",
      "/orders": "我的课程",
      "/booking": "预约课程",
    };
    document.title = (names[pathname] || "开启运动旅程") + " · 跃星 PLAY ORBIT";
  }, [pathname]);
  let page;
  const needsLogin = [
    "/agent",
    "/profile",
    "/universe",
    "/orders",
    "/booking",
    "/children/select",
    "/tasks",
  ].includes(pathname);
  if (needsLogin && !state.loggedIn && !loading) page = <Login />;
  else if (pathname === "/") page = <Home />;
  else if (pathname === "/login") page = <Login />;
  else if (pathname === "/children/select") page = <Children />;
  else if (pathname === "/coaches") page = <Coaches />;
  else if (pathname.startsWith("/coaches/"))
    page = <CoachDetail id={pathname.split("/")[2]} />;
  else if (pathname === "/booking") page = <Booking key={child?.id} />;
  else if (pathname === "/agent") page = <Agent key={child?.id} />;
  else if (pathname === "/orders") page = <Orders key={child?.id} />;
  else if (pathname === "/profile") page = <Profile key={child?.id} />;
  else if (pathname === "/universe") page = <Growth key={child?.id} />;
  else if (pathname === "/tasks") page = <Tasks />;
  else if (pathname === "/videos") page = <Videos />;
  else if (pathname === "/demo/coach") page = <Operator />;
  else page = <NotFound />;
  const dark = pathname === "/universe" && state.loggedIn;
  return (
    <Context.Provider
      value={{
        state,
        setState,
        child,
        route,
        act,
        refresh,
        notify,
        motionPaused,
        toggleMotion,
      }}
    >
      <div className={"app " + (dark ? "is-dark" : "")}>
        {pathname === "/" && <OrbitIntro />}
        <a href="#main" className="skip-link">
          跳到主要内容
        </a>
        <AcidEffects />
        <Header />
        <main id="main">
          {loading ? (
            <Busy />
          ) : error && !state.coaches.length ? (
            <Empty title="暂时没有连上运动宇宙。" text={error}>
              <button
                className="button"
                onClick={() => {
                  setLoading(true);
                  refresh().catch(() => {});
                }}
              >
                重新连接
                <RefreshCw size={16} />
              </button>
            </Empty>
          ) : (
            page
          )}
        </main>
        <Footer />
        {toast && (
          <div className="toast" role="status">
            <AlertCircle size={18} />
            {toast}
            <button onClick={() => setToast("")} aria-label="关闭提示">
              <X size={16} />
            </button>
          </div>
        )}
        {switching && (
          <div className="switching">
            <Busy text="正在切换孩子的运动宇宙…" />
          </div>
        )}
      </div>
    </Context.Provider>
  );
}
