const request = require('../../utils/request')
const { formatError } = require('../../utils/format')
Page({
  data: { loading: true, error: '', detailError: '', libraries: [], selected: null, documents: [], modal: false, name: '', uploading: false },
  onShow() {
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
  async load() {
    this.setData({ loading: true, error: '' })
    try {
      const result = await request.get('/knowledge-bases')
      const libraries = result.items || []
      let selected = this.data.selected
      if (selected) selected = libraries.find(item => item.id === selected.id) || null
      this.setData({ libraries, selected, loading: false })
      if (selected) await this.loadDocuments(selected.id, this.pollGeneration)
    } catch (error) { this.setData({ loading: false, error: formatError(error) }) }
  },
  openCreate() { this.setData({ modal: true, name: '' }) },
  closeCreate() { this.setData({ modal: false }) },
  inputName(event) { this.setData({ name: event.detail.value }) },
  async create() {
    if (!this.data.name.trim()) return
    try {
      const kb = await request.post('/knowledge-bases', { name: this.data.name.trim(), category: '课程', icon: '📘' })
      this.setData({ libraries: [kb, ...this.data.libraries], modal: false })
      await this.select({ currentTarget: { dataset: { kb } } })
    } catch (error) { this.setData({ error: formatError(error) }) }
  },
  async select(event) {
    const kb = event.currentTarget.dataset.kb || event.currentTarget.dataset.item
    if (!kb) return
    this.stopPolling()
    const generation = this.pollGeneration
    this.setData({ selected: kb, documents: [], detailError: '' })
    await this.loadDocuments(kb.id, generation)
    if (this.data.selected && this.data.selected.id === kb.id && generation === this.pollGeneration) this.startPolling(kb.id)
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
  retry() { this.load() },
  retryDocuments() { if (this.data.selected) this.loadDocuments(this.data.selected.id, this.pollGeneration) }
})
