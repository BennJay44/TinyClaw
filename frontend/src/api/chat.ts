import api from './index'

// SSE fetch 使用与 axios 相同的 base URL（已包含 /api）
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
const API_KEY = import.meta.env.VITE_API_KEY || ''

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  content: string
  session_id: string | null
}

export interface StreamEvent {
  type: 'session' | 'step_start' | 'chunk' | 'tool_start' | 'tool_finish' | 'step_finish' | 'done' | 'error'
  content?: string
  tool?: string
  args?: Record<string, unknown>
  result?: string
  error?: string
  session_id?: string | null
  step?: number
  max_steps?: number
}

export type StreamCallback = (event: StreamEvent) => void

export const chatApi = {
  // 流式发送消息 (SSE)
  sendMessage: async (message: string, sessionId?: string) => {
    return api.post('/chat/send', { message, session_id: sessionId })
  },

  // 同步发送消息（支持取消，超时时间 5 分钟）
  sendMessageSync: async (
    message: string,
    sessionId?: string,
    signal?: AbortSignal
  ): Promise<ChatResponse> => {
    return api.post('/chat/send/sync', { message, session_id: sessionId }, {
      signal,
      timeout: 300000, // 5 分钟超时
    })
  },

  // 流式发送消息 (SSE) - 返回完整响应
  sendMessageStream: async (
    message: string,
    sessionId: string | null | undefined,
    onChunk: StreamCallback,
    signal?: AbortSignal
  ): Promise<ChatResponse> => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (API_KEY) {
      headers['X-API-Key'] = API_KEY
    }

    const response = await fetch(`${API_BASE}/chat/send/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ message, session_id: sessionId }),
      signal,
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let fullContent = ''
    let finalSessionId = sessionId

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const decoded = decoder.decode(value, { stream: true })
        buffer += decoded

        // 按双换行分割完整的 SSE 事件块（兼容 \r\n 和 \n）
        const normalized = buffer.replace(/\r\n/g, '\n')
        const blocks = normalized.split('\n\n')
        buffer = blocks.pop() || ''

        for (const block of blocks) {
          if (!block.trim()) continue

          let eventType = ''
          let dataLines: string[] = []

          for (const line of block.split('\n')) {
            const trimmedLine = line.replace(/\r$/, '')
            if (trimmedLine.startsWith('event:')) {
              eventType = trimmedLine.substring(6).trim()
            } else if (trimmedLine.startsWith('data:')) {
              dataLines.push(trimmedLine.substring(5))
            }
            // 忽略 id:, retry:, 注释行等
          }

          // 跳过心跳 ping 和无数据事件
          if (eventType === 'ping' || dataLines.length === 0) continue

          const dataStr = dataLines.join('\n').trim()
          if (!dataStr) continue

          try {
            const parsed = JSON.parse(dataStr)

            if (eventType === 'session') {
              finalSessionId = parsed.session_id
              onChunk({ type: 'session', session_id: parsed.session_id })
            } else if (eventType === 'step_start') {
              onChunk({ type: 'step_start', step: parsed.step, max_steps: parsed.max_steps })
            } else if (eventType === 'chunk') {
              fullContent += parsed.content || ''
              onChunk({ type: 'chunk', content: parsed.content })
            } else if (eventType === 'tool_start') {
              onChunk({ type: 'tool_start', tool: parsed.tool, args: parsed.args })
            } else if (eventType === 'tool_finish') {
              onChunk({ type: 'tool_finish', tool: parsed.tool, result: parsed.result })
            } else if (eventType === 'step_finish') {
              onChunk({ type: 'step_finish', step: parsed.step })
            } else if (eventType === 'done') {
              finalSessionId = parsed.session_id
              onChunk({ type: 'done', content: parsed.content, session_id: parsed.session_id })
            } else if (eventType === 'error') {
              onChunk({ type: 'error', error: parsed.error })
            }
          } catch {
            // 忽略解析错误
          }
        }
      }
    } finally {
      reader.releaseLock()
    }

    return { content: fullContent, session_id: finalSessionId ?? null }
  },
}
