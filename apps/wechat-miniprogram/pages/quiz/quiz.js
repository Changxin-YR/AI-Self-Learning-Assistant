const request = require('../../utils/request')
Page({
  data: { loading: true, quiz: null, answers: {}, submitted: false, result: null },
  onLoad(options) { this.load(Number(options.id)) },
  async load(id) { try { const quiz = await request.get(`/quizzes/${id}`); quiz.questions = quiz.questions.map(question => ({ ...question, optionItems: question.options.map((label, index) => ({ label, value: question.question_type === 'TRUE_FALSE' ? label : String.fromCharCode(65 + index), selected: false })) })); this.setData({ quiz, loading: false }) } catch (error) { this.setData({ loading: false }); wx.showToast({ title: error.message || '加载失败', icon: 'none' }) } },
  choose(event) { const { id, type, value } = event.currentTarget.dataset; const current = this.data.answers[id] || []; const next = type === 'MULTIPLE' ? (current.includes(value) ? current.filter(item => item !== value) : [...current, value]) : [value]; const questions = this.data.quiz.questions.map(question => question.id === Number(id) ? { ...question, optionItems: question.optionItems.map(option => ({ ...option, selected: next.includes(option.value) })) } : question); this.setData({ [`answers.${id}`]: next, 'quiz.questions': questions }) },
  async submit() { if (!this.data.quiz || this.data.submitted) return; const answers = Object.keys(this.data.answers).map(question_id => ({ question_id: Number(question_id), answer: this.data.answers[question_id] })); try { const result = await request.post(`/quizzes/${this.data.quiz.id}/submit`, { answers }); this.setData({ submitted: true, result }) } catch (error) { wx.showToast({ title: error.message || '交卷失败', icon: 'none' }) } }
  ,back() { wx.navigateBack() }
})
