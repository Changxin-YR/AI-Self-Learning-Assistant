const request = require('../../utils/request')
const { formatError } = require('../../utils/format')
Page({
  data: { loading: true, error: '', dashboard: {}, libraries: [], progress: 0, nickname: '学习者' },
  onShow() { this.load() },
  async load() {
    this.setData({ loading: true, error: '' })
    try {
      const [dashboard, libraries] = await Promise.all([request.get('/dashboard'), request.get('/knowledge-bases')])
      const nickname = getApp().globalData.user?.nickname || '学习者'
      this.setData({ dashboard, libraries: libraries.items || [], progress: dashboard.task_total ? Math.round(dashboard.task_done / dashboard.task_total * 100) : 0, nickname, loading: false })
    } catch (error) { this.setData({ loading: false, error: formatError(error) }) }
  },
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
      const quiz = await request.post('/quizzes', { knowledge_base_id: kb.id, question_count: 5, question_types: ['SINGLE', 'MULTIPLE', 'TRUE_FALSE'] })
      wx.navigateTo({ url: `/pages/quiz/quiz?id=${quiz.id}` })
    } catch (error) { this.setData({ error: formatError(error) }) }
  }
})
