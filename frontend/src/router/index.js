import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/notes' },
  {
    path: '/chat',
    name: 'AgentChat',
    component: () => import('../views/AgentChat.vue'),
  },
  {
    path: '/notes',
    name: 'NoteList',
    component: () => import('../views/NoteList.vue'),
  },
  {
    path: '/notes/new',
    name: 'NoteNew',
    component: () => import('../views/NoteEditor.vue'),
    props: { mode: 'create' },
  },
  {
    path: '/notes/:id',
    name: 'NoteEdit',
    component: () => import('../views/NoteEditor.vue'),
    props: (route) => ({ mode: 'edit', id: route.params.id }),
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
