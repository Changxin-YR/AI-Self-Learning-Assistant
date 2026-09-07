const request = require('../../utils/request')
const { formatError } = require('../../utils/format')
Page({
  data: { loading: true, error: '', libraries: [], selected: null, documents: [], modal: false, name: '', uploading: false },
  onShow() { this.load() },
  async load() { this.setData({ loading: true, error: '' }); try { const result = await request.get('/knowledge-bases'); this.setData({ libraries: result.items || [], loading: false }) } catch (error) { this.setData({ loading: false, error: formatError(error) }) } },
  openCreate() { this.setData({ modal: true, name: '' }) },
  closeCreate() { this.setData({ modal: false }) },
  inputName(event) { this.setData({ name: event.detail.value }) },
  async create() { if (!this.data.name.trim()) return; try { const kb = await request.post('/knowledge-bases', { name: this.data.name.trim(), category: '课程', icon: '📘' }); this.setData({ libraries: [kb, ...this.data.libraries], modal: false }); this.select({ currentTarget: { dataset: { kb } } }) } catch (error) { this.setData({ error: formatError(error) }) } },
  async select(event) { const kb = event.currentTarget.dataset.kb || event.currentTarget.dataset.item; this.setData({ selected: kb }); try { const result = await request.get(`/knowledge-bases/${kb.id}/documents`); this.setData({ documents: result.items || [] }) } catch (error) { this.setData({ error: formatError(error) }) } },
  upload() { if (!this.data.selected) return; wx.chooseMessageFile({ count: 1, type: 'file', extension: ['pdf', 'docx', 'pptx', 'txt', 'md'], success: ({ tempFiles }) => { const file = tempFiles[0]; this.setData({ uploading: true }); request.upload(`/knowledge-bases/${this.data.selected.id}/documents`, file.path).then(doc => this.setData({ documents: [doc, ...this.data.documents] })).catch(error => this.setData({ error: formatError(error) })).finally(() => this.setData({ uploading: false })) } }) },
  chat() { if (this.data.selected) wx.navigateTo({ url: `/pages/chat/chat?kbId=${this.data.selected.id}&name=${encodeURIComponent(this.data.selected.name)}` }) },
  retry() { this.load() }
})
