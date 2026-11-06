<template>
  <div class="chat-layout">
    <!-- 左侧会话列表 -->
    <aside class="sidebar">
      <div class="sidebar-head">
        <span class="sidebar-title">会话</span>
        <button class="btn-new" @click="newSession">＋</button>
      </div>
      <ul class="session-list">
        <li
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === sessionId }"
          @click="openSession(s.id)"
        >
          <span class="session-name">{{ s.title }}</span>
          <button class="btn-del" @click.stop="removeSession(s)">×</button>
        </li>
      </ul>
    </aside>

    <!-- 右侧聊天区 -->
    <div class="chat">
      <header class="chat-header">
        <button class="btn-back" @click="router.push('/notes')">← 返回笔记</button>
        <div class="title">
          🤖 Agent 助手
          <span class="subtitle">用一句话操作你的笔记库</span>
        </div>
        <button class="btn-clear" :disabled="!messages.length" @click="newSession">新对话</button>
      </header>

      <div class="chat-body" ref="bodyRef">
        <div v-if="!messages.length" class="welcome">
          <h2>👋 试试这些指令</h2>
          <ul>
            <li @click="use('我有哪些笔记？')">我有哪些笔记？</li>
            <li @click="use('找出关于读书的笔记并告诉我正文')">找出关于读书的笔记并告诉我正文</li>
            <li @click="use('帮我新建一篇笔记，标题叫「周报」，正文写本周完成了 Agent 功能')">
              帮我新建一篇笔记…
            </li>
            <li @click="use('把标题包含「待办」的笔记正文改成已完成')">
              把标题包含「待办」的笔记正文改成已完成
            </li>
          </ul>
        </div>

        <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
          <div v-if="m.role === 'user'" class="bubble user">{{ m.content }}</div>

          <div v-else class="bubble agent">
            <div v-if="m.steps && m.steps.length" class="steps">
              <div
                v-for="s in m.steps"
                :key="s.step + '-' + s.tool"
                class="step"
                :class="{ failed: !s.ok }"
              >
                <div class="step-head" @click="toggle(i, s)">
                  <span class="step-caret">{{ opened[stepKey(i, s)] ? '▾' : '▸' }}</span>
                  <code class="tool-name">{{ s.tool }}</code>
                  <span class="step-args">{{ brief(s) }}</span>
                  <span class="step-status">{{ s.ok ? '✓' : '✕' }}</span>
                </div>
                <pre v-if="opened[stepKey(i, s)]" class="step-result">{{ pretty(s.result) }}</pre>
              </div>
            </div>

            <div v-if="m.content" class="answer" v-html="render(m.content)" />
            <div v-else class="answer thinking-text">
              <span class="dot"></span><span class="dot"></span><span class="dot"></span>
            </div>
          </div>
        </div>
      </div>

      <footer class="chat-input">
        <textarea
          v-model="draft"
          class="input-box"
          rows="1"
          placeholder="让 Agent 帮你管理笔记…（Enter 发送，Shift+Enter 换行）"
          @keydown.enter.exact.prevent="send"
        />
        <button class="btn-send" :disabled="loading || !draft.trim()" @click="send">
          {{ loading ? '执行中…' : '发送' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import { agentChatStream, deleteSession, getSession, listSessions } from '../api/agent'

const router = useRouter()

const sessions = ref([])
const sessionId = ref(null)
const messages = ref([])
const draft = ref('')
const loading = ref(false)
const bodyRef = ref(null)
const opened = reactive({})

function stepKey(i, s) {
  return i + '-' + s.step + '-' + s.tool
}

function use(text) {
  draft.value = text
  send()
}

function toggle(i, s) {
  const key = stepKey(i, s)
  opened[key] = !opened[key]
}

function brief(s) {
  const a = s.arguments || {}
  const keys = Object.keys(a)
  if (!keys.length) return '()'
  return '(' + keys.map((k) => `${k}=${JSON.stringify(a[k])}`).join(', ') + ')'
}

function pretty(obj) {
  return JSON.stringify(obj, null, 2)
}

function render(text) {
  return marked.parse(text || '')
}

async function scrollBottom() {
  await nextTick()
  if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
}

async function reloadSessions() {
  sessions.value = await listSessions()
}

function newSession() {
  sessionId.value = null
  messages.value = []
  draft.value = ''
}

async function openSession(id) {
  sessionId.value = id
  const data = await getSession(id)
  messages.value = data.messages.map((m) => ({
    role: m.role,
    content: m.content,
    steps: m.steps || [],
  }))
  scrollBottom()
}

async function removeSession(s) {
  if (!confirm(`删除会话「${s.title}」？`)) return
  await deleteSession(s.id)
  if (sessionId.value === s.id) newSession()
  reloadSessions()
}

async function send() {
  const text = draft.value.trim()
  if (!text || loading.value) return

  loading.value = true
  messages.value.push({ role: 'user', content: text })
  draft.value = ''

  // 流式占位消息
  const agentMsg = { role: 'agent', content: '', steps: [] }
  messages.value.push(agentMsg)
  scrollBottom()

  const priorSession = sessionId.value
  let newSessionId = priorSession

  await agentChatStream(text, priorSession, {
    onStep(s) {
      agentMsg.steps.push({
        step: s.step, tool: s.tool, arguments: s.arguments, result: s.result, ok: s.ok,
      })
      scrollBottom()
    },
    onAnswer(content) {
      agentMsg.content = content
      scrollBottom()
    },
    onDone(sid) {
      newSessionId = sid
      if (!sessionId.value) sessionId.value = sid
      reloadSessions()
    },
    onError(msg) {
      agentMsg.content = '**执行失败**：' + msg
    },
  }).catch((e) => {
    if (!agentMsg.content) agentMsg.content = '**执行失败**：' + (e.message || '网络错误')
  }).finally(() => {
    loading.value = false
    scrollBottom()
  })
}

watch(messages, scrollBottom, { deep: true })
onMounted(reloadSessions)
</script>

<style scoped>
.chat-layout { display: flex; height: 100vh; background: #f3f4f6; }

/* 会话侧边栏 */
.sidebar {
  width: 220px; background: #fff; border-right: 1px solid #e5e7eb;
  display: flex; flex-direction: column; flex-shrink: 0;
}
.sidebar-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: .8rem 1rem; border-bottom: 1px solid #e5e7eb;
}
.sidebar-title { font-weight: 600; font-size: .9rem; }
.btn-new {
  background: #7c3aed; color: #fff; border: none; width: 26px; height: 26px;
  border-radius: 6px; cursor: pointer; font-size: 1rem; line-height: 1;
}
.session-list { list-style: none; padding: .5rem; margin: 0; overflow-y: auto; flex: 1; }
.session-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: .55rem .6rem; border-radius: 6px; cursor: pointer; font-size: .85rem;
  color: #374151; margin-bottom: .2rem;
}
.session-item:hover { background: #f3f4f6; }
.session-item.active { background: #ede9fe; color: #6d28d9; }
.session-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.btn-del {
  background: transparent; border: none; color: #9ca3af; cursor: pointer;
  font-size: 1rem; line-height: 1; padding: 0 .2rem; visibility: hidden;
}
.session-item:hover .btn-del { visibility: visible; }
.btn-del:hover { color: #ef4444; }

/* 聊天区 */
.chat { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.chat-header {
  display: flex; align-items: center; gap: 1rem;
  padding: .7rem 1.5rem;
  background: #fff; border-bottom: 1px solid #e5e7eb;
}
.btn-back, .btn-clear {
  background: transparent; border: none; cursor: pointer;
  color: #6b7280; font-size: .85rem;
}
.btn-clear:disabled { opacity: .4; cursor: not-allowed; }
.chat-header .title { flex: 1; font-weight: 600; }
.subtitle { font-weight: 400; font-size: .8rem; color: #9ca3af; margin-left: .5rem; }

.chat-body { flex: 1; overflow-y: auto; padding: 1.5rem; }
.welcome { max-width: 560px; margin: 3rem auto; text-align: center; color: #6b7280; }
.welcome h2 { color: #374151; }
.welcome ul { list-style: none; padding: 0; }
.welcome li {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
  padding: .7rem 1rem; margin: .5rem 0; cursor: pointer;
  transition: border-color .15s;
}
.welcome li:hover { border-color: #7c3aed; background: #faf5ff; }

.msg-row { margin-bottom: 1rem; display: flex; }
.msg-row.user { justify-content: flex-end; }
.bubble {
  max-width: 78%; padding: .8rem 1rem; border-radius: 10px;
  line-height: 1.65; font-size: .92rem;
}
.bubble.user { background: #3b82f6; color: #fff; }
.bubble.agent { background: #fff; border: 1px solid #e5e7eb; }
.bubble.agent :deep(p:first-child) { margin-top: 0; }
.bubble.agent :deep(p:last-child) { margin-bottom: 0; }
.bubble.agent :deep(table) { border-collapse: collapse; margin: .6rem 0; }
.bubble.agent :deep(th), .bubble.agent :deep(td) { border: 1px solid #e5e7eb; padding: .3rem .6rem; }
.bubble.agent :deep(code) {
  background: #f3f4f6; padding: .1rem .35rem; border-radius: 4px; font-size: .85em;
}
.bubble.agent :deep(pre) { background: #1f2937; color: #e5e7eb; padding: .8rem; border-radius: 6px; overflow-x: auto; }
.bubble.agent :deep(pre code) { background: transparent; padding: 0; }
.bubble.agent :deep(blockquote) {
  border-left: 3px solid #d1d5db; margin: .5rem 0; padding-left: .8rem; color: #6b7280;
}

.steps { margin-bottom: .7rem; }
.step {
  border: 1px solid #e5e7eb; border-radius: 6px;
  margin-bottom: .4rem; background: #fafafa; overflow: hidden;
}
.step.failed { border-color: #fecaca; background: #fef2f2; }
.step-head {
  display: flex; align-items: center; gap: .5rem;
  padding: .4rem .6rem; cursor: pointer; font-size: .8rem;
}
.step-caret { color: #9ca3af; width: .8rem; }
.tool-name {
  background: #ede9fe; color: #6d28d9;
  padding: .1rem .4rem; border-radius: 4px; font-size: .78rem;
}
.step-args {
  color: #6b7280; flex: 1; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.step-status { color: #16a34a; font-weight: 700; }
.step.failed .step-status { color: #dc2626; }
.step-result {
  margin: 0; padding: .6rem .8rem;
  background: #fff; border-top: 1px solid #e5e7eb;
  font-size: .75rem; line-height: 1.5;
  max-height: 240px; overflow: auto;
  white-space: pre-wrap; word-break: break-all;
}

.dot {
  display: inline-block; width: 6px; height: 6px; margin: 6px 3px 0;
  background: #9ca3af; border-radius: 50%; animation: blink 1.2s infinite;
}
.dot:nth-child(2) { animation-delay: .2s; }
.dot:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 0%, 80%, 100% { opacity: .3 } 40% { opacity: 1 } }

.chat-input {
  display: flex; gap: .75rem; align-items: flex-end;
  padding: .85rem 1.5rem; background: #fff; border-top: 1px solid #e5e7eb;
}
.input-box {
  flex: 1; resize: none; border: 1px solid #d1d5db; border-radius: 8px;
  padding: .6rem .8rem; font-family: inherit; font-size: .92rem;
  max-height: 160px; outline: none;
}
.input-box:focus { border-color: #7c3aed; }
.btn-send {
  background: #7c3aed; color: #fff; border: none;
  padding: .6rem 1.3rem; border-radius: 8px; cursor: pointer; font-size: .9rem;
}
.btn-send:hover:not(:disabled) { background: #6d28d9; }
.btn-send:disabled { background: #c4b5fd; cursor: not-allowed; }
</style>