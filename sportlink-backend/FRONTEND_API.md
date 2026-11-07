# 星动到家 StarFit · 前端对接文档

> 后端为**现有 FastAPI 服务的增量扩展**，不是第二个服务。所有新接口与原有
> `/api/v1/*`（SoloPilot）共存于同一个进程、同一个 SQLite 文件 `prisma/dev.db`。
> 本文只描述 StarFit 新接口；legacy 接口路径不变、不受影响。

---

## 1. 启动后端（已实测）

项目根目录（本文档所在目录）：

```
C:\Users\asus\.myagents\projects\mino\myagents_files\福建黑客松
```

```powershell
cd C:\Users\asus\.myagents\projects\mino\myagents_files\福建黑客松
.\.venv\Scripts\python.exe -m backend.run
```

等价写法（显式指定 host/port）：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8100
```

交互文档 / OpenAPI：

- Swagger UI：`http://127.0.0.1:8100/docs`
- OpenAPI JSON：`http://127.0.0.1:8100/openapi.json`
- 健康检查：`GET http://127.0.0.1:8100/api/starfit/health`（无需登录）
- legacy 健康检查：`GET http://127.0.0.1:8100/api/v1/health`

首次启动会自动建 `sf_*` 表并写入**明确标记的演示数据**（仅当 `sf_user` 为空时，幂等，不删已有数据）。重建演示数据：

```powershell
.\.venv\Scripts\python.exe -m backend.starfit.seed --reset
```

### 环境变量

复制 `backend/.env.example` 为 `backend/.env`。真实 OS 环境变量优先。

| 变量 | 默认 | 说明 |
|---|---|---|
| `SOLOPILOT_LLM_MODE` | `auto` | 有 Key 走真实百炼；无 Key 自动 mock（完整工具调用链路离线可跑） |
| `SOLOPILOT_DASHSCOPE_API_KEY` | 空 | 百炼 Key，**只存服务端**，前端永远不要传 |
| `SOLOPILOT_DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 与 Key 地域必须匹配 |
| `SOLOPILOT_DASHSCOPE_MODEL` | `qwen3.7-plus` | 主模型 |
| `SOLOPILOT_DASHSCOPE_FALLBACK_MODEL` | `qwen3.8-max` | 备用模型 |
| `SOLOPILOT_DATABASE_PATH` | `prisma/dev.db` | 统一 SQLite 文件 |
| `SOLOPILOT_STARFIT_SECRET` | 空（开发默认值） | 服务端 HMAC 签名密钥，生产必填长随机值 |
| `SOLOPILOT_STARFIT_SEED_DEMO` | `true` | 启动时是否初始化演示数据 |

**是否需要百炼 Key**：演示链路**不需要**——mock 模式下 Agent 仍会真实调用后端工具、真实读写数据库。需要真实模型语义时才配 Key。

---

## 2. API Base URL 与登录

```
API Base URL = http://127.0.0.1:8100
```

除 `/api/auth/login`、`/api/starfit/health`、`/api/v1/*`、`/docs`、`/openapi.json` 外，**所有接口都需要**：

```
Authorization: Bearer <token>
```

### 演示账号（密码统一 `demo123456`）

| 角色 | 手机号 | 说明 |
|---|---|---|
| PARENT | `13800000001` | 林女士，名下 2 个儿童：`c_xingxing`(小星,8岁)、`c_xiaoyue`(小跃,6岁) |
| PARENT | `13800000002` | 陈先生，名下 `c_other`（用于验证越权隔离） |
| COACH | `13900000001` | 王教练（`coach_wang`，篮球基础 / 敏捷训练，鼓楼区） |
| COACH | `13900000002` | 李教练（`coach_li`，平衡 / 协调，仓山区） |
| COACH | `13900000003` | 张教练（`coach_zhang`，体适能） |
| ADMIN | `13700000000` | 平台管理员 |

### 登录请求 / 响应

```http
POST /api/auth/login
Content-Type: application/json

{"phone":"13800000001","password":"demo123456"}
```

```json
{
  "success": true,
  "data": {
    "token": "eyJ1aWQiOiJ1X3BhcmVudF9kZW1vIiwi...",
    "tokenType": "Bearer",
    "expiresInSeconds": 604800,
    "user": {"id":"u_parent_demo","phone":"13800000001","name":"林女士（演示）","role":"PARENT"}
  },
  "error": null,
  "requestId": "uuid"
}
```

前端 `fetch` 示例：

```js
const BASE = "http://127.0.0.1:8100";
const login = await fetch(`${BASE}/api/auth/login`, {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({phone: "13800000001", password: "demo123456"}),
}).then(r => r.json());
const headers = {Authorization: `Bearer ${login.data.token}`, "Content-Type": "application/json"};
```

---

## 3. 统一响应与错误码

**所有**接口（含 legacy）使用同一信封，并带 `x-request-id` 响应头：

```json
{"success": true,  "data": {...}, "error": null, "requestId": "uuid"}
{"success": false, "data": null, "error": {"code":"...","message":"...","details":null}, "requestId": "uuid"}
```

| HTTP | code | 含义 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 缺少 Bearer Token |
| 401 | `INVALID_TOKEN` / `INVALID_CREDENTIALS` | Token 无效/过期、账号密码错误 |
| 401 | `USER_INACTIVE` | 账号停用 |
| 403 | `FORBIDDEN` | 角色不允许 |
| 403 | `CHILD_ACCESS_DENIED` | 儿童数据越权（**仅传 child_id 不足以读取**） |
| 403 | `COACH_PROFILE_MISSING` | 账号未绑定教练资料 |
| 404 | `CHILD_NOT_FOUND` / `COACH_NOT_FOUND` / `SERVICE_NOT_FOUND` / `BOOKING_NOT_FOUND` / `EXERCISE_NOT_FOUND` / `TASK_NOT_FOUND` / `SUBMISSION_NOT_FOUND` / `SESSION_NOT_FOUND` | 资源不存在 |
| 400 | `VALIDATION_ERROR` | 参数校验失败（Pydantic，多余字段也会拒绝） |
| 409 | `BOOKING_CONFLICT` | 同一教练该时段已有预约 |
| 409 | `SLOT_NOT_AVAILABLE` | 所选时间不在教练开放档期 |
| 409 | `INVALID_STATE_TRANSITION` | 订单状态非法流转 |
| 409 | `TRAINING_RECORD_REQUIRED` | 未完成训练记录就想结束课程 |
| 409 | `COACH_NOT_APPROVED` / `AGE_OUT_OF_RANGE` | 教练未审核 / 儿童年龄不在课程适龄范围 |
| 500 | `INTERNAL_ERROR` | 服务端异常 |

列表接口统一分页参数 `page`（默认 1）、`pageSize`（默认 20，最大 100），返回：

```json
{"items":[...],"page":1,"pageSize":20,"total":42,"hasMore":true}
```

---

## 4. 家长端（PARENT）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/children` | 创建儿童档案（可创建多个） |
| GET | `/api/children` | 只返回自己有监护权限的儿童 |
| GET | `/api/children/{id}` | 档案详情 |
| GET | `/api/coaches` | 筛选教练（`sportType` / `area` / `availableOn`） |
| GET | `/api/coaches/{id}` | 教练详情 |
| GET | `/api/coaches/{id}/slots` | 真实可预约档期 |
| GET | `/api/services` | 课程列表 |
| POST | `/api/bookings` | 创建预约（模拟支付） |
| GET | `/api/bookings` | 自己的订单 |
| GET | `/api/bookings/{id}` | 订单详情 |
| POST | `/api/bookings/{id}/cancel` | 取消订单 |
| GET | `/api/children/{id}/training-records` | 训练记录 |
| GET | `/api/children/{id}/stars` | 成长星图 |
| GET | `/api/exercises` / `/api/exercises/{id}` | 运动知识库 |
| GET | `/api/videos` | 教学视频 |
| GET | `/api/tasks` | 家庭任务 |
| POST | `/api/tasks/{id}/submissions` | 提交任务完成记录（可传 `photoUrls`） |
| GET | `/api/tasks/{id}/submissions` | 查看提交记录 |
| POST | `/api/agent/chat` | AI Agent 对话 |
| GET | `/api/agent/sessions/{id}` | 会话与工具轨迹 |
| GET | `/api/auth/me` | 当前用户 |

创建儿童档案示例：

```http
POST /api/children
{"nickname":"小辰","age":7,"sportsInterests":["跳绳"],"trainingGoals":["协调性"]}
```

创建预约示例（金额由后端按课程价目表计算，前端**不要**传金额）：

```http
POST /api/bookings
{
  "childId": "c_xingxing",
  "serviceId": "svc_basketball",
  "startAt": "2026-11-14T09:00:00+08:00",
  "endAt":   "2026-11-14T10:00:00+08:00",
  "note": "第一次上门"
}
```

```json
{"success":true,"data":{
  "id":"bk_...","status":"PENDING","paymentStatus":"SIMULATED_UNPAID",
  "amountCents":19900,"amountYuan":"199.00","childId":"c_xingxing",
  "coachId":"coach_wang","serviceId":"svc_basketball",
  "startAt":"2026-11-14T01:00:00+00:00","endAt":"2026-11-14T02:00:00+00:00"
},"error":null,"requestId":"..."}
```

> 时间为 ISO-8601（UTC 输出，请求需带时区偏移）。订单状态只能由后端按
> `PENDING → ACCEPTED → IN_PROGRESS → COMPLETED` 推进，前端不能 PATCH 状态。

---

## 5. 教练端（COACH）

在家长端所有 GET 接口基础上（儿童数据仅在有已接单课程时可访问）：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/bookings/{id}/accept` | 接单 `PENDING → ACCEPTED`，同时置 `SIMULATED_PAID` |
| POST | `/api/bookings/{id}/start` | 开课 `ACCEPTED → IN_PROGRESS` |
| POST | `/api/bookings/{id}/complete` | 完成 `IN_PROGRESS → COMPLETED`，**自动发放成长星星** |
| POST | `/api/training-records` | 提交真实训练记录（完成课程前必须） |
| POST | `/api/tasks` | 布置家庭训练任务 |
| POST | `/api/tasks/{id}/submissions/{sid}/confirm` | 确认任务完成，**自动发放挑战星** |

训练记录示例：

```http
POST /api/training-records
{
  "bookingId": "bk_...",
  "content": "完成20分钟运球与平衡练习，单脚站立较上周更稳定",
  "durationMinutes": 20,
  "performance": {"balance": 4, "notes": "教练现场评价"}
}
```

`performance` 只允许 `strength / speed / endurance / coordination / balance / notes / source` 这些 key；**后端不会生成或推断任何身体指标**，数值必须由教练明确填写。

布置家庭任务示例：

```http
POST /api/tasks
{"childId":"c_xingxing","title":"平衡小勇士",
 "items":["单脚站立","敏捷梯","跨越障碍物"],"goalCount":3}
```

---

## 6. 管理员端（ADMIN）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/stats` | 用户/儿童/教练/订单状态/星星/模拟收入统计 |
| 其余 GET | 同上 | 可读取全部儿童档案与订单（用于审核） |

---

## 7. AI Agent 接口（核心亮点）

### `POST /api/agent/chat`

请求：

```json
{
  "message": "我家孩子8岁，协调性不太好，有没有适合他的运动？",
  "sessionId": null,
  "childId": "c_xingxing",
  "confirmationId": null,
  "context": {"sportType":"篮球基础","availableOn":"2026-11-14"}
}
```

`context` 为可选的演示辅助参数（给离线 mock 提供筛选条件），真实百炼模式下由模型从对话中理解。

响应：

```json
{
  "success": true,
  "data": {
    "sessionId": "as_...",
    "reply": "已结合儿童档案、真实训练记录和动作知识库生成结构化运动建议……",
    "llmMode": "mock",
    "model": "mock-starfit",
    "fcSupported": true,
    "mode": "function_calling",
    "toolRounds": 1,
    "toolCalls": [
      {"name":"get_child_profile","arguments":{"child_id":"c_xingxing"},"status":"success","result":{...}},
      {"name":"search_exercises","arguments":{},"status":"success","result":{...}}
    ],
    "pendingConfirmation": null,
    "tokenUsage": {"promptTokens":300,"completionTokens":70,"totalTokens":370,"calls":1,"models":["mock-starfit"]},
    "childId": "c_xingxing",
    "disclaimer": "本平台仅提供一般儿童体育活动建议，不构成医疗诊断……"
  },
  "error": null,
  "requestId": "..."
}
```

### Agent 工具（白名单，真实 Function Calling）

| 工具 | 作用 |
|---|---|
| `get_child_profile` | 读取**有权限的**儿童档案 |
| `get_training_history` | 真实历史训练记录 |
| `search_exercises` | 检索运动动作知识库 |
| `generate_training_plan` | 基于年龄/目标/真实记录生成结构化建议（只读，不落库） |
| `search_coaches` | 按运动类型/地区/日期筛选已审核教练 |
| `get_available_slots` | 查询真实档期（排除已预订） |
| `get_growth_progress` | 成长星图与训练进度 |
| `generate_course_report` | 基于真实训练记录生成课后反馈草稿 |
| `create_booking` | 创建预约（**必须确认令牌**） |
| `request_confirmation` | 为写入操作申请用户确认令牌 |

### 写入必须两步确认（前端必须实现）

1. 用户说「帮我预约教练」→ Agent 调用 `request_confirmation`，响应里出现 `pendingConfirmation`：

```json
"pendingConfirmation": {
  "confirmationId": "cf_xxx",
  "action": "create_booking",
  "summary": "创建预约订单（黑客松模拟支付，不产生真实扣款）"
}
```

此时**不会**创建订单。

2. 前端展示确认按钮，用户点击后回传令牌：

```json
{
  "message": "确认预约",
  "sessionId": "上一步返回的 sessionId",
  "childId": "c_xingxing",
  "confirmationId": "cf_xxx"
}
```

Agent 才会执行 `create_booking`。模型不能自行生成令牌，也不能绕过确认；伪造令牌会被 `INVALID_CONFIRMATION` 拒绝。同理 `generate_course_report` 带 `confirmationId` 才会保存为正式报告。

工具级错误在 `toolCalls[].result.error.code`：`TOOL_NOT_WHITELISTED`、`INVALID_TOOL_ARGS`、`CONFIRMATION_REQUIRED`、`INVALID_CONFIRMATION`、`TOOL_EXECUTION_ERROR` 等。

### `GET /api/agent/sessions/{id}`

返回会话、消息历史、每轮 `toolCalls` / `toolResults` 轨迹，可用于调试与演示「AI 真的调用了工具」。

---

## 8. 成长星图数据格式（前端可直接渲染）

`GET /api/children/{id}/stars`：

```json
{
  "success": true,
  "data": {
    "childId": "c_xingxing",
    "total": 2,
    "disclaimer": "成长星星仅记录真实完成的课程与家庭任务，不构成医学诊断或体能评估结论。",
    "constellations": [
      {"name": "启程座", "count": 1},
      {"name": "跃动座", "count": 1}
    ],
    "stars": [
      {
        "starId": "st_...",
        "childId": "c_xingxing",
        "starType": "FIRST_COURSE",
        "title": "启明星",
        "description": "完成首次上门体育课程，正式开启运动旅程",
        "sourceType": "BOOKING",
        "sourceId": "bk_...",
        "earnedAt": "2026-11-07T02:00:00+00:00",
        "metadata": {
          "color": "#FFD166",
          "constellation": "启程座",
          "stage": "起步",
          "animation": "ignite",
          "position": {"x": 58.0, "y": 50.0}
        }
      }
    ]
  },
  "error": null,
  "requestId": "..."
}
```

- `position.x / y` 是 0–100 的百分比坐标（黄金角确定性布局），前端按容器尺寸换算即可。
- `starType`：`FIRST_COURSE`(启明星)、`BALANCE`(平衡星)、`BASKETBALL`(篮球星)、`HOME_CHALLENGE`(挑战星)。
- `sourceType`：`BOOKING` 或 `TASK`；`sourceId` 是真实订单/任务 id。
- 同一次课程或同一个任务**只会发放一次**（数据库唯一约束 + 事务内校验），重复完成/重复确认不会多给星。
- 星星只能由后端按真实完成事件发放，**AI Agent 无权生成成长奖励**。

---

## 9. 完整演示链路（真实接口，非静态 JSON）

| 步骤 | 角色 | 请求 |
|---|---|---|
| 1 登录 | 家长 | `POST /api/auth/login` |
| 2 选择儿童 | 家长 | `GET /api/children` → `c_xingxing` |
| 3 询问 AI | 家长 | `POST /api/agent/chat`（推荐运动/结构化计划） |
| 4 查教练 | 家长 | `GET /api/coaches?sportType=篮球基础` → `GET /api/coaches/{id}/slots` |
| 5 预约 | 家长 | `POST /api/bookings` → `PENDING` |
| 6 接单 | 教练 | `POST /api/bookings/{id}/accept` → `ACCEPTED` |
| 7 开课 | 教练 | `POST /api/bookings/{id}/start` → `IN_PROGRESS` |
| 8 记录训练 | 教练 | `POST /api/training-records` |
| 9 完成课程 | 教练 | `POST /api/bookings/{id}/complete` → `COMPLETED`，返回 `starsAwarded` |
| 10 课后反馈 | 教练/家长 | `POST /api/agent/chat` + `context.bookingId` → 报告草稿 |
| 11 查看星图 | 家长 | `GET /api/children/c_xingxing/stars` → 新星球 |

> 所有步骤读写同一个 `prisma/dev.db`。数据由真实接口创建、读取、更新，不是静态 JSON。

---

## 10. 前端对接注意

1. **不要传金额**：`amountCents` 由后端按 `sf_service.priceCents` 确定。
2. **不要自行改订单状态**：只能用 accept/start/complete/cancel 四个动作端点。
3. **儿童数据隔离**：家长只能访问自己有监护关系的儿童；教练只能访问与自己已接单课程相关的儿童。前端传任意 `childId` 不会绕过后端校验。
4. **模拟支付**：`paymentStatus` 仅为 `SIMULATED_UNPAID` / `SIMULATED_PAID`，**没有任何真实扣款**。
5. **媒体资源**：演示数据中 `videoUrl` / `model3dUrl` / `thumbnailUrl` 一律为空字符串，表示「暂无资源」，不要当作可播放链接。
6. **AI 安全**：运动建议含免责声明；遇伤病/疼痛提示就医，不做医学诊断；AI 不能伪造训练记录或直接发星星。
7. **legacy 接口保留**：Node/Fastify 服务（端口 3000）与 `/api/v1/*` 未改动，原有前端不受影响。

---

## 11. AI 运动陪练（Motion Coach，MVP 1.1 新增）

架构：**摄像头 → 前端本地姿态识别 → 规则引擎（前后端同一份配置）→ 结构化事件 → 后端校验 → AI 只负责组织语言**。
每帧永远不调用大模型；不传视频/照片/原始关键点序列，只传结构化事件。

### 11.1 可直接使用的训练页

**页面入口（MVP 1.2）**：

| 地址 | 内容 |
|---|---|
| `http://127.0.0.1:8100/demo` | 演示控制台：教练列表 / 预约 / AI 助手 / 课后反馈 / 成长星图 / 动作库（六大功能，全部走真实 API） |
| `http://127.0.0.1:8100/motion-coach` | AI 运动陪练训练页（摄像头 + 实时骨架 + 动作计数 + 语音 + 模式 B） |

训练页基于 **MediaPipe Tasks Vision（PoseLandmarker）**，模型与运行时已 vendor 到 `backend/static/pose2/`，离线可用。摄像头必须运行在安全上下文（localhost 或 HTTPS）；非 HTTPS 打开会看到明确的修复指引。

后端自带一个**离线可用**的完整训练页（摄像头预览 + 骨架叠加 + 计数 + 语音播报 + 模式 B 提醒 + 星星结果）：

```
http://127.0.0.1:8100/static/coach/index.html
```

MediaPipe Pose 资源已 vendor 到 `backend/static/pose/`，无需外网。队友可以直接用它，或按下面的契约自己实现。

### 11.2 训练接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/training/exercises` | 支持姿态识别的 3 个动作 + `motionConfig`（判定阈值/错误规则/提示语） |
| GET | `/api/training/exercises/{id}` | 动作详情 + 配置 |
| POST | `/api/training/sessions` | 创建训练会话 `{childId, exerciseId, taskId?, mode?: "POSE"\|"GUIDED", targetReps?, targetSeconds?}` |
| GET | `/api/training/sessions?childId=` | 会话列表（家长/教练按权限隔离） |
| GET | `/api/training/sessions/{id}` | 会话详情：`counters`（实时计数）、`recentEvents`、`result` |
| POST | `/api/training/sessions/{id}/feedback` | 批量上报事件 `{events: [...]}`（每批 ≤100） |
| POST | `/api/training/sessions/{id}/complete` | 结束训练（**后端按规则判定达标**，幂等；达标自动发「陪练星」） |
| POST | `/api/agent/motion-coach/chat` | 陪练对话（模式 B 提醒/鼓励/总结；控制语句零模型调用） |

### 11.3 事件契约（前端 → 后端）

```json
{
  "events": [
    {"type": "REP",        "confidence": 0.92, "metrics": {"minKneeAngleInRep": 96, "repDurationMs": 1800}},
    {"type": "HOLD",       "confidence": 0.88, "holdMs": 1000},
    {"type": "FORM_ERROR", "code": "TRUNK_LEAN", "confidence": 0.9, "metrics": {"trunkLeanAngle": 63}},
    {"type": "POSE_LOST",  "confidence": 0.1}
  ]
}
```

- `type` 只允许 `REP / HOLD / FORM_ERROR / POSE_LOST / QUALITY_LOW`；`code` 必须来自 `motionConfig.errorRules`。
- `confidence < motionConfig.minConfidence` 的事件被拒收（响应 `rejected` 数组会给出原因）。
- 同一错误码 2 秒内自动去重；语音播报节流由 `motionConfig.voiceCooldownSeconds` 控制（前端本地做）。
- 识别不到人/关键点丢失 → 发 `POSE_LOST` 并提示调整镜头，**禁止猜测训练结果**。

### 11.4 完成与奖励（后端校验，前端无法伪造）

`POST .../complete` 不接受任何 `completed` 标志。达标条件来自 `motionConfig.completion`：
REPS 类需 `validRepCount ≥ targetReps`；HOLD 类需 `holdSeconds ≥ targetSeconds`。

```json
// 达标响应（200）
{
  "result": {"completed": true, "validRepCount": 8, "holdSeconds": 0.0, "durationSeconds": 46, "starAwarded": true, "...": "..."},
  "starsAwarded": [{"starType": "HOME_TRAINING", "title": "陪练星", "...": "..."}],
  "idempotent": false
}

// 未达标响应（422）
{"error": {"code": "TRAINING_REQUIREMENTS_NOT_MET", "message": "尚未达标：需要 8 reps，当前 5 reps。继续加油！"}}
```

重复调用 complete 幂等返回首次结果（`idempotent: true`），**绝不二次发星**。

### 11.5 模式 B（无摄像头）

不开摄像头也能用：`POST /api/agent/motion-coach/chat`，消息包含「开始/继续/做完了/总结」等控制词时走确定性状态机（毫秒级、零模型调用、不花钱），读取教练布置的家庭任务（`GET /api/tasks?childId=`）逐步提醒动作 → 组间休息 → 下一个。总结类消息才走百炼；百炼失败自动降级为规则模板（响应 `degraded: true`）。
