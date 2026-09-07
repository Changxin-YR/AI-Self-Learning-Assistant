<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { BookOpen, Brain, CalendarDays, Check, ChevronRight, FileText, Home, LogOut, MessageCircle, Plus, Send, Settings2, Sparkles, Target, Upload, UserRound, X } from 'lucide-vue-next'
import { api, type Dashboard, type DocumentItem, type KnowledgeBase, type StudyPlan, type Task } from './api'

type Tab = 'home' | 'library' | 'learning' | 'profile'
const activeTab = ref<Tab>('home')
const loading = ref(true)
const error = ref('')
const nickname = ref('学习者')
const dashboard = ref<Dashboard>({ today_minutes: 0, task_total: 0, task_done: 0, weekly_accuracy: 0, weak_points: [] })
const libraries = ref<KnowledgeBase[]>([])
const selected = ref<KnowledgeBase | null>(null)
const documents = ref<DocumentItem[]>([])
const tasks = ref<Task[]>([])
const plan = ref<StudyPlan | null>(null)
const newKbOpen = ref(false)
const newKbName = ref('')
const uploadBusy = ref(false)
const planOpen = ref(false)
const chatOpen = ref(false)
const conversationId = ref<number | null>(null)
const chatInput = ref('')
const chatLoading = ref(false)
const chatMessages = ref<Array<{ role: 'user' | 'assistant'; content: string; citation?: string }>>([])

const progress = computed(() => dashboard.value.task_total ? Math.round(dashboard.value.task_done / dashboard.value.task_total * 100) : 0)
const greeting = computed(() => new Date().getHours() < 12 ? '早上好' : new Date().getHours() < 18 ? '下午好' : '晚上好')

async function refresh() {
  loading.value = true; error.value = ''
  try {
    const [d, k, t] = await Promise.all([api.dashboard(), api.knowledgeBases(), api.tasks()])
    dashboard.value = d; libraries.value = k.items; tasks.value = t.items
    if (selected.value) await selectLibrary(selected.value)
  } catch (e) { error.value = e instanceof Error ? e.message : '加载失败' } finally { loading.value = false }
}

async function bootstrap() {
  const token = localStorage.getItem('study-agent-token')
  if (!token) { const result = await api.login('开发学习者'); localStorage.setItem('study-agent-token', result.access_token); nickname.value = result.user.nickname }
  await refresh()
}

async function createLibrary() {
  if (!newKbName.value.trim()) return
  const kb = await api.createKnowledgeBase({ name: newKbName.value.trim(), category: '课程', icon: '📘' })
  libraries.value.unshift(kb); newKbName.value = ''; newKbOpen.value = false; await selectLibrary(kb)
}

async function selectLibrary(kb: KnowledgeBase) {
  selected.value = kb; documents.value = (await api.documents(kb.id)).items; activeTab.value = 'library'
}

async function onUpload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]; if (!file || !selected.value) return
  uploadBusy.value = true
  try { const item = await api.upload(selected.value.id, file); documents.value.unshift(item); await refresh() } catch (e) { error.value = e instanceof Error ? e.message : '上传失败' } finally { uploadBusy.value = false }
}

async function createPlan() {
  if (!selected.value) return
  const result = await api.plan({ name: '14 天学习冲刺', knowledge_base_id: selected.value.id, goal: '掌握核心知识并完成测验', target_date: new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10), daily_minutes: 30, weekly_days: 5 })
  plan.value = result; planOpen.value = false
}

async function activatePlan() { if (plan.value) { plan.value = await api.activatePlan(plan.value.id); await refresh(); activeTab.value = 'learning' } }
async function complete(task: Task) { await api.completeTask(task.id); task.status = 'DONE'; dashboard.value.task_done += 1 }
function logout() { localStorage.removeItem('study-agent-token'); location.reload() }

async function openChat() {
  if (!selected.value) { selected.value = libraries.value[0] || null }
  if (!selected.value) { error.value = '请先创建知识库'; return }
  const conversation = await api.conversation(selected.value.id); conversationId.value = conversation.id; chatMessages.value = []; chatOpen.value = true
}
async function sendChat() {
  if (!chatInput.value.trim() || !conversationId.value) return
  const text = chatInput.value.trim(); chatInput.value = ''; chatMessages.value.push({ role: 'user', content: text }); chatLoading.value = true
  try { const result = await api.chat(conversationId.value, text); chatMessages.value.push({ role: 'assistant', content: result.content, citation: result.citations[0]?.quote_text }) } catch (e) { error.value = e instanceof Error ? e.message : '发送失败' } finally { chatLoading.value = false }
}

onMounted(bootstrap)
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand-mark"><span class="brand-dot"></span><span>StudyAgent</span></div>
      <div class="top-actions"><button class="icon-btn" title="设置"><Settings2 :size="18" /></button><div class="avatar">{{ nickname.slice(0, 1) }}</div></div>
    </header>

    <main class="content">
      <div v-if="error" class="alert"><span>{{ error }}</span><button @click="error = ''"><X :size="16" /></button></div>
      <div v-if="loading" class="skeleton-stack"><div class="skeleton hero"></div><div class="skeleton row"></div><div class="skeleton row"></div></div>
      <template v-else>
        <section v-if="activeTab === 'home'" class="view home-view">
          <div class="welcome"><div><p class="eyebrow">{{ greeting }}，{{ nickname }}</p><h1>今天也保持<br><em>好奇心。</em></h1></div><div class="streak"><Sparkles :size="16" /><strong>7</strong><span>连续学习天</span></div></div>
          <section class="focus-card"><div class="focus-head"><div><p class="eyebrow light">今日学习</p><h2>{{ dashboard.task_done }} / {{ dashboard.task_total || 4 }} 项任务</h2></div><div class="ring" :style="{ '--progress': `${progress}%` }"><span>{{ progress }}%</span></div></div><div class="progress-line"><span :style="{ width: `${progress}%` }"></span></div><div class="focus-foot"><span><CalendarDays :size="15" />预计 {{ Math.max(30, (dashboard.task_total || 4) * 15) }} 分钟</span><button class="light-button" @click="activeTab = 'learning'">继续学习 <ChevronRight :size="16" /></button></div></section>
          <section class="section"><div class="section-title"><h3>AI 快捷入口</h3><span>一键开始</span></div><div class="quick-grid"><button @click="openChat"><MessageCircle :size="20" /><span>问知识库</span><small>从资料中找答案</small></button><button @click="openChat"><FileText :size="20" /><span>总结资料</span><small>提炼核心内容</small></button><button @click="selected ? createPlan() : (newKbOpen = true)"><Target :size="20" /><span>制定计划</span><small>按目标安排学习</small></button><button @click="selected ? activeTab = 'learning' : (newKbOpen = true)"><Brain :size="20" /><span>生成测试</span><small>检验掌握程度</small></button></div></section>
          <section class="section"><div class="section-title"><h3>最近知识库</h3><button class="text-btn" @click="activeTab = 'library'">查看全部 <ChevronRight :size="15" /></button></div><div v-if="libraries.length" class="library-strip"><button v-for="kb in libraries.slice(0, 3)" :key="kb.id" class="library-mini" @click="selectLibrary(kb)"><span class="library-icon">{{ kb.icon }}</span><span><strong>{{ kb.name }}</strong><small>{{ kb.document_count }} 份资料 · {{ kb.chunk_count }} 个片段</small></span><ChevronRight :size="16" /></button></div><div v-else class="empty"><BookOpen :size="24" /><p>创建第一个知识库，开始沉淀你的学习资料</p><button class="primary-button" @click="newKbOpen = true"><Plus :size="16" />新建知识库</button></div></section>
        </section>

        <section v-else-if="activeTab === 'library'" class="view"><div class="page-head"><div><p class="eyebrow">你的资料空间</p><h1>知识库</h1></div><button class="primary-button" @click="newKbOpen = true"><Plus :size="17" />新建</button></div><div class="library-grid"><button v-for="kb in libraries" :key="kb.id" class="library-card" @click="selectLibrary(kb)"><span class="library-icon large">{{ kb.icon }}</span><div class="card-main"><h3>{{ kb.name }}</h3><p>{{ kb.description || '还没有描述，先从上传资料开始。' }}</p><div class="meta"><span>{{ kb.document_count }} 份资料</span><span>{{ kb.chunk_count }} 个片段</span></div></div><span class="status-dot" :class="{ ready: kb.status === 'ACTIVE' }"></span></button><div v-if="!libraries.length" class="empty wide"><BookOpen :size="28" /><h3>还没有知识库</h3><p>将课程、教材或笔记放进来，StudyAgent 会帮你整理。</p><button class="primary-button" @click="newKbOpen = true"><Plus :size="16" />创建第一个知识库</button></div></div><div v-if="selected" class="detail-panel"><div class="detail-head"><div><span class="eyebrow">当前知识库</span><h2>{{ selected.icon }} {{ selected.name }}</h2></div><div class="detail-actions"><label class="outline-button"><Upload :size="16" />{{ uploadBusy ? '处理中…' : '上传资料' }}<input type="file" accept=".pdf,.docx,.pptx,.txt,.md" hidden @change="onUpload" /></label><button class="primary-button" @click="openChat"><MessageCircle :size="16" />向 AI 提问</button></div></div><div class="detail-tabs"><span class="active">文档（{{ documents.length }}）</span><span>知识点</span><span>历史对话</span></div><div v-if="documents.length" class="document-list"><div v-for="doc in documents" :key="doc.id" class="document-row"><FileText :size="18" /><span><strong>{{ doc.filename }}</strong><small>{{ Math.round(doc.size_bytes / 1024) }} KB</small></span><span class="doc-status" :class="doc.status.toLowerCase()">{{ doc.status === 'READY' ? '已就绪' : doc.status }}</span></div></div><div v-else class="empty compact"><Upload :size="22" /><p>上传 PDF、DOCX、PPTX、TXT 或 MD 文件</p></div></div></section>

        <section v-else-if="activeTab === 'learning'" class="view"><div class="page-head"><div><p class="eyebrow">保持节奏</p><h1>学习计划</h1></div><button class="primary-button" @click="planOpen = true"><Plus :size="17" />新计划</button></div><div v-if="plan" class="plan-card"><div><span class="eyebrow light">当前计划 · {{ plan.status === 'ACTIVE' ? '进行中' : '待确认' }}</span><h2>{{ plan.name }}</h2><p>目标日期 {{ plan.target_date }} · 每天 {{ plan.daily_minutes }} 分钟</p></div><button v-if="plan.status === 'DRAFT'" class="light-button" @click="activatePlan">确认并开始 <ChevronRight :size="16" /></button><div v-else class="plan-progress"><strong>{{ plan.progress_percent }}%</strong><span>完成度</span></div></div><div v-else class="empty wide"><Target :size="28" /><h3>还没有学习计划</h3><p>告诉我你的目标和时间，生成一份可执行的路线图。</p><button class="primary-button" @click="planOpen = true"><Sparkles :size="16" />生成计划</button></div><section v-if="tasks.length" class="task-section"><div class="section-title"><h3>今日任务</h3><span>{{ tasks.filter(t => t.status === 'DONE').length }} / {{ tasks.length }} 已完成</span></div><div class="task-list"><div v-for="task in tasks" :key="task.id" class="task-row" :class="{ done: task.status === 'DONE' }"><button class="check-btn" @click="task.status !== 'DONE' && complete(task)"><Check :size="15" /></button><div><strong>{{ task.title }}</strong><small>{{ task.task_type }} · {{ task.estimated_minutes }} 分钟</small></div><ChevronRight :size="17" /></div></div></section></section>

        <section v-else class="view"><div class="profile-hero"><div class="avatar xl">{{ nickname.slice(0, 1) }}</div><div><p class="eyebrow">StudyAgent 账户</p><h1>{{ nickname }}</h1><span>开发模式 · 本地数据</span></div></div><div class="stats-row"><div><strong>{{ dashboard.today_minutes }}</strong><span>今日分钟</span></div><div><strong>{{ dashboard.weekly_accuracy }}%</strong><span>本周正确率</span></div><div><strong>{{ dashboard.task_done }}</strong><span>已完成任务</span></div></div><div class="settings-list"><button><Settings2 :size="18" /><span>AI 设置</span><ChevronRight :size="17" /></button><button><UserRound :size="18" /><span>数据与隐私</span><ChevronRight :size="17" /></button><button @click="logout"><LogOut :size="18" /><span>退出登录</span><ChevronRight :size="17" /></button></div></section>
      </template>
    </main>

    <nav class="tabbar"><button :class="{ active: activeTab === 'home' }" @click="activeTab = 'home'"><Home :size="19" /><span>首页</span></button><button :class="{ active: activeTab === 'library' }" @click="activeTab = 'library'"><BookOpen :size="19" /><span>知识库</span></button><button :class="{ active: activeTab === 'learning' }" @click="activeTab = 'learning'"><Target :size="19" /><span>学习</span></button><button :class="{ active: activeTab === 'profile' }" @click="activeTab = 'profile'"><UserRound :size="19" /><span>我的</span></button></nav>

    <div v-if="newKbOpen" class="modal-backdrop" @click.self="newKbOpen = false"><div class="modal"><div class="modal-head"><h2>新建知识库</h2><button @click="newKbOpen = false"><X :size="19" /></button></div><label>名称<input v-model="newKbName" maxlength="50" placeholder="例如：计算机网络" @keyup.enter="createLibrary" /></label><p class="hint">支持课程、考试、技术和其他资料，后续可以继续添加文件。</p><button class="primary-button full" @click="createLibrary">创建知识库 <ChevronRight :size="16" /></button></div></div>
    <div v-if="planOpen" class="modal-backdrop" @click.self="planOpen = false"><div class="modal"><div class="modal-head"><h2>生成学习计划</h2><button @click="planOpen = false"><X :size="19" /></button></div><div class="plan-preview"><Sparkles :size="22" /><div><strong>AI 会根据你的知识库生成草案</strong><p>默认 14 天 · 每天 30 分钟 · 标准强度</p></div></div><button class="primary-button full" @click="createPlan">生成草案 <ChevronRight :size="16" /></button></div></div>
    <div v-if="chatOpen" class="chat-drawer"><div class="chat-head"><div><span class="eyebrow">AI 学习助手</span><h2>{{ selected?.name }}</h2></div><button @click="chatOpen = false"><X :size="20" /></button></div><div class="chat-body"><div v-if="!chatMessages.length" class="chat-empty"><MessageCircle :size="28" /><p>问问你的资料。<br />我会标注答案来源。</p></div><div v-for="(message, index) in chatMessages" :key="index" class="chat-message" :class="message.role"><div class="message-bubble">{{ message.content }}</div><div v-if="message.citation" class="citation"><FileText :size="14" /><span>来源片段：{{ message.citation }}</span></div></div><div v-if="chatLoading" class="typing"><span></span><span></span><span></span>正在检索资料…</div></div><form class="chat-input" @submit.prevent="sendChat"><input v-model="chatInput" placeholder="问一个关于资料的问题…" /><button type="submit" :disabled="chatLoading"><Send :size="18" /></button></form></div>
  </div>
</template>
