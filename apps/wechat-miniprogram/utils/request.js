const config = require('../config')
const { apiBaseUrl } = config

let devLoginPromise = null

function isAuthPath(path) {
  return path === '/auth/dev-login' || path === '/auth/wechat/login'
}

function saveDevAuth(data) {
  wx.setStorageSync('study-agent-token', data.access_token)
  const app = getApp()
  app.globalData.user = data.user
  app.globalData.ready = true
  return data
}

function ensureDevAuth() {
  if (!config.devMode) return Promise.reject(new Error('登录已过期'))
  if (!devLoginPromise) {
    devLoginPromise = rawRequest('/auth/dev-login', { method: 'POST', data: { nickname: '微信学习者' } })
      .then(saveDevAuth)
      .finally(() => { devLoginPromise = null })
  }
  return devLoginPromise
}

function ensureAppAuth(force = false) {
  const app = getApp()
  if (!app || typeof app.ensureAuth !== 'function') return Promise.reject(new Error('登录尚未初始化'))
  return app.ensureAuth(force)
}

function rawRequest(path, options = {}) {
  const token = wx.getStorageSync('study-agent-token')
  return new Promise((resolve, reject) => wx.request({
    url: `${apiBaseUrl}${path}`,
    method: options.method || 'GET',
    data: options.data,
    header: { 'content-type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.header || {}) },
    success(response) {
      if (response.statusCode === 401) { wx.removeStorageSync('study-agent-token'); const error = new Error('登录已过期'); error.statusCode = 401; reject(error); return }
      if (response.statusCode < 200 || response.statusCode >= 300) { reject(new Error(response.data?.detail || '请求失败')); return }
      resolve(response.data.data)
    },
    fail: reject
  }))
}

function request(path, options = {}) {
  const protectedRequest = !isAuthPath(path)
  const token = wx.getStorageSync('study-agent-token')
  if (protectedRequest && !token) {
    const auth = config.devMode ? ensureDevAuth() : ensureAppAuth()
    return auth.then(() => request(path, { ...options, _authRetried: options._authRetried }))
  }

  return rawRequest(path, options).catch(error => {
    if (error.statusCode === 401 && protectedRequest && !options._authRetried) {
      const auth = config.devMode ? ensureDevAuth() : ensureAppAuth(true)
      return auth.then(() => request(path, { ...options, _authRetried: true }))
    }
    throw error
  })
}

request.get = (path) => request(path)
request.post = (path, data) => request(path, { method: 'POST', data })
request.patch = (path, data) => request(path, { method: 'PATCH', data })
request.del = (path) => request(path, { method: 'DELETE' })
request.upload = (path, filePath, name = 'file') => {
  const upload = () => new Promise((resolve, reject) => wx.uploadFile({
    url: `${apiBaseUrl}${path}`,
    filePath,
    name,
    header: { Authorization: `Bearer ${wx.getStorageSync('study-agent-token')}` },
    success(response) {
      if (response.statusCode === 401) { wx.removeStorageSync('study-agent-token'); const error = new Error('登录已过期'); error.statusCode = 401; reject(error); return }
      if (response.statusCode >= 200 && response.statusCode < 300) {
        try { resolve(JSON.parse(response.data).data) } catch (error) { reject(new Error('上传响应解析失败')) }
        return
      }
      let message = '上传失败'
      try { message = JSON.parse(response.data)?.detail || message } catch (error) {}
      reject(new Error(message))
    },
    fail: reject
  }))

  const ensureToken = wx.getStorageSync('study-agent-token')
    ? Promise.resolve()
    : (config.devMode ? ensureDevAuth() : ensureAppAuth())
  return ensureToken.then(upload).catch(error => {
    if (error.statusCode === 401) return (config.devMode ? ensureDevAuth() : ensureAppAuth(true)).then(upload)
    throw error
  })
}

module.exports = request
