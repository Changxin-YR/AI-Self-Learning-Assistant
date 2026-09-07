const request = require('../../utils/request')
Page({
  data: { kbId: 0, name: '知识库', conversationId: 0, input: '', messages: [], sending: false },
  onLoad(options) { this.setData({ kbId: Number(options.kbId), name: decodeURIComponent(options.name || '知识库') }); request.post('/conversations', { knowledge_base_id: Number(options.kbId) }).then(conversation => this.setData({ conversationId: conversation.id })).catch(error => wx.showToast({ title: error.message || '会话创建失败', icon: 'none' })) },
  input(event) { this.setData({ input: event.detail.value }) },
  async send() { const text = this.data.input.trim(); if (!text || !this.data.conversationId || this.data.sending) return; const userMessage = { role: 'USER', content: text }; this.setData({ input: '', sending: true, messages: [...this.data.messages, userMessage] }); try { const result = await request.post(`/conversations/${this.data.conversationId}/messages`, { content: text }); const citation = result.citations?.[0]; this.setData({ messages: [...this.data.messages, { role: 'ASSISTANT', content: result.content, citation: citation?.quote_text }] }) } catch (error) { wx.showToast({ title: error.message || '发送失败', icon: 'none' }) } finally { this.setData({ sending: false }) } }
})
