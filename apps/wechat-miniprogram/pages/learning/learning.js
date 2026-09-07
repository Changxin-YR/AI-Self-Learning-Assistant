const request = require('../../utils/request')
const { formatError } = require('../../utils/format')
Page({
  data: { loading: true, error: '', libraries: [], plans: [], plan: null, tasks: [], modal: false, selectedKb: null, draft: null, form: { name: '', goal: '', target_date: '', daily_minutes: 30, weekly_days: 5 } },
  onShow() { this.load() },
  async load() { this.setData({ loading: true, error: '' }); try { const [libraries, plans, tasks] = await Promise.all([request.get('/knowledge-bases'), request.get('/study-plans'), request.get('/tasks/today')]); const planItems = plans.items || []; this.setData({ libraries: libraries.items || [], plans: planItems, plan: planItems[0] || null, tasks: tasks.items || [], loading: false }) } catch (error) { this.setData({ loading: false, error: formatError(error) }) } },
  openPlan() { const target = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10); this.setData({ modal: true, draft: null, selectedKb: this.data.libraries[0] || null, form: { name: '我的学习计划', goal: '', target_date: target, daily_minutes: 30, weekly_days: 5 } }) },
  closePlan() { this.setData({ modal: false }) },
  chooseKb(event) { this.setData({ selectedKb: this.data.libraries[event.detail.value] }) },
  input(event) { this.setData({ [`form.${event.currentTarget.dataset.field}`]: event.detail.value }) },
  async createPlan() { if (!this.data.selectedKb || !this.data.form.name.trim()) return; try { const plan = await request.post('/study-plans', { ...this.data.form, name: this.data.form.name.trim(), knowledge_base_id: this.data.selectedKb.id, daily_minutes: Number(this.data.form.daily_minutes), weekly_days: Number(this.data.form.weekly_days) }); this.setData({ draft: plan }); } catch (error) { this.setData({ error: formatError(error) }) } },
  async confirmPlan() { if (!this.data.draft) return; try { await request.post(`/study-plans/${this.data.draft.id}/activate`); this.setData({ modal: false, plan: { ...this.data.draft, status: 'ACTIVE' } }); this.load() } catch (error) { this.setData({ error: formatError(error) }) } },
  async complete(event) { const id = event.currentTarget.dataset.id; try { await request.post(`/tasks/${id}/complete`); this.load() } catch (error) { this.setData({ error: formatError(error) }) } },
  async generateQuiz() { const kb = this.data.selectedKb || this.data.libraries[0]; if (!kb) return; try { const quiz = await request.post('/quizzes', { knowledge_base_id: kb.id, question_count: 5, question_types: ['SINGLE', 'MULTIPLE', 'TRUE_FALSE'] }); wx.navigateTo({ url: `/pages/quiz/quiz?id=${quiz.id}` }) } catch (error) { this.setData({ error: formatError(error) }) } },
  retry() { this.load() }
})
