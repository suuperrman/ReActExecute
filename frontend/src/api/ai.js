import axios from 'axios'

// LLM 调用可能耗时较久，单独设置较长超时
const http = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

/**
 * @param {'polish'|'continue'|'title'|'summary'} action
 * @param {string} text
 * @param {string} [instruction] 附加指令
 * @returns {Promise<string>}
 */
export const transform = (action, text, instruction) =>
  http
    .post('/ai/transform', { action, text, instruction })
    .then((r) => r.data.result)
