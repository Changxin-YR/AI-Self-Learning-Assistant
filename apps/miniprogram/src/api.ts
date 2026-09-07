const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1'

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('study-agent-token')
  const headers = new Headers(options.headers)
  if (!(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${baseURL}${path}`, { ...options, headers })
  if (response.status === 401) { localStorage.removeItem('study-agent-token'); throw new Error('登录已过期') }
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.detail || '请求失败')
  return payload.data as T
}

export const api = {
  login: (nickname: string) => request<{ access_token: string; user: { id: number; nickname: string } }>('/auth/dev-login', { method: 'POST', body: JSON.stringify({ nickname }) }),
  dashboard: () => request<Dashboard>('/dashboard'),
  knowledgeBases: () => request<{ items: KnowledgeBase[] }>('/knowledge-bases'),
  createKnowledgeBase: (payload: Partial<KnowledgeBase>) => request<KnowledgeBase>('/knowledge-bases', { method: 'POST', body: JSON.stringify(payload) }),
  documents: (id: number) => request<{ items: DocumentItem[] }>(`/knowledge-bases/${id}/documents`),
  upload: (id: number, file: File) => { const form = new FormData(); form.append('file', file); return request<DocumentItem>(`/knowledge-bases/${id}/documents`, { method: 'POST', body: form }) },
  plan: (payload: PlanPayload) => request<StudyPlan>('/study-plans', { method: 'POST', body: JSON.stringify(payload) }),
  activatePlan: (id: number) => request<StudyPlan>(`/study-plans/${id}/activate`, { method: 'POST' }),
  tasks: () => request<{ items: Task[] }>('/tasks/today'),
  completeTask: (id: number) => request<Task>(`/tasks/${id}/complete`, { method: 'POST' }),
  quiz: (id: number) => request<Quiz>(`/quizzes/${id}`),
  createQuiz: (id: number, question_count = 5) => request<Quiz>('/quizzes', { method: 'POST', body: JSON.stringify({ knowledge_base_id: id, question_count }) }),
  conversation: (knowledge_base_id: number) => request<{ id: number }>('/conversations', { method: 'POST', body: JSON.stringify({ knowledge_base_id }) }),
  chat: (conversation_id: number, content: string) => request<{ content: string; citations: Array<{ quote_text: string; page_start: number }> }>(`/conversations/${conversation_id}/messages`, { method: 'POST', body: JSON.stringify({ content }) }),
}

export type KnowledgeBase = { id: number; name: string; description: string; category: string; icon: string; document_count: number; chunk_count: number; status: string }
export type DocumentItem = { id: number; filename: string; status: string; size_bytes: number }
export type Dashboard = { today_minutes: number; task_total: number; task_done: number; weekly_accuracy: number; weak_points: string[] }
export type StudyPlan = { id: number; name: string; target_date: string; daily_minutes: number; status: string; progress_percent: number }
export type PlanPayload = { name: string; knowledge_base_id: number; goal?: string; target_date: string; daily_minutes: number; weekly_days: number }
export type Task = { id: number; title: string; description: string; task_type: string; estimated_minutes: number; status: string }
export type Quiz = { id: number; title: string; status: string; question_count: number; questions: Array<{ id: number; question: string; options: string[]; question_type: string }> }
