# StudyAgent 第二轮收口审计报告

日期：2026-09-08  
分支：`audit/wechat-release-gates-20260907`  
基线：`8a412c5`

## 1. 最终结论

```text
FUNCTIONAL_GATE = PASS
WECHAT_CODE_GATE = PASS
WECHAT_RELEASE_GATE = BLOCKED_EXTERNAL
```

`FUNCTIONAL_GATE` 的代码侧 P0/P1 问题已关闭，后端单测、迁移、生产样 Docker 链路、RAG、Worker、Quiz、Plan、Agent、Memory、Cleanup 和原生 JavaScript 静态检查均通过。微信开发者工具窗口未被当前自动化环境暴露，未声称其运行态或真机通过。

`WECHAT_CODE_GATE` 的仓库可验证项全部通过。正式域名、平台合法域名、主体备案/AI 合规材料、微信后台审核和真实 Android/iOS 设备仍需外部配置或人工操作。

## 2. 修改统计

- 本轮提交：cleanup/safety、production-like E2E、微信构建和报告文档均按模块提交，完整历史见 `git log 8a412c5..HEAD`。
- 相对基线代码/门禁修改文件：24 个；新增代码约 1,183 行，删除 76 行；交付文档 3 个，合计 27 个文件。
- 测试：全量 50 条通过；新增 Cleanup 投递失败/过期 claim、内容安全输入/输出和生产 Provider 覆盖。
- 数据库迁移：`0006_cleanup_jobs`、`0007_content_safety`。
- 未删除既有失败测试；未提交 `tmp-build-log.json`。

## 3. Bug 修复表

| ID | 严重度 | 问题 | 根因 | 修复 | 测试 | 状态 |
|---|---|---|---|---|---|---|
| F-001~F-004 | P0 | 生产 RAG/Worker/Provider 失真或静默 Fake | 向量链路和环境边界不完整 | Embedding → Qdrant TopK、用户/知识库过滤、Worker 同配置、生产 Fake fail-fast | `test_quality_gates.py`、Docker E2E | PASS |
| F-005~F-008 | P0 | Quiz、Plan、Dashboard 使用硬编码或错误统计 | 未从真实资料/任务/答卷聚合 | 结构化 AI 生成、真实任务/答卷/Mastery/趋势聚合 | 全量 pytest、Docker E2E | PASS |
| F-009~F-011 | P0 | 登录竞态、首页入口/任务伪造 | 前端启动与数据绑定不完整 | auth promise/401 重试、点击项绑定、空数据真实展示 | 原生 JS 检查、后端回归 | PASS |
| F-012~F-015 | P1 | 计划重复激活、未答题、简答评分和解析缺失 | 状态和评分模型不完整 | 唯一约束/幂等激活、未答记错、Rubric 评分、逐题结果 | Quiz/Plan 测试、E2E | PASS |
| F-016~F-018 | P1 | 会话历史、Citation、流式能力缺口 | 原生端未接完整历史/引用 | 会话列表/删除/恢复、多 Citation；REST 保持真实非伪流式，WebSocket 保留 token 流 | 原生 JS 检查、API 测试 | PASS |
| F-019~F-021 | P1 | 文档状态、重建和跨服务删除不可靠 | 外部资源删除为 best-effort | `cleanup_jobs` 持久化、状态/重试/人工 retry、过期 PROCESSING claim 恢复、Storage/Qdrant 用户隔离；删除先提交 DB 再投递 | Cleanup 失败、重试、隔离、投递失败、过期 claim、E2E | PASS |
| F-022~F-025 | P1 | 文件攻击面、readiness、CORS、JWT 风险 | 校验和生产配置不足 | 流式大小限制、MIME/魔数/ZIP 防护、真实依赖探测、CORS/JWT fail-fast | 质量门禁和 Provider 测试 | PASS |
| F-026~F-030 | P1 | Profile 假入口、长期记忆和原生功能缺口 | 页面与后端能力未闭环 | 真实隐私/AI 说明与删除入口、结构化 Memory CRUD/抽取/召回、六页功能保留 | 原生 JS 检查、Memory/IDOR 测试 | PASS |
| R-007 | P1 | 内容安全未闭环 | 仅依赖模型自拒答 | 可替换 Provider、输入/输出/上传审核、PASS/REVIEW/BLOCK、日志、举报和内部审核 API | `test_safety.py` | PASS（代码侧） |

## 4. 自动化测试

| 命令 | 结果 |
|---|---|
| `pytest -q apps/api/tests` | 50 passed，0 failed |
| `ruff check --select F apps/api/app apps/api/tests scripts` | PASS |
| `python -m compileall -q apps/api scripts` | PASS |
| `alembic upgrade head` | PASS |
| `npm run build`（`apps/miniprogram`） | PASS |
| 原生小程序全部 JS `node --check` | PASS |
| `python scripts/check_wechat_release.py --code-only` | 15 PASS / 0 FAIL |
| `python scripts/e2e_production_like.py --check` | PASS |

## 5. Production-like E2E

`python scripts/e2e_production_like.py` 已真实启动 Docker Compose 中的 MySQL 8.4、Redis 7、MinIO、Qdrant、FastAPI 和 Celery Worker，配置 `APP_ENV=production`、`DEV_MODE=false`，并显式使用仅限 E2E 的 `TEST_LLM_PROVIDER`。

通过链路：微信登录测试 Provider → 知识库 → MinIO 上传 → Celery 解析/切片/Embedding/Qdrant → RAG Citation → Plan/Activate/Today Tasks → Quiz Submit/未答题/WrongQuestion/Mastery → Agent tools → Memory → 删除文档 → Cleanup Job → MinIO/Qdrant 为空 → 删除后检索无 Citation。

生产配置中 Fake LLM、Fake Embedding、Fake Vector、Local Storage、弱 JWT、缺 Redis/Qdrant 均有 fail-fast 测试；`TEST_*` 只由 E2E 显式开启。

## 6. 微信开发者工具

- 编译：当前环境未暴露可控的微信开发者工具窗口，未伪造 PASS。
- Console/Network：未取得真实 DevTools 运行态证据。
- 真机：未执行。
- 原生源码 JS 静态检查：PASS。
- Vue 预览构建：PASS，但未用作原生小程序截图替代。

## 7. UI

六个原生页面均保留原业务入口并完成统一 WXSS/WXML 视觉重构：首页、知识库、学习计划、AI 对话、测验、我的。统一背景/主色/卡片/间距/空态/错误/加载/AI 标识；Profile 的“AI 生成说明”“数据与隐私”“关于”均为可操作展示，删除账号进入真实删除流程。

| 页面 | Before | Design | After | 功能一致性 |
|---|---|---|---|---|
| 首页 | 未采集 | `IMAGE2_EXTERNAL_BLOCKER` | 未采集 | 源码保留 Dashboard、知识库和四个快捷入口 |
| 知识库 | 未采集 | `IMAGE2_EXTERNAL_BLOCKER` | 未采集 | 保留创建、上传、轮询、重试、重建、删除、问 AI |
| 学习计划 | 未采集 | `IMAGE2_EXTERNAL_BLOCKER` | 未采集 | 保留参数填写、草案确认、今日任务、测验 |
| AI 对话 | 未采集 | `IMAGE2_EXTERNAL_BLOCKER` | 未采集 | 保留历史、新建、删除、多 Citation、加载/重试 |
| 测验 | 未采集 | `IMAGE2_EXTERNAL_BLOCKER` | 未采集 | 保留单选、多选、判断、简答、结果和解析 |
| 我的 | 未采集 | `IMAGE2_EXTERNAL_BLOCKER` | 未采集 | 保留统计、隐私说明、账号删除、退出登录 |

未生成或伪造 Image2 设计图；`docs/ui/README.md` 记录了当前证据边界。

## 8. 上架检查

| 项目 | 结果 |
|---|---|
| AppID | 仓库存在非游客格式值；归属和主体需微信平台核验 |
| HTTPS/API/域名 | 生产构建强制注入 HTTPS 域名；当前开发配置为 LAN HTTP |
| `devMode` / `urlCheck` | 生产构建固定 `false` / `true`；开发配置保留本地调试值 |
| Privacy | `__usePrivacyCheck__`、`chooseMessageFile` 声明、协议草案已对齐；平台指引需人工同步 |
| Filing | 需主体按实际情况办理/核验 |
| AI Label | Chat、Plan、Quiz、解析、简答评分均显示 `AI 生成 · 请核验重要信息` |
| AI Registration | 未伪造登记/备案号，需按主体和供应商核验 |
| Content Safety | 代码层 PASS；生产审核供应商需配置真实适配器 |
| Release Config | `npm run build:wechat:production` 缺真实 HTTPS/AppID 时非零失败；代码预检 15/15 |

## 9. External Blockers

- `EXTERNAL BLOCKER: PRODUCTION_HTTPS_DOMAIN`：正式 API、上传/下载和可选 WSS 域名、证书及微信合法域名配置。
- `EXTERNAL BLOCKER: WECHAT_PLATFORM_ACCOUNT`：真实 AppID/AppSecret 归属、隐私保护指引、备案和提审审核。
- `EXTERNAL BLOCKER: AI_COMPLIANCE_MATERIALS`：主体适用的生成式 AI 备案/登记及模型供应商核验材料。
- `EXTERNAL BLOCKER: REAL_DEVICE_ANDROID`：Android 真机验收。
- `EXTERNAL BLOCKER: REAL_DEVICE_IOS`：iOS 真机验收。
- `IMAGE2_EXTERNAL_BLOCKER`：当前环境没有 image2 能力；没有伪造设计图。
- 当前未将任何纯代码问题列为 External Blocker。

## 10. Git

- Branch：`audit/wechat-release-gates-20260907`
- Commits：按模块提交；基线到当前的完整列表以 `git log 8a412c5..HEAD` 为准。
- PR：继续现有 Draft PR #1，未创建第二个 PR。
- CI：`ci.yml` 保留 push/PR 基础检查；`release-gate.yml` 为 `workflow_dispatch`，包含测试、迁移、production-like E2E、编译、ruff、Vue build、原生 JS 和微信代码门禁。

## 11. 已知问题

仅剩外部验证项：微信开发者工具运行态截图/Console/Network、Android/iOS 真机、正式域名和平台后台配置、主体备案与 AI 合规材料。代码侧未发现待修 P0/P1。
