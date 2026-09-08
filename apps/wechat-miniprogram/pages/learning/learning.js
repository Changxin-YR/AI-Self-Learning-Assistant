const request = require('../../utils/request')
const { formatError } = require('../../utils/format')
Page({
  data: { loading: true, error: '', libraries: [], plans: [], plan: null, tasks: [], dashboard: {}, masteryPreview: [], trend: [], weakPointsText: '', daysRemaining: 0, modal: false, selectedKb: null, draft: null, creatingPlan: false, activatingPlan: false, generatingQuiz: false, form: { name: '', goal: '', target_date: '', daily_minutes: 30, weekly_days: 5 } },
  async onShow() {
    if (getApp().globalData.signedOut) { wx.switchTab({ url: '/pages/home/home' }); return }
    await this.load()
    if (wx.getStorageSync('study-agent-plan-kb') && this.data.libraries.length) this.openPlan()
  },
  buildAnalytics(dashboard, plan) {
    const masteryPreview = [...(dashboard.mastery || [])].sort((a, b) => a.score - b.score).slice(0, 5)
    const maxMinutes = Math.max(1, ...(dashboard.trend || []).map(item => Number(item.minutes || 0)))
    const trend = (dashboard.trend || []).map(item => ({ ...item, percent: Math.round(Number(item.minutes || 0) / maxMinutes * 100), shortDate: String(item.date || '').slice(5) }))
    let daysRemaining = 0
    if (plan?.target_date) {
      const target = new Date(`${plan.target_date}T23:59:59`)
      daysRemaining = Math.max(0, Math.ceil((target.getTime() - Date.now()) / 86400000))
    }
    return { masteryPreview, trend, weakPointsText: (dashboard.weak_points || []).slice(0, 5).join('、'), daysRemaining }
  },
  async load() {
    this.setData({ loading: true, error: '' })
    try {
      const [libraries, plans, tasks, dashboard] = await Promise.all([request.get('/knowledge-bases'), request.get('/study-plans'), request.get('/tasks/today'), request.get('/dashboard')])
      const libraryItems = libraries.items || []
      const planItems = plans.items || []
      const activePlan = planItems.find(item => item.status === 'ACTIVE') || planItems[0] || null
      this.setData({ libraries: libraryItems, plans: planItems, plan: activePlan, tasks: tasks.items || [], dashboard, ...this.buildAnalytics(dashboard, activePlan), loading: false })
    } catch (error) { this.setData({ loading: false, error: formatError(error) }) }
  },
  openPlan() {
    const target = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10)
    const preferredKbId = Number(wx.getStorageSync('study-agent-plan-kb') || 0)
    if (preferredKbId) wx.removeStorageSync('study-agent-plan-kb')
    const selectedKb = this.data.libraries.find(item => item.id === preferredKbId) || this.data.libraries[0] || null
    this.setData({ modal: true, draft: null, selectedKb, form: { name: '我的学习计划', goal: '', target_date: target, daily_minutes: 30, weekly_days: 5 } })
  },
  closePlan() { this.setData({ modal: false, draft: null, selectedKb: null }) },
  chooseKb(event) { this.setData({ selectedKb: this.data.libraries[event.detail.value] }) },
  chooseDate(event) { this.setData({ 'form.target_date': event.detail.value }) },
  input(event) { this.setData({ [`form.${event.currentTarget.dataset.field}`]: event.detail.value }) },
  async createPlan() {
    if (!this.data.selectedKb || !this.data.form.name.trim() || this.data.creatingPlan) return
    this.setData({ creatingPlan: true, error: '' })
    try {
      const plan = await request.post('/study-plans', { ...this.data.form, name: this.data.form.name.trim(), knowledge_base_id: this.data.selectedKb.id, daily_minutes: Number(this.data.form.daily_minutes), weekly_days: Number(this.data.form.weekly_days) })
      this.setData({ draft: plan })
    } catch (error) { this.setData({ error: formatError(error) }) }
    finally { this.setData({ creatingPlan: false }) }
  },
  async confirmPlan() {
    if (!this.data.draft || this.data.activatingPlan) return
    this.setData({ activatingPlan: true, error: '' })
    try {
      await request.post(`/study-plans/${this.data.draft.id}/activate`)
      this.setData({ modal: false, draft: null, selectedKb: null })
      await this.load()
    } catch (error) { this.setData({ error: formatError(error) }) }
    finally { this.setData({ activatingPlan: false }) }
  },
  async complete(event) {
    const id = Number(event.currentTarget.dataset.id)
    const task = this.data.tasks.find(item => item.id === id)
    if (!task || task.status === 'DONE') return
    try { await request.post(`/tasks/${id}/complete`); await this.load() } catch (error) { this.setData({ error: formatError(error) }) }
  },
  async generateQuiz() {
    if (this.data.generatingQuiz) return
    const planKbId = this.data.plan?.knowledge_base_id
    const kb = this.data.libraries.find(item => item.id === planKbId) || this.data.libraries[0]
    if (!kb) { wx.showToast({ title: '请先创建知识库', icon: 'none' }); return }
    this.setData({ generatingQuiz: true, error: '' })
    try {
      const quiz = await request.post('/quizzes', { knowledge_base_id: kb.id, question_count: 5, question_types: ['SINGLE', 'MULTIPLE', 'TRUE_FALSE', 'SHORT'] })
      wx.navigateTo({ url: `/pages/quiz/quiz?id=${quiz.id}` })
    } catch (error) { this.setData({ error: formatError(error) }) }
    finally { this.setData({ generatingQuiz: false }) }
  },
  retry() { this.load() }
})
