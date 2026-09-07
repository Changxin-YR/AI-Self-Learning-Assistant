# StudyAgent 微信小程序发布包

这是可直接导入微信开发者工具的原生小程序客户端，复用 `apps/api` 的 REST API。

## 开发

1. 用微信开发者工具打开本目录。
2. 在 `config.js` 修改 `apiBaseUrl`。本地调试可使用 `http://127.0.0.1:8000/api/v1`，真机和发布必须使用 HTTPS 域名。
3. 本地无 AppID 可使用 `touristappid` 预览；正式发布前必须替换 `project.config.json` 的 `appid`。
4. `config.js` 的 `devMode` 仅在本地开启。生产环境设为 `false`，并在服务端配置 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`。
5. 在微信公众平台配置 request 合法域名、uploadFile 合法域名和 websocket 合法域名，均指向 API 网关。

## 发布前检查

- `DEV_MODE=false`，不允许开发登录回退。
- `JWT_SECRET` 使用至少 32 字节随机值。
- API、对象存储和 WebSocket 全部使用 HTTPS/WSS。
- 参考仓库 `docs/compliance/` 完成微信隐私保护指引、用户协议和资料删除流程；本地 `privacy.json` 不代表平台审核完成。
- 在开发者工具执行“预览”和“真机调试”，再上传代码、提交体验版和审核。
