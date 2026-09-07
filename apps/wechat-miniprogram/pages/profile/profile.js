const request = require('../../utils/request')
Page({
  data: { dashboard: {}, nickname: '学习者', avatar: '学', panel: '' },
  onShow() { this.load() },
  async load() { try { const dashboard = await request.get('/dashboard'); const app = getApp(); const nickname = app.globalData.user?.nickname || '学习者'; this.setData({ dashboard, nickname, avatar: nickname[0] || '学' }) } catch (error) { wx.showToast({ title: error.message || '加载失败', icon: 'none' }) } },
  openPanel(event) { this.setData({ panel: event.currentTarget.dataset.panel }) },
  closePanel() { this.setData({ panel: '' }) },
  async deleteAccount() { wx.showModal({ title: '删除账号数据', content: '删除后将停止访问账号，资料与学习记录进入清理流程。', confirmText: '确认删除', success: async result => { if (!result.confirm) return; try { await request.del('/auth/account'); wx.removeStorageSync('study-agent-token'); wx.reLaunch({ url: '/pages/home/home' }) } catch (error) { wx.showToast({ title: error.message || '删除失败', icon: 'none' }) } } }) },
  async logout() { wx.removeStorageSync('study-agent-token'); const app = getApp(); app.globalData.user = null; app.globalData.ready = false; try { await app.ensureAuth(true); wx.reLaunch({ url: '/pages/home/home' }) } catch (error) { wx.showToast({ title: error.message || '重新登录失败', icon: 'none' }) } }
})
