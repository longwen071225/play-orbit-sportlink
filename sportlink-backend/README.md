# SportLink（星动到家）· 黑客松全栈项目

儿童上门体育预约平台：**FastAPI 单后端（端口 8100）+ 双 AI Agent（预约管家 / 运动陪练）+ 浏览器本地姿态识别训练页 + 可视化演示控制台**。本目录是当前唯一在维护和运行的项目根目录。

> 历史说明：目录里同时保留了一份 legacy Node/Fastify 服务（`src/`，原 SoloCoach/SoloPilot，端口 3000，文档见第 7 节之后与 `README_SoloPilot.md`）。它未被删除、与本 Python 后端共用同一 SQLite 文件；日常演示与开发只依赖 Python 后端。

## 1. 一分钟启动（当前真实入口）

```powershell
cd 本目录
.\.venv\Scripts\python.exe -m backend.run          # 或: python -m uvicorn backend.app:app --host 127.0.0.1 --port 8100
```

| 地址 | 内容 |
|---|---|
| `http://127.0.0.1:8100/demo` | 演示控制台：教练列表 / 预约 / AI 助手 / 课后反馈 / 成长星图 / 动作库 |
| `http://127.0.0.1:8100/motion-coach` | AI 运动陪练：摄像头 + 实时骨架 + 动作计数 + 语音 + 模式 B 提醒 |
| `http://127.0.0.1:8100/docs` | Swagger（全部接口，含 🔒 角色标注） |
| `http://127.0.0.1:8100/api/starfit/health` | 平台健康检查（llmMode / fcSupported） |

演示账号密码统一 `demo123456`：家长 `13800000001`、教练 `13900000001`、管理员 `13700000000`。重置演示数据：`.\.venv\Scripts\python.exe -m backend.starfit.seed --reset`。前端对接契约见 `FRONTEND_API.md`。

## 2. 测试（两套都在 `tests/`）

```powershell
.\.venv\Scripts\python.exe -m pytest -q        # Python 后端：34 passed / 1 skipped
npm test                                        # legacy Node 服务：vitest（23 passed）
```

- `1 skipped` = `tests/test_flow_real.py`（需要把真实百炼 Key 通过 OS 环境变量注入的选测用例，离线套件有意跳过，不是失败）。
- 测试隔离：conftest 用独立 SQLite（`prisma/solopilot_test.db`）+ mock LLM，不碰 `prisma/dev.db`。

## 3. 目录结构（真实）

```
backend/            FastAPI 应用（唯一后端服务）
  app.py            create_app：CORS/统一信封/异常处理/静态资源挂载
  config.py         SOLOPILOT_* 环境变量（Key 只在服务端）
  llm.py            百炼客户端（超时/重试/降级模型/token 统计）
  starfit/          平台模块：auth/routes/services/schema/seed/stars
    agent.py        预约 Agent（白名单工具→Pydantic→幂等→确认门禁）
    coach.py        运动陪练 Agent（独立提示词+只读工具子集+模式B提醒）
    pose.py         动作规则引擎（深蹲/开合跳/单脚站立，配置即契约）
  static/
    motion/         /motion-coach 训练页（MediaPipe Tasks Vision，本地姿态识别）
    demo/           /demo 演示控制台（单文件 SPA，无框架无 CDN）
    pose2/          PoseLandmarker 模型与 WASM 运行时（离线可用）
    swagger-ui/     自托管 Swagger 静态资源
tests/              pytest（StarFit + legacy 流程）与 vitest（legacy 单测）
prisma/             SQLite（dev.db 运行数据）与 legacy 迁移
src/                legacy Node/Fastify 服务（保留，不影响 Python 后端）
```

## 4. 注意

- **密钥**：`backend/.env` 的 `SOLOPILOT_DASHSCOPE_API_KEY` 只存服务端；`SOLOPILOT_STARFIT_SECRET` 生产环境必须设置。两者均已被 .gitignore 忽略。
- **姿态识别阈值**为训练演示调参值，不构成医学标准（页面与 API 均有声明）。
- **目录里没有其他可运行的副本**：`myagents_files/` 下同级存在过 `福建黑客松_1` 等复制目录，均为历史副本，请勿在其内启动服务。

---

# 以下为 legacy SoloCoach/SoloPilot Node 服务的历史文档（未删除，端口 3000）

面向独立体育教练「一人公司」的 AI 员工系统后端：AI 销售、课程规划、商务报价、客户跟进、预约管理与总控编排，完成「家长咨询 → 预约成交」的业务闭环。

- **仅后端**，不含前端页面。
- Node.js 20+ / TypeScript / Fastify 5 / Prisma 6 / SQLite / Zod 3。
- 大模型走 OpenAI SDK 兼容接口接阿里云百炼（DashScope），`baseURL` / `apiKey` / `model` 全部来自环境变量，**代码中不含任何密钥**。
- 无 API Key 时自动进入 **mock AI 模式**，离线也能跑通完整业务链路。
- 所有 `/api/*` 响应统一为 `{ "success": ..., "data": ..., "error": ..., "requestId": ... }`。
- 金额由后端按可配置价目表确定性计算，大模型不参与定价；预约与外部发送必须人工确认。
- 不接入真实支付、短信、第三方预约平台；不做医疗诊断/康复建议。客户与儿童信息均为虚构演示字段。

---

## 1. 安装

```bash
npm install
cp .env.example .env          # Windows: copy .env.example .env
npm run prisma:generate
npm run db:migrate            # 应用 prisma/migrations 里的初始迁移
npm run db:seed               # 写入虚构演示数据
```

> 仓库已附带一份可直接用的 `.env`（`DASHSCOPE_API_KEY` 为空 → mock 模式）。生产环境请复制 `.env.example` 并填写自己的 Key，`.env` 已被 `.gitignore` 忽略。

## 2. 启动

```bash
npm run dev                   # tsx watch，http://localhost:3000
# 或
npm run build && npm start
```

- Swagger UI：<http://localhost:3000/documentation>
- OpenAPI JSON：<http://localhost:3000/documentation/json>
- 静态快照：`docs/openapi.json`（`npm run docs:generate` 重新生成）
- 健康检查：`GET /api/health`（返回 `mockAI`、当前模型、当前价目表）

## 3. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` / `HOST` | `3000` / `0.0.0.0` | 监听地址 |
| `NODE_ENV` | `development` | `development` / `test` / `production` |
| `LOG_LEVEL` | `info` | pino 日志级别 |
| `CORS_ORIGIN` | `*` | 开发环境 CORS；可填逗号分隔的域名白名单 |
| `DATABASE_URL` | `file:./dev.db` | SQLite 文件（相对 `prisma/` 目录） |
| `DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 百炼 OpenAI 兼容端点 |
| `DASHSCOPE_API_KEY` | 空 | 真实密钥；**仅从环境变量读取** |
| `DASHSCOPE_MODEL` | `qwen-plus` | 模型名 |
| `MOCK_AI` | `auto` | `auto`=无 Key 时用 mock；`true`=强制 mock；`false`=强制真实模型 |
| `PRICE_SINGLE_CENTS` | `12900` | 单节课单价（分） |
| `PRICE_PACKAGE_4_CENTS` | `49900` | 四节套餐价（分） |
| `PACKAGE_SESSIONS` | `4` | 套餐包含节数 |

改价只需改环境变量并重启，无需改代码。

## 4. 统一响应格式

成功：

```json
{ "success": true, "data": { "...": "..." }, "error": null, "requestId": "uuid" }
```

失败：

```json
{ "success": false, "data": null,
  "error": { "code": "BOOKING_CONFLICT", "message": "该时间段已有预约，请另选时间" },
  "requestId": "uuid" }
```

`requestId` 同时通过 `x-request-id` 响应头返回。常见错误码：`VALIDATION_ERROR`、`LEAD_NOT_FOUND`、`BOOKING_CONFLICT`、`INVALID_STATE_TRANSITION`、`COACH_INSUFFICIENT_INFO`、`LLM_INVALID_RESPONSE`、`LLM_NOT_CONFIGURED`。

## 5. 接口一览

| 方法 | 路径 | 模块 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/leads` | A 创建咨询客户 |
| `GET` | `/api/leads` | A 客户列表（可按 `status` 过滤） |
| `GET` | `/api/leads/:id` | A 客户详情 + 咨询记录 |
| `POST` | `/api/leads/:id/messages` | A 保存家长消息 |
| `POST` | `/api/agent/sales` | B AI 销售员工 |
| `POST` | `/api/agent/coach` | C AI 课程员工 |
| `POST` | `/api/agent/quote` | D AI 商务员工 |
| `POST` | `/api/agent/followup` | F AI 跟进员工 |
| `POST` | `/api/agent/run` | G AI 总控员工 |
| `POST` | `/api/bookings` | E 创建待确认预约 |
| `GET` | `/api/bookings` | E 预约列表 |
| `PATCH` | `/api/bookings/:id/confirm` | E 确认预约 |

客户状态：`new → consulting → quoted → booked → closed`。预约状态：`pending → confirmed`（只有 `PATCH .../confirm` 能推进）。

## 6. 接口示例

```bash
# 1) 创建客户
curl -s -X POST http://localhost:3000/api/leads \
  -H 'Content-Type: application/json' \
  -d '{"parentName":"林女士（虚构）","contact":"demo-wechat-001","childAge":8,"goal":"跳绳","location":"福州市鼓楼区（虚构）"}'
# 记下返回的 data.id，设为 LEAD_ID

# 2) AI 销售：抽取信息 / 追问
curl -s -X POST http://localhost:3000/api/agent/sales \
  -H 'Content-Type: application/json' \
  -d '{"leadId":"LEAD_ID","message":"我家孩子8岁，想提升跳绳和体能，零基础，周末下午可以上课"}'

# 3) AI 课程：四周计划
curl -s -X POST http://localhost:3000/api/agent/coach \
  -H 'Content-Type: application/json' \
  -d '{"leadId":"LEAD_ID"}'

# 4) AI 商务：报价（金额后端算）
curl -s -X POST http://localhost:3000/api/agent/quote \
  -H 'Content-Type: application/json' \
  -d '{"leadId":"LEAD_ID","preferredSessions":4}'

# 5) 总控：一次编排整条链路
curl -s -X POST http://localhost:3000/api/agent/run \
  -H 'Content-Type: application/json' \
  -d '{"leadId":"LEAD_ID","message":"我家孩子8岁，想提升跳绳和体能，零基础，周末下午可以上课，住在鼓楼区"}'

# 6) 人工确认时间后，才能创建待确认预约
curl -s -X POST http://localhost:3000/api/bookings \
  -H 'Content-Type: application/json' \
  -d '{"leadId":"LEAD_ID","startAt":"2026-12-05T10:00:00+08:00","endAt":"2026-12-05T11:00:00+08:00"}'

# 7) 用户显式确认
curl -s -X PATCH http://localhost:3000/api/bookings/BOOKING_ID/confirm

# 8) 跟进话术草稿（不发送）
curl -s -X POST http://localhost:3000/api/agent/followup \
  -H 'Content-Type: application/json' \
  -d '{"leadId":"LEAD_ID"}'
```

## 7. 演示流程（推荐顺序）

1. `GET /api/health` 确认 `mockAI: true` 与当前价目表。
2. `POST /api/leads` 建客户。
3. `POST /api/agent/run` 跑总控：返回每一步的 `status / result / durationMs / log` 与结构化 `nextStep`（下一步建议），并真实写入 `Message`、`TrainingPlan`、`Quote`、`QuoteItem`、`AgentRun`、`AgentAction`。
   - 信息不全时 `status = needs_input`，`coach`/`quote` 为 `skipped`，`nextStep.action = ask_parent` 并附追问话术；补全信息后再跑一次即可生成方案与报价。
   - 信息齐全时 `nextStep.action = confirm_booking`；`booking` 与 `external_send` 永远是 `awaiting_confirmation`，**不会**自动创建预约或发送消息。
4. `GET /api/leads/:id` 查看客户详情，确认方案、报价、消息、编排日志都已落库。
5. 家长确认时间 → `POST /api/bookings`（始终 `pending`）→ `PATCH /api/bookings/:id/confirm`（唯一改成 `confirmed` 的入口，客户状态同步变 `booked`）。
6. `POST /api/agent/followup` 生成跟进草稿（`sent: false`）。

切到真实模型：在 `.env` 填 `DASHSCOPE_API_KEY` 并设 `MOCK_AI=false`，其余流程不变。所有模型输出都会被 Zod 校验，解析/校验失败会自动带修正提示重试一次，两次仍失败返回 `LLM_INVALID_RESPONSE`。

## 8. 测试

```bash
npm test
```

覆盖：客户创建与统一信封、报价确定性计算（含「模型注入价格被剥离」）、预约冲突与确认门禁、AI JSON 解析与重试一次、总控端到端编排与人工确认门禁。测试使用独立的 `prisma/test.db`，`globalSetup` 会先应用迁移，`MOCK_AI=true` 无需网络。

```bash
npm run build        # tsc 类型检查（含 src / prisma / tests / scripts）
npm run docs:generate # 重新生成 docs/openapi.json
```

## 9. 目录结构

```
prisma/
  schema.prisma            数据模型：Lead/Message/TrainingPlan/Quote/QuoteItem/Booking/AgentRun/AgentAction
  migrations/              初始 SQL 迁移
  seed.ts                  虚构演示数据
src/
  config/env.ts            Zod 校验的环境变量 + mock 模式判定
  config/pricing.ts        可配置价目表 + 确定性金额计算
  db/prisma.ts             Prisma 单例
  llm/client.ts            OpenAI SDK 兼容百炼（全部读环境变量）
  llm/complete.ts          JSON 抽取 + Zod 校验 + 失败重试一次
  llm/prompts.ts           四类员工 system prompt
  schemas/                 请求 / LLM 输出的 Zod schema
  services/               客户 / 预约 / 方案 / 报价 + agents/*
  routes/                 各模块路由
  app.ts / server.ts       Fastify 装配（CORS / Swagger / 错误处理 / requestId）
scripts/generate-openapi.ts
tests/
docs/openapi.json
```

## 10. 设计约束说明

- **不编造信息**：销售员工的输出 schema 中未知字段必须为 `null`；后端 `sanitizeSales` 会按实际值重算 `missingFields`，信息不全时强制 `recommendedService = ask_more` 且回复必须发问。
- **不做医疗判断**：课程员工的 system prompt 禁止医疗/康复内容，且 `disclaimer` 由后端固定覆盖，模型无法改写。
- **价格不可被模型篡改**：`QuoteOutputSchema` 没有任何金额字段；`computeQuote()` 只读价目表，`Quote` / `QuoteItem` 金额全部由它产生。
- **人工确认边界**：总控与跟进只产出草稿与「待确认预约建议」；`POST /api/bookings` 只创建 `pending`，`PATCH .../confirm` 是唯一确认入口。
- **演示数据**：seed 里的姓名、联系方式、地址全部标注「虚构」，不接入任何真实支付/短信/预约平台。
