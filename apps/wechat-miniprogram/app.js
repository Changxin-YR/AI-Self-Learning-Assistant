const config = require('./config')
const request = require('./utils/request')

App({
  globalData: { user: null, ready: false },
  onLaunch() {
    const login = config.devMode
      ? request.post('/auth/dev-login', { nickname: '微信学习者' })
      : new Promise((resolve, reject) => wx.login({
        success: ({ code }) => request.post('/auth/wechat/login', { code }).then(resolve, reject),
        fail: reject
      }))
    login.then(data => this.saveAuth(data)).catch(() => wx.showToast({ title: '登录失败，请检查 API', icon: 'none' }))
  },
  saveAuth(data) {
    wx.setStorageSync('study-agent-token', data.access_token)
    this.globalData.user = data.user
    this.globalData.ready = true
  }
})
