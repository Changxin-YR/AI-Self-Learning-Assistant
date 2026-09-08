const request = require('../../utils/request')
const { formatError } = require('../../utils/format')
Page({
  data: { loading: true, error: '', dashboard: {}, libraries: [], recentLibraries: [], progress: 0, nickname: '学习者', signedOut: false },
  onShow() {
    const signedOut = Boolean(getApp().globalData.signedOut)
    this.setData({ signedOut })
    if (signedOut) {
      this.setData({ loading: false, error: '', dashboard: {}, libraries: [], recentLibraries: [], progress: 0, nickname: '学习者' })
      return
    }
    this.load()
  },
  async login() {
    this.setData({ loading: true, error: '' })
    try {
      await getApp().resumeAuth()
      this.setData({ signedOut: false })
      await this.load()
    } catch (error) {
      this.setData({ loading: false, error: formatError(error) })
    }
  },
  async load() {
    this.setData({ loading: true, error: '' })
    try {
      const [dashboard, libraries] = await Promise.all([request.get('/dashboard'), request.get('/knowledge-bases')])
      const items = libraries.items || []
      const nickname = getApp().globalData.user?.nickname || '学习者'
      this.setData({
        dashboard,
        libraries: items,
        recentLibraries: items.slice(0, 3),
        progress: dashboard.task_total ? Math.round(dashboard.task_done / dashboard.task_total * 100) : 0,
        nickname,
        loading: false,
        signedOut: false
      })
    } catch (error) {
      if (error.code === 'MANUAL_SIGNED_OUT') this.setData({ signedOut: true, loading: false, error: '' })
      else this.setData({ loading: false, error: formatError(error) })
    }
  },
  retry() { this.load() },
  goLibrary() { wx.switchTab({ url: '/pages/library/library' }) },
  goLearning() { wx.switchTab({ url: '/pages/learning/learning' }) },
  openChat(event) {
    const kb = event?.currentTarget?.dataset?.kb || this.data.libraries[0]
    if (!kb) { this.goLibrary(); return }
    const action = event?.currentTarget?.dataset?.action || ''
    wx.navigateTo({ url: `/pages/chat/chat?kbId=${kb.id}&name=${encodeURIComponent(kb.name)}&action=${action}` })
  },
  createPlan() { this.goLearning() },
  async generateQuiz() {
    const kb = this.data.libraries[0]
    if (!kb) { this.goLibrary(); return }
    try {
      const quiz = await request.post('/quizzes', { knowledge_base_id: kb.id, question_count: 5, question_types: ['SINGLE', 'MULTIPLE', 'TRUE_FALSE', 'SHORT'] })
      wx.navigateTo({ url: `/pages/quiz/quiz?id=${quiz.id}` })
    } catch (error) { this.setData({ error: formatError(error) }) }
  }
})
