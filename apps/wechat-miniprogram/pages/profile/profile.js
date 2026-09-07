const request = require('../../utils/request')
Page({
  data: { dashboard: {}, nickname: '学习者', avatar: '学' },
  onShow() { this.load() },
  async load() { try { const dashboard = await request.get('/dashboard'); const app = getApp(); const nickname = app.globalData.user?.nickname || '学习者'; this.setData({ dashboard, nickname, avatar: nickname[0] || '学' }) } catch (error) { wx.showToast({ title: error.message || '加载失败', icon: 'none' }) } },
  logout() { wx.removeStorageSync('study-agent-token'); wx.reLaunch({ url: '/pages/home/home' }) }
})
