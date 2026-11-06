import axios from 'axios'

// Agent 可能多轮工具调用，耗时长，超时放宽
const http = axios.create({
  baseURL: '/api',
  timeout: 180000,
})

/**
 * 非流式对话
 * @param {string} message
 * @param {string} [sessionId]
 * @returns {Promise<{session_id:string, answer:string, steps:Array, stopped_reason:string}>}
 */
export const agentChat = (message, sessionId) =>
  http.post('/agent/chat', { message, session_id: sessionId }).then((r) => r.data)

/**
 * 流式对话（SSE）。回调说明：
 * - onStep(step): step = { step, tool, arguments, result, ok }
 * - onAnswer(content)
 * - onDone(sessionId, stoppedReason)
 * - onError(message)
 * @returns {Promise<void>}
 */
export async function agentChatStream(message, sessionId, { onStep, onAnswer, onDone, onError }) {
  const resp = await fetch('/api/agent/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  })

  if (!resp.ok) {
    let detail = 'HTTP ' + resp.status
    try { detail = (await resp.json()).detail || detail } catch { /* ignore */ }
    onError && onError(detail)
    return
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const dispatch = (json) => {
    switch (json.type) {
      case 'step': onStep && onStep(json); break
      case 'answer': onAnswer && onAnswer(json.content); break
      case 'done': onDone && onDone(json.session_id, json.stopped_reason); break
      case 'error': onError && onError(json.message); break
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop()
    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data:')) continue
      try { dispatch(JSON.parse(line.slice(5).trim())) } catch { /* 忽略解析失败 */ }
    }
  }
}

// ---------- 会话管理 ----------

export const listSessions = () => http.get('/agent/sessions').then((r) => r.data)

export const getSession = (id) => http.get(`/agent/sessions/${id}`).then((r) => r.data)

export const deleteSession = (id) => http.delete(`/agent/sessions/${id}`).then(() => null)