<template>
  <div class="editor">
    <header class="editor-header">
      <button class="btn-back" @click="backToList">← 返回</button>
      <input
        v-model="form.title"
        class="title-input"
        placeholder="笔记标题"
        @input="scheduleAutoSave"
      />
      <div class="actions">
        <span v-if="mode === 'edit' && savedAt" class="save-hint">
          {{ dirty ? '编辑中…' : `已保存 ${savedAt}` }}
        </span>
        <button class="btn-primary" @click="save" :disabled="saving">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </header>

    <!-- AI 工具栏 -->
    <div class="editor-toolbar">
      <span class="toolbar-label">AI</span>
      <button class="btn-ai" :disabled="aiLoading" @click="runPolish">
        ✨ 润色
      </button>
      <button class="btn-ai" :disabled="aiLoading" @click="runContinue">
        ➕ 续写
      </button>
      <button class="btn-ai" :disabled="aiLoading" @click="runTitle">
        🏷 生成标题
      </button>
      <button class="btn-ai" :disabled="aiLoading" @click="runSummary">
        📋 生成摘要
      </button>
      <span v-if="aiLoading" class="ai-loading">AI 处理中…</span>
    </div>

    <!-- 摘要结果 -->
    <div v-if="summary" class="ai-summary">
      <div class="summary-head">
        <strong>AI 摘要</strong>
        <button class="btn-close" @click="summary = ''">×</button>
      </div>
      <p>{{ summary }}</p>
    </div>

    <div class="editor-body">
      <!-- 左侧：Markdown 编辑 -->
      <textarea
        ref="editorRef"
        v-model="form.content"
        class="md-editor"
        placeholder="用 Markdown 写点什么…"
        @input="onContentInput"
      />

      <!-- 右侧：实时预览 -->
      <div
        class="md-preview"
        v-html="previewHtml"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import { createNote, getNote, updateNote } from '../api/notes'
import { transform } from '../api/ai'

const props = defineProps({
  mode: { type: String, required: true }, // 'create' | 'edit'
  id: { type: String, default: null },
})

const router = useRouter()
const route = useRoute()
const editorRef = ref(null)

const form = reactive({ title: '', content: '' })
const saving = ref(false)
const dirty = ref(false)
const savedAt = ref('')
const aiLoading = ref(false)
const summary = ref('')
let autoSaveTimer = null

const previewHtml = computed(() => marked.parse(form.content || ''))

function backToList() {
  router.push('/notes')
}

function onContentInput() {
  dirty.value = true
  scheduleAutoSave()
}

function scheduleAutoSave() {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => {
    if (props.mode === 'edit' && dirty.value) save()
  }, 1500)
}

// ---------- AI 相关 ----------

/** 取当前选区文本；没有选区时返回整个内容 */
function getSelection() {
  const el = editorRef.value
  const content = form.content
  if (!el) return { text: content, start: 0, end: content.length }
  const start = el.selectionStart ?? 0
  const end = el.selectionEnd ?? 0
  if (start === end) return { text: content, start: 0, end: content.length }
  return { text: content.slice(start, end), start, end }
}

/** 用新文本替换指定区间 */
function replaceRange(start, end, newText) {
  form.content = form.content.slice(0, start) + newText + form.content.slice(end)
  dirty.value = true
  scheduleAutoSave()
}

async function runAI(action, fn) {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    await fn()
  } catch (e) {
    const detail = e.response?.data?.detail || e.message
    alert('AI 调用失败：' + detail)
  } finally {
    aiLoading.value = false
  }
}

/** 润色选中的文本（无选区则润色全文） */
function runPolish() {
  const { text, start, end } = getSelection()
  if (!text.trim()) return alert('请先输入内容')
  return runAI('polish', async () => {
    const result = await transform('polish', text)
    replaceRange(start, end, result)
  })
}

/** 在全文末尾续写 */
function runContinue() {
  const text = form.content
  if (!text.trim()) return alert('请先输入内容')
  return runAI('continue', async () => {
    const result = await transform('continue', text)
    form.content = form.content.replace(/\s*$/, '') + '\n\n' + result
    dirty.value = true
    scheduleAutoSave()
  })
}

/** 用内容生成标题 */
function runTitle() {
  const text = form.content
  if (!text.trim()) return alert('请先输入内容')
  return runAI('title', async () => {
    const result = await transform('title', text)
    form.title = result.replace(/^["'「『]|["'」』]$/g, '').trim()
    dirty.value = true
    scheduleAutoSave()
  })
}

/** 生成摘要 */
function runSummary() {
  const text = form.content
  if (!text.trim()) return alert('请先输入内容')
  return runAI('summary', async () => {
    summary.value = await transform('summary', text)
  })
}

// ---------- 保存 / 加载 ----------

async function save() {
  if (!form.title.trim()) {
    alert('标题不能为空')
    return
  }
  saving.value = true
  try {
    if (props.mode === 'create') {
      const created = await createNote({
        title: form.title,
        content: form.content,
      })
      // 创建成功 → 跳到编辑页
      router.replace(`/notes/${created.id}`)
      return
    } else {
      await updateNote(props.id, {
        title: form.title,
        content: form.content,
      })
    }
    dirty.value = false
    savedAt.value = new Date().toLocaleTimeString()
  } catch (e) {
    alert('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function loadNote() {
  if (props.mode !== 'edit' || !props.id) return
  try {
    const n = await getNote(props.id)
    form.title = n.title
    form.content = n.content
    savedAt.value = new Date(n.updated_at).toLocaleString()
    dirty.value = false
  } catch (e) {
    alert('加载失败：' + (e.response?.data?.detail || e.message))
    router.replace('/notes')
  }
}

// 兼容 hash 路由下 props.id 同步
watch(
  () => route.params.id,
  (v) => {
    if (v) loadNote()
  }
)

onMounted(loadNote)
onBeforeUnmount(() => {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
})
</script>

<style scoped>
.editor {
  display: flex; flex-direction: column;
  height: 100vh;
}
.editor-header {
  display: flex; align-items: center; gap: 1rem;
  padding: .75rem 1.5rem;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
}
.btn-back {
  background: transparent; border: none; cursor: pointer;
  color: #6b7280; font-size: .9rem;
}
.btn-back:hover { color: #111827; }

.title-input {
  flex: 1; border: none; outline: none; font-size: 1.15rem;
  font-weight: 600; padding: .35rem 0;
}
.actions { display: flex; align-items: center; gap: .75rem; }
.save-hint { font-size: .8rem; color: #6b7280; }

/* AI 工具栏 */
.editor-toolbar {
  display: flex; align-items: center; gap: .5rem;
  padding: .5rem 1.5rem;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}
.toolbar-label {
  font-size: .7rem; font-weight: 700; letter-spacing: .05em;
  color: #7c3aed; background: #ede9fe;
  padding: .1rem .45rem; border-radius: 4px;
}
.btn-ai {
  background: #fff; border: 1px solid #ddd6fe; color: #6d28d9;
  padding: .3rem .7rem; border-radius: 6px;
  cursor: pointer; font-size: .8rem;
}
.btn-ai:hover:not(:disabled) { background: #f5f3ff; border-color: #a78bfa; }
.btn-ai:disabled { opacity: .5; cursor: not-allowed; }
.ai-loading { font-size: .8rem; color: #7c3aed; margin-left: .4rem; }

/* 摘要 */
.ai-summary {
  padding: .75rem 1.5rem;
  background: #fffbeb;
  border-bottom: 1px solid #fde68a;
  font-size: .9rem;
  color: #78350f;
}
.summary-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: .3rem;
}
.btn-close {
  background: transparent; border: none; cursor: pointer;
  color: #b45309; font-size: 1.1rem; line-height: 1;
}
.ai-summary p { margin: 0; line-height: 1.6; }

.editor-body {
  flex: 1; display: grid;
  grid-template-columns: 1fr 1fr;
  overflow: hidden;
}
.md-editor, .md-preview {
  height: 100%;
  padding: 1.5rem;
  overflow: auto;
}
.md-editor {
  border: none; outline: none; resize: none;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: .95rem; line-height: 1.6;
  background: #fafafa;
}
.md-preview {
  border-left: 1px solid #e5e7eb;
  font-family: -apple-system, 'Segoe UI', Roboto, sans-serif;
  line-height: 1.7;
  color: #1f2937;
}
.md-preview :deep(h1) { font-size: 1.6rem; border-bottom: 1px solid #e5e7eb; padding-bottom: .3rem; }
.md-preview :deep(h2) { font-size: 1.3rem; }
.md-preview :deep(h3) { font-size: 1.1rem; }
.md-preview :deep(pre) {
  background: #1f2937; color: #e5e7eb;
  padding: 1rem; border-radius: 6px; overflow-x: auto;
}
.md-preview :deep(code) {
  background: #f3f4f6; padding: .15rem .4rem; border-radius: 4px;
  font-family: Consolas, Monaco, monospace; font-size: .85em;
}
.md-preview :deep(pre code) { background: transparent; padding: 0; }
.md-preview :deep(blockquote) {
  border-left: 4px solid #3b82f6; margin: 1rem 0; padding-left: 1rem;
  color: #4b5563;
}
.md-preview :deep(a) { color: #3b82f6; }
.md-preview :deep(table) { border-collapse: collapse; margin: 1rem 0; }
.md-preview :deep(th), .md-preview :deep(td) {
  border: 1px solid #e5e7eb; padding: .4rem .8rem;
}
.md-preview :deep(img) { max-width: 100%; }

.btn-primary {
  background: #3b82f6; color: #fff; border: none;
  padding: .5rem 1rem; border-radius: 6px; cursor: pointer; font-size: .85rem;
}
.btn-primary:hover:not(:disabled) { background: #2563eb; }
.btn-primary:disabled { background: #93c5fd; cursor: not-allowed; }
</style>
