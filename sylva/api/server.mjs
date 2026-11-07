import http from "node:http";
import { readFile, mkdir, writeFile, rename } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const coaches = [
  {
    id: "chen",
    name: "陈宇",
    english: "CHEN YU",
    sport: "篮球",
    title: "让孩子爱上球场的第一课",
    tag: "耐心引导 · 兴趣启蒙",
    bio: "从认识篮球开始，用游戏建立球感，再慢慢找到投篮的自信。课堂关注每个孩子的节奏，让运动成为可以期待的事。",
    experience: 8,
    students: 128,
    rating: 4.9,
    price: 198,
    age: "6–12岁",
    minAge: 6,
    maxAge: 12,
    area: "徐汇区",
    image: "coach-chen.jpg",
    cover: "basketball.jpg",
    badges: ["青少年篮球教练", "儿童体适能指导"],
    lessons: ["篮球兴趣启蒙", "控球与协调训练", "投篮基础进阶"],
  },
  {
    id: "lin",
    name: "林悦",
    english: "LIN YUE",
    sport: "游泳",
    title: "每一次入水，多一点勇敢",
    tag: "水感培养 · 安全第一",
    bio: "用耐心陪孩子熟悉水的世界，从呼吸、水感到基础泳姿。课程按孩子的水中适应情况安排，并由教练全程看护。",
    experience: 6,
    students: 96,
    rating: 4.9,
    price: 238,
    age: "5–12岁",
    minAge: 5,
    maxAge: 12,
    area: "浦东新区",
    image: "coach-lin.jpg",
    cover: "swimming.jpg",
    badges: ["游泳社会体育指导员", "儿童水中启蒙"],
    lessons: ["亲水与呼吸启蒙", "自由泳基础", "水中协调训练"],
  },
  {
    id: "wang",
    name: "王浩",
    english: "WANG HAO",
    sport: "足球",
    title: "一起奔跑，也学会一起成长",
    tag: "团队协作 · 快乐奔跑",
    bio: "用有趣的小场地游戏，练习带球、传接球和团队配合。鼓励孩子主动表达，在运动中认识朋友、收获参与感。",
    experience: 7,
    students: 112,
    rating: 4.8,
    price: 168,
    age: "6–14岁",
    minAge: 6,
    maxAge: 14,
    area: "徐汇区",
    image: "coach-wang.jpg",
    cover: "football.jpg",
    badges: ["青少年足球教练", "团队运动启蒙"],
    lessons: ["足球快乐启蒙", "带球与传接球", "小队合作训练"],
  },
  {
    id: "zhao",
    name: "赵可",
    english: "ZHAO KE",
    sport: "体能",
    title: "把每一次进步，变成小小成就",
    tag: "协调发展 · 游戏体能",
    bio: "通过平衡、跳跃和协调游戏探索身体的可能。尊重孩子的个体差异，着重建立积极、轻松的运动习惯。",
    experience: 5,
    students: 87,
    rating: 4.9,
    price: 158,
    age: "4–10岁",
    minAge: 4,
    maxAge: 10,
    area: "静安区",
    image: "coach-zhao.jpg",
    cover: "training.jpg",
    badges: ["儿童体适能教练", "运动游戏设计"],
    lessons: ["趣味体能探索", "平衡与协调", "敏捷游戏课"],
  },
];
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dbFile =
  process.env.DEMO_DB_PATH || path.join(root, ".local", "demo.json");
const operatorCode = process.env.DEMO_OPERATOR_CODE || "orbit-demo-2026";
const now = () => new Date().toISOString();
const seed = () => ({
  children: [
    {
      id: "child-1",
      name: "小宇",
      age: 8,
      avatar: "Y",
      color: "#eaf0ff",
      goal: "找到热爱的运动，勇敢尝试",
      sports: ["篮球", "足球"],
      weeklyGoal: 3,
    },
    {
      id: "child-2",
      name: "朵朵",
      age: 6,
      avatar: "D",
      color: "#f9e8d9",
      goal: "更自信地表达，享受运动",
      sports: ["体能", "游泳"],
      weeklyGoal: 2,
    },
  ],
  orders: [
    {
      id: "seed-order",
      childId: "child-1",
      coachId: "chen",
      lesson: "篮球兴趣启蒙",
      date: "2026-11-01",
      time: "10:30",
      status: "completed",
      price: 198,
      completedAt: "2026-11-01T03:15:00Z",
      feedback:
        "今天主动尝试了左右手运球，也和新朋友完成了一次默契传球。继续保持对球场的好奇心！",
    },
    {
      id: "seed-fitness",
      childId: "child-1",
      coachId: "zhao",
      lesson: "平衡与协调",
      date: "2026-10-25",
      time: "09:00",
      status: "completed",
      price: 158,
      completedAt: "2026-10-25T01:45:00Z",
      feedback: "在平衡游戏中愿意主动再尝试一次，这是今天的小小进步。",
    },
    {
      id: "seed-football",
      childId: "child-1",
      coachId: "wang",
      lesson: "小队合作训练",
      date: "2026-10-18",
      time: "14:00",
      status: "completed",
      price: 168,
      completedAt: "2026-10-18T06:45:00Z",
      feedback: "和小伙伴完成传接球挑战，体验了合作的乐趣。",
    },
  ],
  stars: [
    {
      id: "seed-star-1",
      childId: "child-1",
      orderId: "seed-order",
      sport: "篮球",
      title: "第一次勇敢上场",
      date: "2026-11-01",
      description: "认识篮球，完成球感与基础运球体验。",
      coachId: "chen",
    },
    {
      id: "seed-star-2",
      childId: "child-1",
      orderId: "seed-fitness",
      sport: "体能",
      title: "平衡小达人",
      date: "2026-10-25",
      description: "完成平衡游戏与双脚跳跃练习。",
      coachId: "zhao",
    },
    {
      id: "seed-star-3",
      childId: "child-1",
      orderId: "seed-football",
      sport: "足球",
      title: "第一次团队配合",
      date: "2026-10-18",
      description: "和小伙伴完成传接球挑战。",
      coachId: "wang",
    },
  ],
  tasks: [
    {
      id: "task-1",
      childId: "child-1",
      title: "和篮球交个朋友",
      description: "在安全空地，与家长一起尝试原地拍球，以轻松、有趣为主。",
      coachId: "chen",
      done: false,
    },
    {
      id: "task-2",
      childId: "child-1",
      title: "今天也一起动一动",
      description: "选择喜欢的户外游戏，记录一件让你开心的小事。",
      coachId: "zhao",
      done: false,
    },
  ],
  chats: {},
  sessions: {},
  operators: {},
  events: [],
  seen: [],
  graphVersion: 1,
});
let db;
try {
  db = JSON.parse(await readFile(dbFile, "utf8"));
} catch (e) {
  if (e.code !== "ENOENT") throw e;
  db = seed();
}
for (const [key, value] of Object.entries({
  operators: {},
  events: [],
  seen: [],
  graphVersion: 1,
}))
  db[key] ??= value;
const persist = async () => {
  await mkdir(path.dirname(dbFile), { recursive: true });
  await writeFile(dbFile + ".tmp", JSON.stringify(db, null, 2));
  await rename(dbFile + ".tmp", dbFile);
};
const response = (res, status, value, headers = {}) => {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    ...headers,
  });
  res.end(JSON.stringify(value));
};
const fail = (message, status = 400) =>
  Object.assign(new Error(message), { status });
const cookie = (req, key) =>
  (req.headers.cookie || "")
    .split(";")
    .map((s) => s.trim())
    .find((s) => s.startsWith(key + "="))
    ?.slice(key.length + 1);
const sessionFor = (req) => db.sessions[cookie(req, "orbit_session")];
const unseenFor = (childId) =>
  db.events.filter(
    (e) => e.childId === childId && !db.seen.includes(e.eventId),
  );
const snapshot = (session) => ({
  coaches,
  loggedIn: !!session,
  children: session ? db.children : [],
  activeChildId: session?.childId || null,
  orders: session ? db.orders.filter((x) => x.childId === session.childId) : [],
  stars: session ? db.stars.filter((x) => x.childId === session.childId) : [],
  tasks: session ? db.tasks.filter((x) => x.childId === session.childId) : [],
  messages: session ? db.chats[session.childId] || [] : [],
  events: session ? unseenFor(session.childId) : [],
  graphVersion: db.graphVersion,
});
const times = ["09:00", "10:30", "14:00", "16:00"];
const dateToday = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
const isDate = (value) =>
  typeof value === "string" &&
  /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  !Number.isNaN(new Date(value + "T00:00:00+08:00").getTime());
const slotAvailable = (coachId, date, time) =>
  !db.orders.some(
    (x) =>
      x.coachId === coachId &&
      x.date === date &&
      x.time === time &&
      x.status !== "cancelled",
  );
async function handler(req, res) {
  try {
    const url = new URL(req.url, "http://localhost");
    const route = url.pathname;
    const method = req.method;
    let body = {};
    if (["POST", "PATCH", "PUT"].includes(method)) {
      let raw = "";
      for await (const chunk of req) {
        raw += chunk;
        if (raw.length > 16000) throw fail("请求内容过长", 413);
      }
      try {
        body = JSON.parse(raw || "{}");
      } catch {
        throw fail("请求格式错误");
      }
    }
    if (route === "/api/health")
      return response(res, 200, { ok: true, mode: "local-demo" });
    if (route === "/api/state" && method === "GET")
      return response(res, 200, snapshot(sessionFor(req)));
    if (route === "/api/login" && method === "POST") {
      const token = randomUUID();
      db.sessions[token] = { childId: db.children[0].id };
      await persist();
      return response(res, 200, snapshot(db.sessions[token]), {
        "Set-Cookie": `orbit_session=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800`,
      });
    }
    if (route === "/api/demo/login" && method === "POST") {
      if (body.code !== operatorCode) throw fail("测试教练口令不正确", 403);
      const token = randomUUID();
      db.operators[token] = { createdAt: now() };
      await persist();
      return response(
        res,
        200,
        { ok: true },
        {
          "Set-Cookie": `orbit_operator=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=7200`,
        },
      );
    }
    const operator = db.operators[cookie(req, "orbit_operator")];
    if (route === "/api/demo/orders" && method === "GET") {
      if (!operator) throw fail("请登录测试教练工作台", 403);
      return response(res, 200, {
        orders: db.orders,
        children: db.children,
        coaches,
      });
    }
    const completion = route.match(/^\/api\/bookings\/([^/]+)\/complete$/);
    if (completion && method === "POST") {
      if (!operator) throw fail("只有测试教练工作台可以确认完课", 403);
      const order = db.orders.find((x) => x.id === completion[1]);
      if (!order) throw fail("没有找到课程", 404);
      if (order.status === "cancelled") throw fail("已取消的课程不能完课", 409);
      if (order.status !== "completed") {
        order.status = "completed";
        order.completedAt = now();
        order.feedback =
          typeof body.feedback === "string" && body.feedback.trim()
            ? body.feedback.trim().slice(0, 1000)
            : "今天完成了一次新的运动探索，主动尝试了基础动作。愿意尝试，就是值得记录的进步。下次继续跟随教练的节奏，享受运动。";
        const star = {
          id: randomUUID(),
          childId: order.childId,
          orderId: order.id,
          sport: coaches.find((x) => x.id === order.coachId).sport,
          title: order.lesson,
          date: order.date,
          description: order.feedback,
          coachId: order.coachId,
          createdAt: now(),
        };
        db.stars.push(star);
        db.graphVersion++;
        db.events.push({
          eventId: randomUUID(),
          childId: order.childId,
          nodeId: star.id,
          recordId: order.id,
          type: "growth.star_earned",
          occurredAt: now(),
          graphVersion: db.graphVersion,
        });
        await persist();
      }
      return response(res, 200, {
        ok: true,
        order,
        star: db.stars.find((s) => s.orderId === order.id),
      });
    }
    const session = sessionFor(req);
    if (!session) throw fail("请先进入演示家庭", 401);
    if (route === "/api/logout" && method === "POST") {
      delete db.sessions[cookie(req, "orbit_session")];
      await persist();
      return response(
        res,
        200,
        { ok: true },
        {
          "Set-Cookie":
            "orbit_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0",
        },
      );
    }
    if (route === "/api/active-child" && method === "PUT") {
      if (!db.children.some((x) => x.id === body.childId))
        throw fail("没有找到这个孩子");
      session.childId = body.childId;
      await persist();
      return response(res, 200, snapshot(session));
    }
    if (route === "/api/profile" && method === "PATCH") {
      const child = db.children.find((x) => x.id === session.childId);
      if (
        typeof body.goal !== "string" ||
        body.goal.length > 100 ||
        !body.goal.trim()
      )
        throw fail("请填写 1–100 字的成长目标");
      if (![1, 2, 3, 4, 5, 6, 7].includes(Number(body.weeklyGoal)))
        throw fail("每周目标应为 1–7 次");
      child.goal = body.goal.trim();
      child.weeklyGoal = Number(body.weeklyGoal);
      await persist();
      return response(res, 200, snapshot(session));
    }
    if (route === "/api/chat" && method === "POST") {
      if (body.childId !== session.childId)
        throw fail("孩子已切换，请重新发送", 409);
      if (
        typeof body.message !== "string" ||
        !body.message.trim() ||
        body.message.length > 1000
      )
        throw fail("请输入 1–1000 字的问题");
      const child = db.children.find((x) => x.id === session.childId),
        message = body.message.trim();
      const sport =
        ["篮球", "游泳", "足球", "体能", "骑行", "田径"].find((x) =>
          message.includes(x),
        ) ||
        child.sports[0];
      let recommended = coaches.filter(
        (x) =>
          x.sport === sport && child.age >= x.minAge && child.age <= x.maxAge,
      );
      if (!recommended.length)
        recommended = coaches
          .filter((x) => child.age >= x.minAge && child.age <= x.maxAge)
          .slice(0, 2);
      const injury = /疼|受伤|疾病|不舒服/.test(message);
      const text = injury
        ? "如果孩子有疼痛、受伤或身体不适，请先暂停训练，由医生或专业人员评估后再决定是否恢复运动。这里的演示顾问不能做诊断。"
        : `可以先让${child.name}从一次轻松的${sport}体验开始。\n\n① 给孩子选择权：先聊聊最想尝试的动作。\n② 从游戏开始：把基础练习拆成小任务，关注参与和快乐。\n③ 留一点期待：与教练沟通孩子的节奏，再决定后续安排。\n\n${recommended[0].name}教练的课程面向${recommended[0].age}，特点是${recommended[0].tag}，与${child.name}的年龄和兴趣相符。你可以先看看课程与可约时间。`;
      const pair = [
        { id: randomUUID(), role: "user", text: message },
        {
          id: randomUUID(),
          role: "assistant",
          text,
          coachIds: injury ? [] : recommended.map((x) => x.id),
        },
      ];
      db.chats[session.childId] = [
        ...(db.chats[session.childId] || []),
        ...pair,
      ].slice(-40);
      await persist();
      return response(res, 200, {
        childId: session.childId,
        messages: db.chats[session.childId],
      });
    }
    if (route === "/api/availability" && method === "GET") {
      const coachId = url.searchParams.get("coachId"),
        date = url.searchParams.get("date");
      if (!coaches.some((c) => c.id === coachId) || !isDate(date))
        throw fail("请选择有效日期与课程");
      return response(res, 200, {
        date,
        timezone: "Asia/Shanghai",
        slots: times.map((time) => ({
          time,
          available:
            date >= dateToday() &&
            new Date(date + "T" + time + ":00+08:00") > new Date() &&
            slotAvailable(coachId, date, time),
        })),
      });
    }
    if (route === "/api/bookings" && method === "POST") {
      if (body.childId !== session.childId)
        throw fail("孩子已切换，请重新确认预约", 409);
      if (typeof body.requestId !== "string" || body.requestId.length > 80)
        throw fail("预约请求标识无效");
      const existing = db.orders.find(
        (x) => x.requestId === body.requestId && x.childId === session.childId,
      );
      if (existing)
        return response(res, 200, { order: existing, ...snapshot(session) });
      const coach = coaches.find((x) => x.id === body.coachId);
      if (!coach || !coach.lessons.includes(body.lesson))
        throw fail("请选择有效课程");
      const child = db.children.find((x) => x.id === session.childId);
      if (child.age < coach.minAge || child.age > coach.maxAge)
        throw fail("课程暂不适合孩子的年龄");
      if (!isDate(body.date) || !times.includes(body.time))
        throw fail("请选择有效时间");
      const starts = new Date(body.date + "T" + body.time + ":00+08:00");
      if (starts <= new Date() || starts > Date.now() + 31 * 86400000)
        throw fail("请选择未来 30 天内的时间");
      if (!slotAvailable(coach.id, body.date, body.time))
        throw fail("这个时段刚被预约，请选择其他时间", 409);
      const order = {
        id: randomUUID(),
        requestId: body.requestId,
        childId: session.childId,
        coachId: coach.id,
        lesson: body.lesson,
        date: body.date,
        time: body.time,
        status: "booked",
        price: coach.price,
        paymentStatus: "demo-unpaid",
        createdAt: now(),
      };
      db.orders.unshift(order);
      await persist();
      return response(res, 201, { order, ...snapshot(session) });
    }
    const cancel = route.match(/^\/api\/bookings\/([^/]+)\/cancel$/);
    if (cancel && method === "POST") {
      const order = db.orders.find(
        (x) => x.id === cancel[1] && x.childId === session.childId,
      );
      if (!order) throw fail("课程不存在", 404);
      if (order.status !== "booked") throw fail("只有待上课课程可以取消");
      order.status = "cancelled";
      await persist();
      return response(res, 200, snapshot(session));
    }
    const seen = route.match(/^\/api\/growth-events\/([^/]+)\/seen$/);
    if (seen && method === "POST") {
      if (
        !db.events.some(
          (e) => e.eventId === seen[1] && e.childId === session.childId,
        )
      )
        throw fail("成长事件不存在", 404);
      if (!db.seen.includes(seen[1])) db.seen.push(seen[1]);
      await persist();
      return response(res, 200, { ok: true });
    }
    const task = route.match(/^\/api\/tasks\/([^/]+)$/);
    if (task && method === "PATCH") {
      const value = db.tasks.find(
        (x) => x.id === task[1] && x.childId === session.childId,
      );
      if (!value) throw fail("任务不存在", 404);
      if (typeof body.done !== "boolean") throw fail("打卡状态无效");
      value.done = body.done;
      value.completedAt = body.done ? now() : null;
      await persist();
      return response(res, 200, snapshot(session));
    }
    throw fail("接口不存在", 404);
  } catch (error) {
    response(res, error.status || 500, {
      error: error.status ? error.message : "本地服务出现问题，请稍后重试",
    });
    if (!error.status) console.error(error);
  }
}
let queue = Promise.resolve();
const server = http.createServer((req, res) => {
  queue = queue
    .then(() => handler(req, res))
    .catch((error) => {
      console.error(error);
      if (!res.headersSent) response(res, 500, { error: "服务暂不可用" });
    });
});
server.listen(Number(process.env.API_PORT || 4311), "127.0.0.1", () =>
  console.log(
    "PLAY ORBIT local demo API → http://127.0.0.1:" + server.address().port,
  ),
);
