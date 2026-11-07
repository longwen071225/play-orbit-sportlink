// StarFit backend adapter. Translates the synthetic `/api/*` contract the
// parent app already uses into the real FastAPI service on :8100.

const ORIGIN = import.meta.env.VITE_API_BASE_URL || "";
const TOKEN_KEY = "orbit_starfit_token";
const DEMO_PHONE = "13800000001";
const DEMO_PASSWORD = "demo123456";

const CHILD_COLORS = ["#eaf0ff", "#f9e8d9", "#e6f6e9", "#f3e8f6"];
const COACH_IMAGES = {
  coach_wang: "coach-wang.jpg",
  coach_li: "coach-lin.jpg",
  coach_zhang: "coach-zhao.jpg",
};

let token = localStorage.getItem(TOKEN_KEY) || "";
let activeChildId = "c_xingxing";
const chatSessions = {};
const messageCache = {};

const uid = () =>
  crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

function bearer() {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const response = await fetch(`${ORIGIN}${path}`, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...bearer(),
      ...(options.headers || {}),
    },
    credentials: "include",
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });

  let payload = null;
  const raw = await response.text();
  try {
    payload = raw ? JSON.parse(raw) : null;
  } catch {
    payload = null;
  }

  if (!response.ok || (payload && payload.success === false)) {
    const message =
      payload?.error?.message || payload?.msg || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.code = payload?.error?.code;
    throw error;
  }

  return payload?.data;
}

function normalizeChild(child, index) {
  return {
    id: child.id,
    name: child.nickname || "小朋友",
    age: child.age || 0,
    avatar: (child.nickname || "星").slice(0, 1),
    color: CHILD_COLORS[index % CHILD_COLORS.length],
    goal: (child.trainingGoals || []).join(" · ") || "勇敢尝试，找到热爱",
    sports: child.sportsInterests || [],
    weeklyGoal: 3,
  };
}

function normalizeCoach(coach, services) {
  const own = services.filter((s) => s.coachId === coach.id);
  const primary = own[0] || {};
  const sport = primary.sportType || (coach.courseTypes || [])[0] || "综合运动";
  const minAge = primary.ageMin ?? 5;
  const maxAge = primary.ageMax ?? 12;
  const price = Number(primary.priceYuan ?? coach.priceYuan ?? 0);
  return {
    id: coach.id,
    name: coach.name,
    english: coach.name,
    sport,
    title: primary.title || "一对一上门课程",
    tag: (coach.courseTypes || [sport]).join(" · "),
    bio: coach.bio || "",
    experience: 5,
    students: 0,
    rating: 4.9,
    price,
    age: `${minAge}–${maxAge}岁`,
    minAge,
    maxAge,
    area: (coach.serviceAreas || ["上门服务"])[0],
    image: COACH_IMAGES[coach.id] || "coach-zhao.jpg",
    cover: "",
    badges: [
      coach.certificateStatus === "APPROVED" ? "平台认证教练" : "待审核",
    ],
    lessons: own.map((s) => s.title),
    services: own,
  };
}

function localTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  });
}

function localDate(iso) {
  return iso
    ? new Intl.DateTimeFormat("en-CA", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        timeZone: "Asia/Shanghai",
      }).format(new Date(iso))
    : "";
}

function statusOf(backendStatus) {
  if (backendStatus === "COMPLETED") return "completed";
  if (backendStatus === "CANCELLED" || backendStatus === "REJECTED")
    return "cancelled";
  return "booked";
}

function normalizeOrder(booking, services) {
  const service = services.find((s) => s.id === booking.serviceId);
  return {
    id: booking.id,
    childId: booking.childId,
    coachId: booking.coachId,
    serviceId: booking.serviceId,
    lesson: service?.title || "上门课程",
    date: localDate(booking.startAt),
    time: localTime(booking.startAt),
    endTime: localTime(booking.endAt),
    durationMinutes: (Date.parse(booking.endAt) - Date.parse(booking.startAt)) / 60000,
    status: statusOf(booking.status),
    bookingStatus: booking.status,
    price: Number(booking.amountYuan || 0),
    paymentStatus:
      booking.paymentStatus === "SIMULATED_PAID" ? "demo-paid" : "demo-unpaid",
    feedback: booking.note || "",
    completedAt: booking.status === "COMPLETED" ? booking.updatedAt : null,
  };
}

function normalizeStar(star) {
  return {
    id: star.starId,
    sport: star.metadata?.constellation || star.starType || "成长星",
    title: star.title || "成长星",
    date: localDate(star.earnedAt),
    description: star.description || "",
    coachId: star.coachId,
    orderId: star.sourceType === "BOOKING" ? star.sourceId : null,
    sourceType: star.sourceType,
    sourceId: star.sourceId,
    recordId: star.recordId,
    durationMinutes: star.durationMinutes,
    durationSeconds: star.durationSeconds,
    earnedAt: star.earnedAt,
  };
}

function normalizeRecord(record) {
  const feedback = record.performance?.feedback || {};
  return {
    id: record.id,
    bookingId: record.bookingId,
    childId: record.childId,
    coachId: record.coachId,
    date: localDate(record.createdAt),
    durationMinutes: record.durationMinutes || 0,
    content: record.content || feedback.content || "",
    grade: record.performance?.grade || feedback.performance || "",
    strengths: feedback.strengths || "",
    improvements: feedback.improvements || "",
    homeSuggestion: feedback.homeSuggestion || "",
  };
}

function normalizeVideo(video) {
  return {
    id: video.id,
    title: video.title,
    category: video.category,
    age: `${video.ageMin}–${video.ageMax}岁`,
    url: video.videoUrl || "",
    thumb: video.thumbnailUrl || "",
    duration: video.durationSeconds || 0,
  };
}

function normalizeExercise(exercise) {
  return {
    id: exercise.exerciseId,
    name: exercise.name,
    category: exercise.category,
    age: `${exercise.minAge}–${exercise.maxAge}岁`,
    difficulty: exercise.difficulty,
    goal: exercise.trainingGoal,
    instructions: exercise.instructions || [],
    mistakes: exercise.commonMistakes || [],
    equipment: exercise.equipment || [],
    safety: exercise.safetyNotes || "",
    tags: exercise.tags || [],
  };
}

function pickTool(toolCalls, name) {
  return (toolCalls || []).find((call) => call.name === name)?.result;
}

function composeReply(data) {
  const sections = [];
  const lead = (data.reply || "").trim();
  if (lead) sections.push(lead);

  const plan = pickTool(data.toolCalls, "generate_training_plan");
  if (plan && Array.isArray(plan.weeks) && plan.weeks.length) {
    const lines = plan.weeks.map((week) => {
      const names = (week.exercises || [])
        .map((item) => item.name || item.title)
        .filter(Boolean)
        .join("、");
      return `第 ${week.week} 周 · ${week.focus}${names ? `：${names}` : ""}`;
    });
    sections.push(
      `【运动建议】${plan.title ? `（${plan.title}）` : ""}\n${lines.join("\n")}`,
    );
  }

  const exercises = pickTool(data.toolCalls, "search_exercises");
  if (
    exercises &&
    Array.isArray(exercises.exercises) &&
    exercises.exercises.length
  ) {
    const picks = exercises.exercises
      .slice(0, 3)
      .map(
        (item) => `${item.name}（${item.difficulty || item.category || ""}）`,
      )
      .join("、");
    sections.push(`【推荐动作】${picks}`);
    const safety = exercises.exercises.find(
      (item) => item.safetyNotes,
    )?.safetyNotes;
    if (safety) sections.push(`安全提示：${safety}`);
  }

  const history = pickTool(data.toolCalls, "get_training_history");
  if (history && history.total) {
    sections.push(`已结合 ${history.total} 条历史训练记录。`);
  }

  const coaches = pickTool(data.toolCalls, "search_coaches");
  if (coaches && Array.isArray(coaches.items) && coaches.items.length) {
    sections.push(
      `为你找到 ${coaches.items.length} 位合适的教练：${coaches.items
        .map((item) => item.name)
        .join("、")}。`,
    );
  }

  return sections.join("\n\n");
}

async function snapshot() {
  if (!token) {
    return {
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
      activeChildId: null,
    };
  }

  const childrenData = await request("/api/children");
  const coachesData = await request("/api/coaches");
  const bookingsData = await request("/api/bookings");
  const servicesData = await request("/api/services");
  const services = servicesData.items || [];
  const children = (childrenData.items || []).map(normalizeChild);
  const coaches = (coachesData.items || []).map((coach) =>
    normalizeCoach(coach, services),
  );

  if (!children.some((child) => child.id === activeChildId)) {
    activeChildId = children[0]?.id || "";
  }
  const childId = activeChildId;
  const orders = (bookingsData.items || [])
    .filter((booking) => booking.childId === childId)
    .map((booking) => normalizeOrder(booking, services));

  let stars = [];
  let events = [];
  let tasks = [];
  if (childId) {
    const starData = await request(`/api/children/${childId}/stars`);
    stars = (starData.stars || []).map(normalizeStar);
    events = starData.events || [];
  }
  try {
    const taskData = await request("/api/tasks");
    tasks = taskData.items || [];
  } catch {
    tasks = [];
  }

  let records = [];
  let videos = [];
  let exercises = [];
  try {
    const recordData = await request(
      `/api/children/${childId}/training-records`,
    );
    records = (recordData.items || []).map(normalizeRecord);
  } catch {
    records = [];
  }
  try {
    const videoData = await request("/api/videos");
    videos = (videoData.items || []).map(normalizeVideo);
  } catch {
    videos = [];
  }
  try {
    const exerciseData = await request("/api/exercises");
    exercises = (exerciseData.items || []).map(normalizeExercise);
  } catch {
    exercises = [];
  }

  return {
    coaches,
    children,
    orders,
    stars,
    tasks,
    messages: messageCache[childId] || [],
    events,
    records,
    videos,
    exercises,
    loggedIn: true,
    activeChildId: childId,
  };
}

async function chat(body) {
  const childId = body.childId || activeChildId;
  const sessionId = chatSessions[childId] || null;
  const data = await request("/api/agent/chat", {
    method: "POST",
    signal: body.signal,
    body: {
      message: body.message,
      sessionId,
      childId,
    },
  });
  chatSessions[childId] = data.sessionId;

  const list = messageCache[childId] || (messageCache[childId] = []);
  list.push({ id: uid(), role: "user", text: body.message });

  const coachIds = (data.toolCalls || [])
    .filter((call) => call.name === "search_coaches")
    .flatMap(
      (call) =>
        call.result?.items?.map((item) => item.id) ||
        call.result?.coaches?.map((item) => item.id) ||
        [],
    );

  let reply = composeReply(data) || data.reply || "已收到，正在整理运动建议。";
  if (data.pendingConfirmation?.summary) {
    reply += `\n\n[待确认] ${data.pendingConfirmation.summary}`;
  }
  list.push({ id: uid(), role: "assistant", text: reply, coachIds });
  return {
    messages: [...list],
    pendingConfirmation: data.pendingConfirmation || null,
    sessionId: data.sessionId,
  };
}

async function createBooking(body) {
  const servicesData = await request("/api/services");
  const services = (servicesData.items || []).filter((item) => item.coachId === body.coachId);
  const service = services.find((item) =>
    body.serviceId ? item.id === body.serviceId : item.title === body.lesson,
  );
  if (!service) {
    const error = new Error("该教练暂无可用课程");
    error.status = 404;
    throw error;
  }
  const startAt = `${body.date}T${body.time}:00+08:00`;
  const endAt = new Date(Date.parse(startAt) + service.durationMinutes * 60000).toISOString();
  const booking = await request("/api/bookings", {
    method: "POST",
    body: {
      childId: body.childId,
      serviceId: service.id,
      startAt,
      endAt,
      note: "黑客松演示预约",
    },
  });
  const order = normalizeOrder(booking, services);
  const state = await snapshot().catch(() => null);
  return { ...state, order };
}

async function availability(queryString) {
  const query = new URLSearchParams(queryString);
  const coachId = query.get("coachId");
  const date = query.get("date");
  const durationMs = Number(query.get("durationMinutes") || 0) * 60000;
  const dates = new URLSearchParams({ fromDate: date, toDate: date });
  const data = await request(`/api/coaches/${coachId}/slots?${dates}`);
  const slots = new Map();
  for (const slot of data.slots || []) {
    if (localDate(slot.startAt) !== date) continue;
    const time = localTime(slot.startAt);
    const available = slot.status === "OPEN" && Date.parse(slot.endAt) - Date.parse(slot.startAt) >= durationMs;
    slots.set(time, { time, available: slots.get(time)?.available || available });
  }
  return { slots: [...slots.values()], date };
}

function noopState() {
  return { ok: true };
}

export async function api(path, options = {}) {
  const method = options.method || "GET";

  if (path === "/state" && method === "GET") return snapshot();
  if (path === "/login" && method === "POST") {
    const data = await request("/api/auth/login", {
      method: "POST",
      body: { phone: DEMO_PHONE, password: DEMO_PASSWORD },
    });
    token = data.token;
    localStorage.setItem(TOKEN_KEY, token);
    return snapshot();
  }
  if (path === "/logout" && method === "POST") {
    token = "";
    activeChildId = "c_xingxing";
    localStorage.removeItem(TOKEN_KEY);
    return noopState();
  }
  if (path === "/active-child" && method === "PUT") {
    activeChildId = options.body?.childId || activeChildId;
    return snapshot();
  }
  if (path === "/children" && method === "POST") {
    const child = await request("/api/children", {
      method: "POST",
      body: options.body,
    });
    const state = await snapshot();
    return { created: child, ...state };
  }
  if (path === "/chat" && method === "POST") return chat(options.body || {});
  if (path.startsWith("/availability") && method === "GET") {
    return availability(path.slice(path.indexOf("?") + 1));
  }
  if (path === "/bookings" && method === "POST")
    return createBooking(options.body || {});
  if (/^\/bookings\/[^/]+\/cancel$/.test(path) && method === "POST") {
    const id = path.split("/")[2];
    await request(`/api/bookings/${id}/cancel`, { method: "POST" });
    return snapshot();
  }
  if (path === "/profile" && method === "PATCH") return snapshot();
  if (/^\/growth-events\/[^/]+\/seen$/.test(path) && method === "POST") {
    return request(`/api${path}`, { method });
  }
  if (/^\/tasks\/[^/]+$/.test(path) && method === "PATCH") {
    const id = path.split("/")[2];
    await request(`/api/tasks/${id}/submissions`, {
      method: "POST",
      body: { note: "家长打卡完成", photoUrls: [] },
    });
    return snapshot();
  }
  if (path === "/demo/orders" && method === "GET") return { orders: [] };
  if (path === "/demo/login" && method === "POST") {
    throw Object.assign(new Error("请使用教练工作台登录"), { status: 403 });
  }
  if (/^\/bookings\/[^/]+\/complete$/.test(path)) {
    throw Object.assign(new Error("课程完成请在教练工作台操作"), {
      status: 403,
    });
  }

  const error = new Error("接口不存在");
  error.status = 404;
  throw error;
}
