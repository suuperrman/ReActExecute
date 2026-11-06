import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

// ---------- 笔记 CRUD ----------

export const listNotes = (page = 1, pageSize = 50, tag) =>
  http.get('/notes', { params: { page, page_size: pageSize, tag: tag || undefined } })
    .then((r) => r.data)

export const getNote = (id) =>
  http.get(`/notes/${id}`).then((r) => r.data)

export const createNote = (payload) =>
  http.post('/notes', payload).then((r) => r.data)

export const updateNote = (id, payload) =>
  http.put(`/notes/${id}`, payload).then((r) => r.data)

export const deleteNote = (id) =>
  http.delete(`/notes/${id}`).then(() => null)
