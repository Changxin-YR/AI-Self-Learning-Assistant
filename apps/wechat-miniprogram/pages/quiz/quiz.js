const request = require('../../utils/request')
Page({
  data: { loading: true, quiz: null, answers: {}, submitted: false, submitting: false, result: null, error: '' },
  onLoad(options) { this.load(Number(options.id)) },
  async load(id) {
    try {
      const quiz = await request.get(`/quizzes/${id}`)
      quiz.questions = quiz.questions.map(question => ({
        ...question,
        optionItems: (question.options || []).map((label, index) => ({
          label: question.question_type === 'TRUE_FALSE' ? (String(label) === 'true' ? '正确' : '错误') : label,
          value: question.question_type === 'TRUE_FALSE' ? String(label) : String.fromCharCode(65 + index),
          selected: false
        }))
      }))
      this.setData({ quiz, loading: false, error: '' })
    } catch (error) { this.setData({ loading: false, error: error.message || '加载失败' }) }
  },
  choose(event) {
    if (this.data.submitted || this.data.submitting) return
    const { id, type, value } = event.currentTarget.dataset
    const current = this.data.answers[id] || []
    const next = type === 'MULTIPLE' ? (current.includes(value) ? current.filter(item => item !== value) : [...current, value]) : [value]
    const questions = this.data.quiz.questions.map(question => question.id === Number(id) ? { ...question, optionItems: question.optionItems.map(option => ({ ...option, selected: next.includes(option.value) })) } : question)
    this.setData({ [`answers.${id}`]: next, 'quiz.questions': questions })
  },
  inputShort(event) {
    if (this.data.submitted || this.data.submitting) return
    this.setData({ [`answers.${event.currentTarget.dataset.id}`]: [event.detail.value] })
  },
  async submit() {
    if (!this.data.quiz || this.data.submitted || this.data.submitting) return
    const unanswered = this.data.quiz.questions.filter(question => !(this.data.answers[question.id] || []).some(value => String(value).trim())).length
    const send = async () => {
      if (this.data.submitting || this.data.submitted) return
      this.setData({ submitting: true, error: '' })
      const answers = Object.keys(this.data.answers).map(question_id => ({ question_id: Number(question_id), answer: this.data.answers[question_id] }))
      try {
        const result = await request.post(`/quizzes/${this.data.quiz.id}/submit`, { answers })
        this.setData({ submitted: true, result })
      } catch (error) { this.setData({ error: error.message || '交卷失败' }) }
      finally { this.setData({ submitting: false }) }
    }
    if (!unanswered) return send()
    wx.showModal({ title: '确认交卷', content: `还有 ${unanswered} 题未作答，未答题将按错误计分。`, confirmText: '仍要交卷', success: result => { if (result.confirm) send() } })
  },
  back() { wx.navigateBack() }
})
