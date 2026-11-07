# 跃星 PLAY ORBIT / SportLink

面向家长和儿童的电脑端运动成长平台。本地演示包含教练目录、课程预约、教练和管理工作台、运动陪练和成长星图。人物、课程、费用及反馈为合成演示资料。

- [家长端源码](sylva/) 使用 React、Vite 和 Three.js。
- [后端与工作台](sportlink-backend/) 使用 FastAPI 和 SQLite，并提供教练端、管理端、演示控制台及陪练页面。
- [设计规范](DESIGN.md) 记录页面、组件和成长星图规则。

## 本地启动

准备 Node.js 20.19+ 或 22.12+ 和 Python 3.11+。在仓库根目录打开两个终端。

```sh
cd sportlink-backend
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
SOLOPILOT_LLM_MODE=mock .venv/bin/python -m backend.run
```

```sh
cd sylva
npm ci
npm run dev:web -- --host 127.0.0.1
```

FastAPI 监听 `127.0.0.1:8100`，首次启动会创建 SQLite 演示数据。Vite 默认监听 `127.0.0.1:5173`，并把 API 和工作台请求转发给 FastAPI。

| 入口 | 地址 |
| --- | --- |
| 家长端 | [localhost:5173](http://localhost:5173/) |
| 教练订单 | [localhost:5173/coach-app#/coach/orders](http://localhost:5173/coach-app#/coach/orders) |
| 管理订单 | [localhost:5173/coach-app#/admin/orders](http://localhost:5173/coach-app#/admin/orders) |
| 成长星图 | [localhost:5173/universe](http://localhost:5173/universe) |
| 运动陪练 | [localhost:5173/motion-coach](http://localhost:5173/motion-coach) |
| API 文档 | [localhost:5173/docs](http://localhost:5173/docs) |

家长进入演示家庭后选择孩子与教练，再提交预约。教练工作台切换到对应的演示教练账号后可以处理预约，管理端可查看订单状态。教练保存反馈并确认完课后，家长可以在成长星图中查看训练新星。
