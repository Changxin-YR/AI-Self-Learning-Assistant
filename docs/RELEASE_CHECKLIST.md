# StudyAgent 发布清单

## 已由代码完成

- [x] 原生微信小程序包，可由微信开发者工具直接导入
- [x] 四个 Tab：首页、知识库、学习、我的
- [x] 微信登录接口与 DEV_MODE 登录回退
- [x] 知识库、资料上传、文档状态、AI 问答、引用、学习计划、任务、测验、结果
- [x] 标准 HS256 JWT、用户级 IDOR 隔离、上传扩展名/大小校验
- [x] PDF/DOCX/PPTX/TXT/MD 解析适配器
- [x] MySQL/Redis/Celery/Qdrant/MinIO 配置与 Docker Compose
- [x] Alembic `0001_initial` + `0002_production_fields`
- [x] CI、后端测试、前端构建、微信端 JavaScript 语法检查

## 发布前必须配置

1. 将 `apps/wechat-miniprogram/project.config.json` 的 `appid` 替换为真实 AppID。
2. 将 `apps/wechat-miniprogram/config.js` 的 `apiBaseUrl` 改成 HTTPS API 网关，并将 `devMode` 改为 `false`。
3. 服务端设置至少 32 字节随机 `JWT_SECRET`，并配置 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`。
4. 设置 `DATABASE_URL=mysql+pymysql://...`、`REDIS_URL`、`STORAGE_PROVIDER=s3`、`VECTOR_PROVIDER=qdrant` 和对应 MinIO/Qdrant 参数。
5. 设置 `LLM_PROVIDER=openai_compatible`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`，先做成本和超时压测。
6. 在微信公众平台配置 request、uploadFile、socket 合法域名和隐私保护指引。
7. 执行 `docker compose -f deploy/docker-compose.yml up --build`，确认 `/ready` 返回依赖正常。
8. 用真实 AppID 在开发者工具完成预览、真机调试、体验版上传和审核提交。

## 审核注意

本地 `touristappid`、`DEV_MODE=true`、`http://127.0.0.1` 只用于开发，不能进入正式版本。微信审核、域名备案、隐私协议、内容安全和第三方模型资质需要在微信公众平台及云环境中完成。
