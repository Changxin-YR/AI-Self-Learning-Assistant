const request = require('../../utils/request')
const { formatError } = require('../../utils/format')
Page({
  data: { loading: true, error: '', dashboard: {}, libraries: [], progress: 0 },
  onShow() { this.load() },
  async load() {
    this.setData({ loading: true, error: '' })
    try {
      const [dashboard, libraries] = await Promise.all([request.get('/dashboard'), request.get('/knowledge-bases')])
      this.setData({ dashboard, libraries: libraries.items || [], progress: dashboard.task_total ? Math.round(dashboard.task_done / dashboard.task_total * 100) : 0, loading: false })
    } catch (error) { this.setData({ loading: false, error: formatError(error) }) }
  },
  goLibrary() { wx.switchTab({ url: '/pages/library/library' }) },
  goLearning() { wx.switchTab({ url: '/pages/learning/learning' }) },
  openChat() { const kb = this.data.libraries[0]; if (!kb) { this.goLibrary(); return } wx.navigateTo({ url: `/pages/chat/chat?kbId=${kb.id}&name=${encodeURIComponent(kb.name)}` }) },
  createPlan() { this.goLearning() }
})
