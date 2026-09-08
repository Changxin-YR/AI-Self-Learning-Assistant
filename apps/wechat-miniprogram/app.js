const config = require('./config')
const request = require('./utils/request')

const MANUAL_SIGN_OUT_KEY = 'study-agent-manual-signed-out'

App({
  globalData: { user: null, ready: false, authPromise: null, signedOut: false },
  onLaunch() {
    this.globalData.signedOut = Boolean(wx.getStorageSync(MANUAL_SIGN_OUT_KEY))
    if (this.globalData.signedOut) return
    this.ensureAuth().catch(() => wx.showToast({ title: '登录失败，请检查 API', icon: 'none' }))
  },
  ensureAuth(force = false) {
    if (this.globalData.signedOut && !force) {
      const error = new Error('已退出登录，请重新登录')
      error.code = 'MANUAL_SIGNED_OUT'
      return Promise.reject(error)
    }
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
    wx.removeStorageSync(MANUAL_SIGN_OUT_KEY)
    this.globalData.user = data.user
    this.globalData.ready = true
    this.globalData.signedOut = false
  },
  clearAuth(manual = true) {
    wx.removeStorageSync('study-agent-token')
    this.globalData.user = null
    this.globalData.ready = false
    this.globalData.authPromise = null
    this.globalData.signedOut = manual
    if (manual) wx.setStorageSync(MANUAL_SIGN_OUT_KEY, true)
    else wx.removeStorageSync(MANUAL_SIGN_OUT_KEY)
  },
  resumeAuth() {
    this.clearAuth(false)
    return this.ensureAuth(true)
  }
})
