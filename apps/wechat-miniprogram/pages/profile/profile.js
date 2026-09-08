const request = require('../../utils/request')
Page({
  data: { dashboard: {}, nickname: '学习者', avatar: '学', panel: '' },
  onShow() { this.load() },
  async load() {
    if (getApp().globalData.signedOut) return
    try {
      const dashboard = await request.get('/dashboard')
      const app = getApp()
      const nickname = app.globalData.user?.nickname || '学习者'
      this.setData({ dashboard, nickname, avatar: nickname[0] || '学' })
    } catch (error) { wx.showToast({ title: error.message || '加载失败', icon: 'none' }) }
  },
  openPanel(event) { this.setData({ panel: event.currentTarget.dataset.panel }) },
  closePanel() { this.setData({ panel: '' }) },
  deleteAccount() {
    wx.showModal({
      title: '删除账号数据',
      content: '删除后将停止访问账号，资料与学习记录进入清理流程。之后若主动重新登录，将按新用户重新开始。',
      confirmText: '确认删除',
      confirmColor: '#d94b5a',
      success: async result => {
        if (!result.confirm) return
        try {
          await request.del('/auth/account')
          getApp().clearAuth(true)
          wx.showToast({ title: '账号已删除', icon: 'success' })
          setTimeout(() => wx.reLaunch({ url: '/pages/home/home' }), 500)
        } catch (error) { wx.showToast({ title: error.message || '删除失败', icon: 'none' }) }
      }
    })
  },
  logout() {
    wx.showModal({
      title: '退出登录',
      content: '退出后不会自动重新登录，需在首页主动点击“重新登录”。',
      confirmText: '退出',
      success: result => {
        if (!result.confirm) return
        getApp().clearAuth(true)
        wx.reLaunch({ url: '/pages/home/home' })
      }
    })
  }
})
