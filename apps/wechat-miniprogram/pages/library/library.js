const request = require('../../utils/request')
const { formatError } = require('../../utils/format')
const EMPTY_FORM = { name: '', description: '', category: '课程', icon: '📘' }
Page({
  data: { loading: true, error: '', detailError: '', libraries: [], visibleLibraries: [], query: '', selected: null, documents: [], mastery: [], conversations: [], detailTab: 'documents', detailLoading: false, modal: false, editing: false, form: { ...EMPTY_FORM }, uploading: false, categories: ['课程', '考试', '技术', '其他'] },
  onShow() {
    if (getApp().globalData.signedOut) { this.stopPolling(); wx.switchTab({ url: '/pages/home/home' }); return }
    this.load().then(() => {
      if (this.data.selected) this.startPolling(this.data.selected.id)
    })
  },
  onHide() { this.stopPolling() },
  onUnload() { this.stopPolling() },
  stopPolling() {
    this.pollGeneration = (this.pollGeneration || 0) + 1
    if (this.pollTimer) clearInterval(this.pollTimer)
    this.pollTimer = null
  },
  startPolling(kbId) {
    this.stopPolling()
    const generation = this.pollGeneration
    this.pollTimer = setInterval(() => {
      if (!this.data.selected || this.data.selected.id !== kbId || generation !== this.pollGeneration || this.pollInFlight) return
      this.pollInFlight = true
      this.loadDocuments(kbId, generation).finally(() => { this.pollInFlight = false })
    }, 5000)
  },
  applyFilter(libraries = this.data.libraries, query = this.data.query) {
    const keyword = String(query || '').trim().toLowerCase()
    const visibleLibraries = keyword ? libraries.filter(item => `${item.name} ${item.description || ''} ${item.category || ''}`.toLowerCase().includes(keyword)) : libraries
    this.setData({ visibleLibraries })
  },
  inputSearch(event) { const query = event.detail.value; this.setData({ query }); this.applyFilter(this.data.libraries, query) },
  async load() {
    this.setData({ loading: true, error: '' })
    try {
      const result = await request.get('/knowledge-bases')
      const libraries = result.items || []
      let selected = this.data.selected
      if (selected) selected = libraries.find(item => item.id === selected.id) || null
      this.setData({ libraries, selected, loading: false })
      this.applyFilter(libraries, this.data.query)
      if (selected) await this.refreshCurrentTab()
    } catch (error) { this.setData({ loading: false, error: formatError(error) }) }
  },
  openCreate() { this.setData({ modal: true, editing: false, form: { ...EMPTY_FORM } }) },
  openEdit() {
    const kb = this.data.selected
    if (!kb) return
    this.setData({ modal: true, editing: true, form: { name: kb.name || '', description: kb.description || '', category: kb.category || '其他', icon: kb.icon || '📚' } })
  },
  closeCreate() { this.setData({ modal: false, editing: false }) },
  inputForm(event) { this.setData({ [`form.${event.currentTarget.dataset.field}`]: event.detail.value }) },
  chooseCategory(event) { this.setData({ 'form.category': this.data.categories[Number(event.detail.value)] || '其他' }) },
  async saveKnowledgeBase() {
    const name = this.data.form.name.trim()
    if (!name) { wx.showToast({ title: '请输入知识库名称', icon: 'none' }); return }
    const payload = { name, description: this.data.form.description.trim(), category: this.data.form.category || '其他', icon: this.data.form.icon.trim() || '📚', status: this.data.editing ? (this.data.selected?.status || 'ACTIVE') : 'ACTIVE' }
    try {
      if (this.data.editing && this.data.selected) {
        const kb = await request.patch(`/knowledge-bases/${this.data.selected.id}`, payload)
        this.setData({ selected: kb, modal: false, editing: false })
        await this.load()
      } else {
        const kb = await request.post('/knowledge-bases', payload)
        this.setData({ modal: false })
        await this.load()
        await this.select({ currentTarget: { dataset: { kb } } })
      }
    } catch (error) { this.setData({ error: formatError(error) }) }
  },
  async toggleArchive() {
    const kb = this.data.selected
    if (!kb) return
    const status = kb.status === 'ARCHIVED' ? 'ACTIVE' : 'ARCHIVED'
    try {
      const updated = await request.patch(`/knowledge-bases/${kb.id}`, { name: kb.name, description: kb.description || '', category: kb.category || '其他', icon: kb.icon || '📚', status })
      this.setData({ selected: updated })
      await this.load()
    } catch (error) { this.setData({ detailError: formatError(error) }) }
  },
  deleteKnowledgeBase() {
    const kb = this.data.selected
    if (!kb) return
    wx.showModal({
      title: '删除知识库',
      content: `确定删除“${kb.name}”吗？其中的资料与检索索引也会进入清理流程。`,
      confirmText: '删除',
      confirmColor: '#d94b5a',
      success: async result => {
        if (!result.confirm) return
        try {
          this.stopPolling()
          await request.del(`/knowledge-bases/${kb.id}`)
          this.setData({ selected: null, documents: [], mastery: [], conversations: [], detailError: '' })
          await this.load()
        } catch (error) { this.setData({ detailError: formatError(error) }) }
      }
    })
  },
  async select(event) {
    const kb = event.currentTarget.dataset.kb || event.currentTarget.dataset.item
    if (!kb) return
    this.stopPolling()
    const generation = this.pollGeneration
    this.setData({ selected: kb, documents: [], mastery: [], conversations: [], detailTab: 'documents', detailError: '' })
    await this.loadDocuments(kb.id, generation)
    if (this.data.selected && this.data.selected.id === kb.id && generation === this.pollGeneration) this.startPolling(kb.id)
  },
  async switchDetailTab(event) {
    const tab = event.currentTarget.dataset.tab
    if (!['documents', 'mastery', 'history'].includes(tab)) return
    this.setData({ detailTab: tab, detailError: '' })
    await this.refreshCurrentTab()
  },
  async refreshCurrentTab() {
    const kb = this.data.selected
    if (!kb) return
    if (this.data.detailTab === 'mastery') return this.loadMastery(kb.id)
    if (this.data.detailTab === 'history') return this.loadHistory(kb.id)
    return this.loadDocuments(kb.id, this.pollGeneration)
  },
  async loadMastery(kbId) {
    this.setData({ detailLoading: true })
    try {
      const result = await request.get(`/knowledge-bases/${kbId}/mastery`)
      if (this.data.selected?.id === kbId) this.setData({ mastery: result.items || [], detailError: '' })
    } catch (error) {
      if (this.data.selected?.id === kbId) this.setData({ detailError: formatError(error) })
    } finally { this.setData({ detailLoading: false }) }
  },
  async loadHistory(kbId) {
    this.setData({ detailLoading: true })
    try {
      const result = await request.get('/conversations')
      if (this.data.selected?.id === kbId) this.setData({ conversations: (result.items || []).filter(item => item.knowledge_base_id === kbId), detailError: '' })
    } catch (error) {
      if (this.data.selected?.id === kbId) this.setData({ detailError: formatError(error) })
    } finally { this.setData({ detailLoading: false }) }
  },
  openConversation(event) {
    const item = event.currentTarget.dataset.item
    if (!item || !this.data.selected) return
    wx.navigateTo({ url: `/pages/chat/chat?kbId=${this.data.selected.id}&name=${encodeURIComponent(this.data.selected.name)}&conversationId=${item.id}` })
  },
  async loadDocuments(kbId, generation = this.pollGeneration) {
    try {
      const result = await request.get(`/knowledge-bases/${kbId}/documents`)
      if (!this.data.selected || this.data.selected.id !== kbId || generation !== this.pollGeneration) return
      this.setData({ documents: result.items || [], detailError: '' })
    } catch (error) {
      if (this.data.selected && this.data.selected.id === kbId && generation === this.pollGeneration) this.setData({ detailError: formatError(error) })
    }
  },
  upload() {
    if (!this.data.selected || this.data.uploading) return
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['pdf', 'docx', 'pptx', 'txt', 'md'],
      success: ({ tempFiles }) => {
        const file = tempFiles[0]
        if (!file) return
        const kbId = this.data.selected.id
        this.setData({ uploading: true, detailError: '' })
        request.upload(`/knowledge-bases/${kbId}/documents`, file.path)
          .then(doc => {
            if (this.data.selected?.id === kbId) this.setData({ documents: [doc, ...this.data.documents] })
            return this.loadDocuments(kbId, this.pollGeneration)
          })
          .catch(error => this.setData({ detailError: formatError(error) }))
          .finally(() => this.setData({ uploading: false }))
      },
      fail: error => {
        if (String(error?.errMsg || '').includes('cancel')) return
        this.setData({ detailError: formatError(error) })
      }
    })
  },
  async retryDocument(event) {
    const id = event.currentTarget.dataset.id
    const document = this.data.documents.find(item => item.id === id)
    const action = document?.status === 'READY' ? 'rebuild' : 'retry'
    try {
      this.setData({ detailError: '' })
      await request.post(`/documents/${id}/${action}`)
      await this.loadDocuments(this.data.selected.id, this.pollGeneration)
    } catch (error) { this.setData({ detailError: formatError(error) }) }
  },
  deleteDocument(event) {
    const id = event.currentTarget.dataset.id
    const document = this.data.documents.find(item => item.id === id)
    wx.showModal({
      title: '删除资料',
      content: `确定删除“${document?.filename || '该资料'}”吗？删除后将同步清理检索索引。`,
      confirmText: '删除',
      confirmColor: '#d94b5a',
      success: async result => {
        if (!result.confirm) return
        try {
          await request.del(`/documents/${id}`)
          this.setData({ documents: this.data.documents.filter(item => item.id !== id), detailError: '' })
          await this.loadDocuments(this.data.selected.id, this.pollGeneration)
        } catch (error) { this.setData({ detailError: formatError(error) }) }
      }
    })
  },
  chat() { if (this.data.selected) wx.navigateTo({ url: `/pages/chat/chat?kbId=${this.data.selected.id}&name=${encodeURIComponent(this.data.selected.name)}` }) },
  createPlan() { if (this.data.selected) { wx.setStorageSync('study-agent-plan-kb', this.data.selected.id); wx.switchTab({ url: '/pages/learning/learning' }) } },
  async generateQuiz() {
    if (!this.data.selected) return
    try {
      const quiz = await request.post('/quizzes', { knowledge_base_id: this.data.selected.id, question_count: 5, question_types: ['SINGLE', 'MULTIPLE', 'TRUE_FALSE', 'SHORT'] })
      wx.navigateTo({ url: `/pages/quiz/quiz?id=${quiz.id}` })
    } catch (error) { this.setData({ detailError: formatError(error) }) }
  },
  retry() { this.load() },
  retryDocuments() { this.refreshCurrentTab() }
})
