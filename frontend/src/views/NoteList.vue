<template>
  <div class="note-list">
    <header class="list-header">
      <h1>我的笔记</h1>
      <div class="head-actions">
        <button class="btn-ai-entry" @click="goChat">🤖 Agent</button>
        <button class="btn-primary" @click="createNew">+ 新建笔记</button>
      </div>
    </header>

    <div v-if="activeTag" class="tag-filter">
      <span>筛选标签：</span>
      <span class="tag-chip active">{{ activeTag }}</span>
      <button class="btn-clear-filter" @click="clearFilter">清除筛选</button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="notes.length === 0" class="empty">
      还没有笔记，点右上角「新建笔记」开始吧。
    </div>

    <ul v-else class="list">
      <li
        v-for="n in notes"
        :key="n.id"
        class="list-item"
        @click="openNote(n.id)"
      >
        <div class="item-title">{{ n.title || '(无标题)' }}</div>
        <div class="item-tags" v-if="n.tags && n.tags.length">
          <span
            v-for="t in n.tags"
            :key="t"
            class="tag-chip"
            @click.stop="filterByTag(t)"
          >{{ t }}</span>
        </div>
        <div class="item-meta">
          <span>{{ formatTime(n.updated_at) }}</span>
          <button
            class="btn-danger btn-sm"
            @click.stop="remove(n)"
          >删除</button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listNotes, deleteNote } from '../api/notes'

const router = useRouter()
const notes = ref([])
const loading = ref(false)
const activeTag = ref('')

async function fetchList() {
  loading.value = true
  try {
    const data = await listNotes(1, 100, activeTag.value || undefined)
    notes.value = data.items
  } finally {
    loading.value = false
  }
}

function filterByTag(tag) {
  activeTag.value = tag
  fetchList()
}

function clearFilter() {
  activeTag.value = ''
  fetchList()
}

function openNote(id) {
  router.push(`/notes/${id}`)
}

function createNew() {
  router.push('/notes/new')
}

function goChat() {
  router.push('/chat')
}

async function remove(n) {
  if (!confirm(`确定删除《${n.title || '(无标题)'}》？`)) return
  try {
    await deleteNote(n.id)
    await fetchList()
  } catch (e) {
    alert('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

function formatTime(iso) {
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(fetchList)
</script>

<style scoped>
.note-list {
  max-width: 780px;
  margin: 2rem auto;
  padding: 0 1rem;
}
.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
}
.list-header h1 { margin: 0; font-size: 1.5rem; }
.head-actions { display: flex; gap: .6rem; align-items: center; }

.btn-ai-entry {
  background: #ede9fe; color: #6d28d9; border: 1px solid #ddd6fe;
  padding: .55rem 1rem; border-radius: 6px; cursor: pointer; font-size: .9rem;
}
.btn-ai-entry:hover { background: #ddd6fe; }

.list { list-style: none; padding: 0; margin: 0; }
.list-item {
  padding: 1rem 1.25rem;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  margin-bottom: .75rem;
  cursor: pointer;
  transition: border-color .15s, background .15s;
}
.list-item:hover { border-color: #3b82f6; background: #f0f7ff; }

.item-title { font-weight: 600; color: #111827; }

.item-tags { margin-top: .4rem; display: flex; flex-wrap: wrap; gap: .3rem; }
.tag-chip {
  display: inline-block; font-size: .7rem; color: #6d28d9;
  background: #ede9fe; padding: .1rem .5rem; border-radius: 999px;
  cursor: pointer;
}
.tag-chip:hover { background: #ddd6fe; }
.tag-chip.active { background: #7c3aed; color: #fff; }

.tag-filter {
  display: flex; align-items: center; gap: .5rem;
  padding: .6rem .75rem; margin-bottom: 1rem;
  background: #faf5ff; border: 1px solid #e9d5ff; border-radius: 8px;
  font-size: .85rem; color: #6b7280;
}
.btn-clear-filter {
  background: transparent; border: none; color: #6d28d9;
  cursor: pointer; font-size: .8rem; margin-left: auto;
}
.item-meta {
  margin-top: .35rem;
  font-size: .8rem;
  color: #6b7280;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.empty { text-align: center; color: #9ca3af; padding: 3rem; }

.btn-primary {
  background: #3b82f6; color: #fff; border: none;
  padding: .55rem 1.1rem; border-radius: 6px;
  cursor: pointer; font-size: .9rem;
}
.btn-primary:hover { background: #2563eb; }

.btn-danger {
  background: transparent; color: #ef4444; border: 1px solid #fecaca;
  padding: .15rem .5rem; border-radius: 4px; cursor: pointer;
}
.btn-danger:hover { background: #fef2f2; }
.btn-sm { font-size: .75rem; }
</style>
