const request = require('../../utils/request')
Page({
  data: { kbId: 0, name: '知识库', conversationId: 0, input: '', messages: [], sending: false, scrollTop: 0, error: '', conversations: [], historyVisible: false, citationVisible: false, selectedCitation: null },
  async onLoad(options) {
    const kbId = Number(options.kbId)
    this.setData({ kbId, name: decodeURIComponent(options.name || '知识库') })
    try {
      if (options.conversationId) {
        this.setData({ conversationId: Number(options.conversationId) })
        await this.loadMessages(Number(options.conversationId))
      } else {
        await this.createConversation()
        if (options.action === 'summary') {
          this.setData({ input: '请根据当前知识库资料总结核心内容' })
          await this.send()
        }
      }
      await this.loadConversations()
    } catch (error) { this.setData({ error: error.message || '会话加载失败' }) }
  },
  async createConversation() {
    const conversation = await request.post('/conversations', { knowledge_base_id: this.data.kbId })
    this.setData({ conversationId: conversation.id, messages: [], error: '', scrollTop: 0 })
    return conversation
  },
  async loadConversations() {
    const result = await request.get('/conversations')
    this.setData({ conversations: (result.items || []).filter(item => !this.data.kbId || item.knowledge_base_id === this.data.kbId) })
  },
  async loadMessages(id) {
    const result = await request.get(`/conversations/${id}/messages`)
    this.setData({ messages: result.items || [], scrollTop: 999999, error: '' })
  },
  input(event) { this.setData({ input: event.detail.value }) },
  async send() {
    const text = this.data.input.trim()
    if (!text || !this.data.conversationId || this.data.sending) return
    this.setData({ input: '', sending: true, error: '', messages: [...this.data.messages, { role: 'USER', content: text }], scrollTop: 999999 })
    try {
      const result = await request.post(`/conversations/${this.data.conversationId}/messages`, { content: text })
      this.setData({ messages: [...this.data.messages, { role: 'ASSISTANT', content: result.content, citations: result.citations || [] }], scrollTop: 999999 })
      await this.loadConversations()
    } catch (error) {
      this.setData({ error: error.message || '发送失败', input: text })
      try { await this.loadMessages(this.data.conversationId) } catch (_) {}
    } finally { this.setData({ sending: false }) }
  },
  async retry() {
    if (!this.data.conversationId) return
    try { await this.loadMessages(this.data.conversationId) } catch (error) { this.setData({ error: error.message || '重新加载失败' }) }
  },
  openHistory() {
    this.setData({ historyVisible: true })
    this.loadConversations().catch(error => this.setData({ error: error.message || '会话列表加载失败' }))
  },
  closeHistory() { this.setData({ historyVisible: false }) },
  async newConversation() {
    try {
      this.setData({ historyVisible: false })
      await this.createConversation()
      await this.loadConversations()
    } catch (error) { this.setData({ error: error.message || '新建会话失败' }) }
  },
  async switchConversation(event) {
    const item = event.currentTarget.dataset.item
    if (!item) return
    this.setData({ conversationId: item.id, historyVisible: false, error: '' })
    try { await this.loadMessages(item.id) } catch (error) { this.setData({ error: error.message || '会话加载失败' }) }
  },
  deleteConversation(event) {
    const id = Number(event.currentTarget.dataset.id)
    wx.showModal({
      title: '删除会话',
      content: '删除后该会话记录将不再显示。',
      confirmText: '删除',
      confirmColor: '#d94b5a',
      success: async result => {
        if (!result.confirm) return
        try {
          await request.del(`/conversations/${id}`)
          if (this.data.conversationId === id) await this.createConversation()
          await this.loadConversations()
        } catch (error) { this.setData({ error: error.message || '删除会话失败' }) }
      }
    })
  },
  openCitation(event) { this.setData({ selectedCitation: event.currentTarget.dataset.citation, citationVisible: true }) },
  closeCitation() { this.setData({ citationVisible: false, selectedCitation: null }) }
})
