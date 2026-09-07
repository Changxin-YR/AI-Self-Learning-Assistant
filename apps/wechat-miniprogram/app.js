const config = require('./config')
const request = require('./utils/request')

App({
  globalData: { user: null, ready: false, authPromise: null },
  onLaunch() {
    this.ensureAuth().catch(() => wx.showToast({ title: '登录失败，请检查 API', icon: 'none' }))
  },
  ensureAuth(force = false) {
    if (!force && this.globalData.authPromise) return this.globalData.authPromise
    if (!force && this.globalData.ready && wx.getStorageSync('study-agent-token')) {
      return Promise.resolve({ user: this.globalData.user })
    }

    const login = config.devMode
      ? request.post('/auth/dev-login', { nickname: '微信学习者' })
      : new Promise((resolve, reject) => wx.login({
        success: ({ code }) => request.post('/auth/wechat/login', { code }).then(resolve, reject),
        fail: reject
      }))

    this.globalData.authPromise = login
      .then(data => {
        this.saveAuth(data)
        return data
      })
      .catch(error => {
        this.globalData.ready = false
        throw error
      })
      .finally(() => { this.globalData.authPromise = null })
    return this.globalData.authPromise
  },
  saveAuth(data) {
    wx.setStorageSync('study-agent-token', data.access_token)
    this.globalData.user = data.user
    this.globalData.ready = true
  }
})
