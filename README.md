# StudyAgent

基于微信小程序 + FastAPI + MySQL + Redis 构建 AI 学习平台，引入 RAG、向量检索、Agent Tool Calling 与长期记忆机制，实现课程资料知识库、智能问答、自动出题、学习计划生成及 Agent 自主任务执行；完成用户权限、文件存储、异步任务、日志审计及 Docker 化部署。

StudyAgent 是一个基于个人学习资料的 AI 知识库助手。当前仓库提供 FastAPI API、Vue 3/TypeScript Web 预览端，以及可直接导入微信开发者工具的原生小程序发布包 `apps/wechat-miniprogram`。

## 已完成

- DEV_MODE 登录、签名 Token、401 处理与用户级资源隔离
- 知识库 CRUD、文件扩展名/大小校验、TXT/MD 实际解析、切片和 READY 状态
- DEV_MODE 使用 Fake Embedding/LLM 的可重复 RAG；生产通过 Embedding + Qdrant TopK 过滤检索并返回可追溯 citation，资料不足时明确拒答
- 学习计划草案、确认激活、今日任务与完成状态
- 结构化测验生成、答题阶段隐藏标准答案、提交评分、错题记录与重复提交保护
- 首页、知识库、学习、我的四个 Tab，加载/空态/错误/上传状态/聊天状态
- Alembic 初始迁移与生命周期迁移、Docker Compose、CI 工作流和 `.env.example`
- 微信小程序四 Tab、微信登录回退、资料上传、AI 问答、学习计划、任务完成、测验答题与结果页

## 本地启动

后端：

```bash
cd apps/api
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd apps/miniprogram
npm install
npm run dev
```

打开 `http://localhost:5173`。开发版会自动调用 `/api/v1/auth/dev-login`，无需微信凭据。

完整基础设施：

```bash
copy .env.example .env
docker compose -f deploy/docker-compose.yml up --build
```

微信小程序：打开 `apps/wechat-miniprogram`，按该目录 README 配置 AppID、HTTPS API 域名和微信合法域名。

## 配置

默认 `DATABASE_URL` 使用 SQLite，适合本地快速验证。生产环境将其改为 MySQL URL，并填写 `JWT_SECRET`、微信配置和 OpenAI-compatible Provider 配置。`.env` 已被 git 忽略，禁止提交密钥。

## 测试

```bash
cd apps/api
pytest -q
cd ../miniprogram
npm run build
```

API 健康检查：`GET /health`；依赖就绪检查：`GET /ready`。

## 目录

```text
apps/api/app/main.py        FastAPI 路由、领域模型与 DEV Provider
apps/api/tests/             主链路与 IDOR 测试
apps/api/alembic/           数据库迁移
apps/miniprogram/src/       Vue 3 Web 预览工作台
apps/wechat-miniprogram/    微信开发者工具可导入的小程序发布包
deploy/docker-compose.yml   MySQL/Redis/Qdrant/MinIO/API/Worker
```

## 已知限制

开发模式使用 SQLite、Fake AI 和本地对象存储；生产启动会拒绝 Fake/Local，并探测 MySQL、Redis、S3、Qdrant、LLM 和 Embedding。微信正式发布仍需要真实 AppID、HTTPS 域名、微信合法域名、隐私协议、备案/AI 合规材料和真机审核，这些不能由本地代码代替。
