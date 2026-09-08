# StudyAgent 微信原生小程序二次复查与修复记录

日期：2026-09-08  
分支：`audit/wechat-release-gates-20260907`

## 结论

本记录是在 `AUDIT_REPORT_ROUND2_2026-09-08.md` 之后针对 `apps/wechat-miniprogram` 做的源码级二次复查。

当前结论：

```text
BACKEND_CORE_GATE = PASS
WECHAT_NATIVE_SOURCE_GATE = PASS
WECHAT_DEVTOOLS_RUNTIME_GATE = NOT_VERIFIED
WECHAT_REAL_DEVICE_GATE = NOT_VERIFIED
WECHAT_RELEASE_GATE = BLOCKED_EXTERNAL
```

这里的 `WECHAT_NATIVE_SOURCE_GATE = PASS` 仅表示本轮确认的原生客户端源码问题已修复且 CI 静态门禁通过，不等价于微信开发者工具运行态、真机或正式发布通过。

## 本轮已直接修复

### 1. 登录、退出与注销

- 修复“退出登录后立即自动重新登录”。
- 增加显式 signed-out 状态与首页“重新登录”。
- 注销账号后不再因为首页请求自动创建/登录新账号。
- 退出后访问知识库、学习、我的 Tab 会回到首页登录态，而不是堆积 401 错误。

### 2. 知识库

- 修复页面隐藏后轮询无法正确恢复的问题。
- 修复快速切换知识库时 A/B 请求竞态覆盖文档列表的问题。
- 增加轮询 in-flight 防重入。
- 文档局部错误不再把整个知识库页面永久锁死。
- 轮询仅在“文档”Tab 开启。
- 文件选择取消不再显示为上传错误。
- 文档删除增加二次确认。
- 补齐搜索、创建描述/图标/分类、编辑、归档/恢复、删除知识库。
- 补齐从当前知识库直接生成计划、生成测验。
- 补齐详情 `文档 / 知识点 / 历史对话` 三个 Tab。
- 知识点使用真实 `/knowledge-bases/{id}/mastery` 数据。
- 历史对话使用真实 `/conversations` 数据并可重新打开。

### 3. AI 对话

- 修复请求恢复后 error 状态未清除导致一直显示错误页。
- 删除当前正在查看的会话后自动创建新会话，避免继续向已删除会话发送消息。
- 删除会话增加确认。
- Citation 支持点击查看文档名、页码和原文片段。
- 发送失败时恢复输入并重新同步服务器消息。

### 4. 学习计划与学习分析

- 当前计划优先选择真实 `ACTIVE` 计划，避免最新 `DRAFT` 冒充当前计划。
- “生成今日测验”优先使用当前计划的 `knowledge_base_id`。
- 知识库到学习计划的跨 Tab 选择能够正确带入知识库。
- 日期改为微信原生 `picker mode="date"`。
- 创建计划、激活计划、生成测验增加防重复提交状态。
- 已完成任务不会重复提交完成动作。
- 接入真实 `/dashboard` 数据，展示：
  - 距离目标天数
  - 总完成度
  - 本周学习分钟
  - 测验正确率
  - 任务完成率
  - 薄弱知识点
  - 掌握度
  - 7 天学习趋势

### 5. Quiz

- 原生入口加入 `SHORT` 简答题。
- 增加 `submitting` 锁，防止双击重复交卷。
- 未答题确认逻辑同时识别空白简答。
- 判断题由 `true/false` 显示为“正确/错误”，提交值保持后端协议不变。
- 交卷中按钮显示明确状态。

### 6. 首页与 Profile

- 最近知识库限制为 3 个。
- 首页展示真实学习概览与薄弱知识点。
- Profile 去除不稳妥的原始 `<strong>`，改用原生 `<text>`。

## 自动化证据

本轮修改后的 GitHub CI：

- native-miniprogram JavaScript syntax：PASS
- Vue preview build：PASS
- backend compileall：PASS
- backend ruff：PASS
- backend pytest：PASS

并扩展 `apps/api/tests/test_wechat_package.py`，为 signed-out、知识库轮询、详情 Tab、Citation、学习分析、原生日期选择、Quiz 防重复提交等增加静态回归断言。

## 仍未伪造完成的事项

以下事项不能因本轮客户端修复而写成 PASS：

1. 微信开发者工具真实运行态、Console、Network。
2. Android/iOS 真机。
3. 正式 HTTPS 域名与微信合法域名；当前域名仍在备案审核。
4. 微信平台隐私、备案、AI 合规与最终审核。
5. Image2 Before/Design/After 真实页面图。

## 仍需后续处理的架构级产品缺口

这些不是本轮 WXML/WXSS/JS 修复可以安全伪装完成的功能：

### A. Agent 自然语言自主执行

后端已有受权限校验的 `/agent/execute` 和 Tool Audit，但当前 AI 对话仍主要走 RAG Chat；用户自然语言“帮我完成任务/查看进度”等尚未形成完整的 LLM Tool Selection → Business Tool → 持久化结果闭环。

### B. Memory 自动参与对话

后端已有 Memory CRUD、Extract、Relevant 接口，但普通 Chat 请求当前没有自动召回 Relevant Memory 并注入模型上下文。不能仅凭存在 Memory API 就宣称“跨会话自动记忆”完整通过。

### C. Quiz 来源筛选

`QuizIn` 已包含 `source_type`、`study_task_id`、`difficulty`，但当前创建测验的检索仍以整个知识库为主；“今日学习内容 / 错题 / 指定知识点”尚未形成真实的检索范围约束，因此原生端没有伪造这些筛选项。

### D. Quiz 类型不匹配 fallback

当前后端在模型题型与请求题型不一致时存在 fallback；其中 MULTIPLE fallback 仍需改成语义与多正确答案约束一致的生成策略，不能通过放宽校验掩盖。

### E. 学习页“最近测验”

当前后端没有用户级测验列表接口，原生端无法真实展示“最近测验”列表，因此本轮没有用假数据补齐。

### F. 连续学习天数

冻结需求包含连续学习天数，但当前 Dashboard 没有该真实指标；本轮未硬编码伪造。

## 后续验收顺序

域名备案期间可继续：

```text
微信开发者工具导入真实 AppID
→ 开发环境临时关闭合法域名校验
→ 六页面运行态检查
→ Console / Network
→ 上传真实资料
→ RAG / Citation
→ Plan / Quiz / Cleanup
→ 退出/重新登录/注销
→ 截取六页面真实 UI
```

域名备案通过后再进行：正式 HTTPS/WSS → 微信合法域名 → 正式 build → Android/iOS 真机 → 提审。
