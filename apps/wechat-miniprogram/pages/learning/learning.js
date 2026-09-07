const request = require('../../utils/request')
const { formatError } = require('../../utils/format')
Page({
  data: { loading: true, error: '', libraries: [], plans: [], plan: null, tasks: [], modal: false, selectedKb: null },
  onShow() { this.load() },
  async load() { this.setData({ loading: true, error: '' }); try { const [libraries, plans, tasks] = await Promise.all([request.get('/knowledge-bases'), request.get('/study-plans'), request.get('/tasks/today')]); const planItems = plans.items || []; this.setData({ libraries: libraries.items || [], plans: planItems, plan: planItems[0] || null, tasks: tasks.items || [], loading: false }) } catch (error) { this.setData({ loading: false, error: formatError(error) }) } },
  openPlan() { this.setData({ modal: true, selectedKb: this.data.libraries[0] || null }) },
  closePlan() { this.setData({ modal: false }) },
  chooseKb(event) { this.setData({ selectedKb: this.data.libraries[event.detail.value] }) },
  async createPlan() { if (!this.data.selectedKb) return; try { const plan = await request.post('/study-plans', { name: '14 天学习冲刺', knowledge_base_id: this.data.selectedKb.id, goal: '掌握核心知识并完成测验', target_date: new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10), daily_minutes: 30, weekly_days: 5 }); await request.post(`/study-plans/${plan.id}/activate`); this.setData({ modal: false, plan }); this.load() } catch (error) { this.setData({ error: formatError(error) }) } },
  async complete(event) { const id = event.currentTarget.dataset.id; try { await request.post(`/tasks/${id}/complete`); this.load() } catch (error) { this.setData({ error: formatError(error) }) } },
  async generateQuiz() { const kb = this.data.selectedKb || this.data.libraries[0]; if (!kb) return; try { const quiz = await request.post('/quizzes', { knowledge_base_id: kb.id, question_count: 5, question_types: ['SINGLE', 'MULTIPLE', 'TRUE_FALSE'] }); wx.navigateTo({ url: `/pages/quiz/quiz?id=${quiz.id}` }) } catch (error) { this.setData({ error: formatError(error) }) } },
  retry() { this.load() }
})
