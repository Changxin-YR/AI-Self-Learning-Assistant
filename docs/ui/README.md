# 原生小程序视觉验收证据

代码侧已完成六个原生页面的统一 WXSS/WXML 重构，并通过 JavaScript 静态检查。当前自动化环境未暴露可控的微信开发者工具窗口，因此不把静态包大小或二维码当作运行态编译证据。

当前工作区只保留开发者工具预览二维码和运行信息，未伪造页面截图：

- `before/`：等待真实 DevTools 页面截图采集。
- `design/`：未使用 image2；没有生成虚假设计图。
- `after/`：等待真实 DevTools 页面截图采集。

`IMAGE2_EXTERNAL_BLOCKER`：当前 Codex 环境没有 image2 能力。
`REAL_DEVICE_ANDROID/IOS = BLOCKED_EXTERNAL`：当前没有可操作的 Android/iOS 真机。
