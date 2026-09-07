const config = require('../config')
const { apiBaseUrl } = config

let devLoginPromise = null

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
  if (!wx.getStorageSync('study-agent-token') && config.devMode && path !== '/auth/dev-login' && path !== '/auth/wechat/login') {
    return ensureDevAuth().then(() => request(path, options))
  }
  return rawRequest(path, options).catch(error => {
    if (error.statusCode === 401 && config.devMode && path !== '/auth/dev-login' && path !== '/auth/wechat/login') {
      return ensureDevAuth().then(() => request(path, options))
    }
    throw error
  })
}

request.get = (path) => request(path)
request.post = (path, data) => request(path, { method: 'POST', data })
request.patch = (path, data) => request(path, { method: 'PATCH', data })
request.del = (path) => request(path, { method: 'DELETE' })
request.upload = (path, filePath, name = 'file') => {
  const upload = () => new Promise((resolve, reject) => wx.uploadFile({ url: `${apiBaseUrl}${path}`, filePath, name, header: { Authorization: `Bearer ${wx.getStorageSync('study-agent-token')}` }, success(response) { if (response.statusCode >= 200 && response.statusCode < 300) resolve(JSON.parse(response.data).data); else reject(new Error('上传失败')) }, fail: reject }))
  return wx.getStorageSync('study-agent-token') || !config.devMode ? upload() : ensureDevAuth().then(upload)
}

module.exports = request
