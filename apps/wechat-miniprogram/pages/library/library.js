const request = require('../../utils/request')
const { formatError } = require('../../utils/format')
Page({
  data: { loading: true, error: '', libraries: [], selected: null, documents: [], modal: false, name: '', uploading: false },
  onShow() { this.load() },
  onHide() { if (this.pollTimer) clearInterval(this.pollTimer) },
  async load() { this.setData({ loading: true, error: '' }); try { const result = await request.get('/knowledge-bases'); this.setData({ libraries: result.items || [], loading: false }) } catch (error) { this.setData({ loading: false, error: formatError(error) }) } },
  openCreate() { this.setData({ modal: true, name: '' }) },
  closeCreate() { this.setData({ modal: false }) },
  inputName(event) { this.setData({ name: event.detail.value }) },
  async create() { if (!this.data.name.trim()) return; try { const kb = await request.post('/knowledge-bases', { name: this.data.name.trim(), category: '课程', icon: '📘' }); this.setData({ libraries: [kb, ...this.data.libraries], modal: false }); this.select({ currentTarget: { dataset: { kb } } }) } catch (error) { this.setData({ error: formatError(error) }) } },
  async select(event) { const kb = event.currentTarget.dataset.kb || event.currentTarget.dataset.item; this.setData({ selected: kb }); await this.loadDocuments(kb.id); if (this.pollTimer) clearInterval(this.pollTimer); this.pollTimer = setInterval(() => this.loadDocuments(kb.id), 5000) },
  async loadDocuments(kbId) { try { const result = await request.get(`/knowledge-bases/${kbId}/documents`); this.setData({ documents: result.items || [] }) } catch (error) { this.setData({ error: formatError(error) }) } },
  upload() { if (!this.data.selected || this.data.uploading) return; wx.chooseMessageFile({ count: 1, type: 'file', extension: ['pdf', 'docx', 'pptx', 'txt', 'md'], success: ({ tempFiles }) => { const file = tempFiles[0]; if (!file) return; this.setData({ uploading: true, error: '' }); request.upload(`/knowledge-bases/${this.data.selected.id}/documents`, file.path).then(doc => { this.setData({ documents: [doc, ...this.data.documents] }); this.loadDocuments(this.data.selected.id) }).catch(error => this.setData({ error: formatError(error) })).finally(() => this.setData({ uploading: false })) }, fail: error => this.setData({ error: formatError(error) }) }) },
  async retryDocument(event) { const document = this.data.documents.find(item => item.id === event.currentTarget.dataset.id); const action = document?.status === 'READY' ? 'rebuild' : 'retry'; try { await request.post(`/documents/${event.currentTarget.dataset.id}/${action}`); this.loadDocuments(this.data.selected.id) } catch (error) { this.setData({ error: formatError(error) }) } },
  async deleteDocument(event) { const id = event.currentTarget.dataset.id; try { await request.del(`/documents/${id}`); this.setData({ documents: this.data.documents.filter(item => item.id !== id) }); this.load() } catch (error) { this.setData({ error: formatError(error) }) } },
  chat() { if (this.data.selected) wx.navigateTo({ url: `/pages/chat/chat?kbId=${this.data.selected.id}&name=${encodeURIComponent(this.data.selected.name)}` }) },
  retry() { this.load() }
})
