const request = require('../../utils/request')
Page({
  data: { kbId: 0, name: '知识库', conversationId: 0, input: '', messages: [], sending: false, scrollTop: 0, error: '', conversations: [], historyVisible: false },
  async onLoad(options) {
    const kbId = Number(options.kbId)
    this.setData({ kbId, name: decodeURIComponent(options.name || '知识库') })
    try {
      if (options.conversationId) {
        this.setData({ conversationId: Number(options.conversationId) })
        await this.loadMessages(Number(options.conversationId))
      } else {
        const conversation = await request.post('/conversations', { knowledge_base_id: kbId })
        this.setData({ conversationId: conversation.id })
        if (options.action === 'summary') {
          this.setData({ input: '请根据当前知识库资料总结核心内容' })
          this.send()
        }
      }
      await this.loadConversations()
    } catch (error) { this.setData({ error: error.message || '会话加载失败' }) }
  },
  async loadConversations() {
    const result = await request.get('/conversations')
    this.setData({ conversations: (result.items || []).filter(item => !this.data.kbId || item.knowledge_base_id === this.data.kbId) })
  },
  async loadMessages(id) { const result = await request.get(`/conversations/${id}/messages`); this.setData({ messages: result.items || [], scrollTop: 999999 }) },
  input(event) { this.setData({ input: event.detail.value }) },
  async send() {
    const text = this.data.input.trim()
    if (!text || !this.data.conversationId || this.data.sending) return
    this.setData({ input: '', sending: true, error: '', messages: [...this.data.messages, { role: 'USER', content: text }], scrollTop: 999999 })
    try {
      const result = await request.post(`/conversations/${this.data.conversationId}/messages`, { content: text })
      this.setData({ messages: [...this.data.messages, { role: 'ASSISTANT', content: result.content, citations: result.citations || [] }], scrollTop: 999999 })
    } catch (error) { this.setData({ error: error.message || '发送失败' }) } finally { this.setData({ sending: false }) }
  },
  retry() { if (this.data.conversationId) this.loadMessages(this.data.conversationId) }
  ,openHistory() { this.setData({ historyVisible: true }); this.loadConversations().catch(error => this.setData({ error: error.message || '会话列表加载失败' })) }
  ,closeHistory() { this.setData({ historyVisible: false }) }
  ,newConversation() { this.setData({ historyVisible: false, conversationId: 0, messages: [] }); this.onLoad({ kbId: String(this.data.kbId), name: encodeURIComponent(this.data.name) }) }
  ,switchConversation(event) { const item = event.currentTarget.dataset.item; this.setData({ conversationId: item.id, historyVisible: false, name: this.data.name }); this.loadMessages(item.id) }
  ,deleteConversation(event) { const id = event.currentTarget.dataset.id; request.del(`/conversations/${id}`).then(() => this.loadConversations()).catch(error => this.setData({ error: error.message || '删除会话失败' })) }
})
