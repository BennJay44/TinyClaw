<script setup lang="ts">
import { ref, watch, computed, nextTick, onMounted } from 'vue'
import { Input, Button, message } from 'ant-design-vue'
import { SendOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { useRouter, useRoute } from 'vue-router'
import { sessionApi } from '@/api/session'
import { chatApi } from '@/api/chat'
import { configApi } from '@/api/config'
import MessageGroup from '@/components/MessageGroup.vue'
import type { Message, MessageSegment, TextSegment, ToolSegment, MessageGroup as MsgGroup } from '@/components/MessageGroup.vue'
import ClawIcon from '@/assets/tinyclaw_logo.svg'

const SESSION_STORAGE_KEY = 'tinyclaw.lastSessionId'

const assistantName = ref('TinyClaw')
const router = useRouter()
const route = useRoute()
const inputMessage = ref('')
const messages = ref<Message[]>([])
const loading = ref(false)
const currentSessionId = ref<string | null>(null)
const messagesContainer = ref<HTMLElement | null>(null)
const abortController = ref<AbortController | null>(null)
const initializing = ref(true)

// 消息分组（Slack 风格）
const messageGroups = computed<MsgGroup[]>(() => {
  const groups: MsgGroup[] = []
  for (const msg of messages.value) {
    const lastGroup = groups[groups.length - 1]
    if (lastGroup && lastGroup.role === msg.role) {
      lastGroup.messages.push(msg)
    } else {
      groups.push({ role: msg.role, messages: [msg] })
    }
  }
  return groups
})

// 是否显示底部加载指示器
const shouldShowLoadingIndicator = computed(() => {
  if (messages.value.length === 0) return true
  const lastMsg = messages.value[messages.value.length - 1]
  if (lastMsg?.role !== 'assistant') return true
  return !hasVisibleContent(lastMsg)
})

const hasVisibleContent = (msg: Message): boolean => {
  if (!msg.segments || msg.segments.length === 0) return !!msg.content
  for (const segment of msg.segments) {
    if (segment.type === 'text' && segment.content) return true
    if (segment.type === 'tool') return true
  }
  return false
}

// 会话管理
const saveCurrentSession = (sessionId: string) => {
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId)
}

const getLastSession = (): string | null => {
  return localStorage.getItem(SESSION_STORAGE_KEY)
}

// 加载会话历史
const loadSessionHistory = async (sessionId: string) => {
  try {
    const res = await sessionApi.getHistory(sessionId)
    const rawMessages = res.messages
    const toolResults: Map<string, string> = new Map()

    for (const msg of rawMessages) {
      if (msg.role === 'tool' && msg.tool_call_id && msg.content) {
        toolResults.set(msg.tool_call_id, msg.content)
      }
    }

    const displayMessages: Message[] = []
    let pendingAssistant: Message | null = null

    for (let i = 0; i < rawMessages.length; i++) {
      const msg = rawMessages[i]!

      if (msg.role === 'user') {
        if (pendingAssistant) {
          displayMessages.push(pendingAssistant)
          pendingAssistant = null
        }
        displayMessages.push({
          id: Date.now() + i,
          role: 'user',
          content: msg.content || '',
          timestamp: new Date()
        })
      } else if (msg.role === 'assistant') {
        if (msg.tool_calls && msg.tool_calls.length > 0) {
          const segments: MessageSegment[] = []
          msg.tool_calls.forEach((tc: { id: string; function: { name: string; arguments: string } }, tcIndex: number) => {
            const result = toolResults.get(tc.id)
            segments.push({
              type: 'tool',
              id: Date.now() + i * 1000 + tcIndex,
              tool: tc.function.name,
              args: JSON.parse(tc.function.arguments || '{}'),
              result: result,
              status: result?.startsWith('❌') ? 'error' : 'done'
            })
          })

          const nextMsg = rawMessages[i + 1]
          if (nextMsg && nextMsg.role === 'assistant' && !nextMsg.tool_calls && nextMsg.content) {
            segments.push({
              type: 'text',
              id: Date.now() + i * 1000 + 100,
              content: nextMsg.content
            })
            i++
          }

          pendingAssistant = {
            id: Date.now() + i,
            role: 'assistant',
            content: '',
            timestamp: new Date(),
            segments
          }
        } else if (msg.content) {
          if (pendingAssistant) {
            if (!pendingAssistant.segments) pendingAssistant.segments = []
            pendingAssistant.segments.push({
              type: 'text',
              id: Date.now() + i,
              content: msg.content
            })
          } else {
            displayMessages.push({
              id: Date.now() + i,
              role: 'assistant',
              content: msg.content,
              timestamp: new Date()
            })
          }
        }
      }
    }

    if (pendingAssistant) displayMessages.push(pendingAssistant)
    messages.value = displayMessages
    await scrollToBottom()
  } catch {
    messages.value = []
  }
}

// 初始化会话
const initSession = async () => {
  try {
    const agentInfo = await configApi.getAgentInfo()
    if (agentInfo.name) assistantName.value = agentInfo.name
  } catch {
    // 使用默认名字
  }

  const urlSession = route.query.session as string | undefined

  if (urlSession) {
    currentSessionId.value = urlSession
    saveCurrentSession(urlSession)
    await loadSessionHistory(urlSession)
    initializing.value = false
  } else {
    const lastSession = getLastSession()
    if (lastSession) {
      currentSessionId.value = lastSession
      saveCurrentSession(lastSession)
      await loadSessionHistory(lastSession)
      window.history.replaceState({}, '', `/?session=${lastSession}`)
      initializing.value = false
    } else {
      try {
        const res = await sessionApi.create()
        saveCurrentSession(res.session_id)
        currentSessionId.value = res.session_id
        window.history.replaceState({}, '', `/?session=${res.session_id}`)
        initializing.value = false
      } catch {
        message.error('创建会话失败')
        initializing.value = false
      }
    }
  }
}

// 监听路由变化
watch(
  () => route.query.session,
  async (newSession, oldSession) => {
    if (initializing.value || newSession === oldSession) return
    const sessionId = (newSession as string) || null
    if (!sessionId) return
    currentSessionId.value = sessionId
    saveCurrentSession(sessionId)
    inputMessage.value = ''
    await loadSessionHistory(sessionId)
  }
)

watch(
  () => route.query.refresh,
  async (newRefresh) => {
    if (newRefresh) {
      try {
        const agentInfo = await configApi.getAgentInfo()
        if (agentInfo.name) assistantName.value = agentInfo.name
      } catch { /* 忽略 */ }
      const currentQuery = { ...route.query }
      delete currentQuery.refresh
      router.replace({ query: currentQuery })
    }
  }
)

onMounted(async () => {
  await initSession()
})

// UI 操作
const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

const stopGeneration = () => {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
    loading.value = false
  }
}

const updateMessageSegments = (msgIndex: number, segments: MessageSegment[]) => {
  if (msgIndex >= 0 && msgIndex < messages.value.length) {
    const existingMsg = messages.value[msgIndex]!
    messages.value[msgIndex] = {
      id: existingMsg.id,
      role: existingMsg.role,
      content: existingMsg.content,
      timestamp: existingMsg.timestamp,
      segments: [...segments]
    }
  }
}

// 发送消息
const sendMessage = async () => {
  if (!inputMessage.value.trim()) return

  const userMessage = inputMessage.value
  const userMsg: Message = {
    id: Date.now(),
    role: 'user',
    content: userMessage,
    timestamp: new Date()
  }

  messages.value.push(userMsg)
  const userMsgIndex = messages.value.length - 1
  inputMessage.value = ''
  loading.value = true
  abortController.value = new AbortController()

  let assistantMsgIndex = -1
  let currentSegments: MessageSegment[] = []
  let currentTextSegmentId = -1

  await scrollToBottom()

  try {
    await chatApi.sendMessageStream(
      userMessage,
      currentSessionId.value || undefined,
      (event) => {
        if (event.type === 'session') {
          if (event.session_id) {
            currentSessionId.value = event.session_id
            saveCurrentSession(event.session_id)
          }
        } else if (event.type === 'step_start') {
          currentTextSegmentId = Date.now()
          currentSegments.push({ type: 'text', id: currentTextSegmentId, content: '' })
          if (assistantMsgIndex === -1) {
            assistantMsgIndex = messages.value.length
            messages.value.push({
              id: Date.now(), role: 'assistant', content: '',
              timestamp: new Date(), segments: currentSegments
            })
          } else {
            updateMessageSegments(assistantMsgIndex, currentSegments)
          }
          scrollToBottom()
        } else if (event.type === 'chunk' && event.content) {
          const textSegment = currentSegments.find(s => s.type === 'text' && s.id === currentTextSegmentId) as TextSegment | undefined
          if (textSegment) {
            textSegment.content += event.content
            updateMessageSegments(assistantMsgIndex, currentSegments)
          }
          scrollToBottom()
        } else if (event.type === 'tool_start') {
          currentSegments.push({
            type: 'tool', id: Date.now(),
            tool: event.tool || '', args: event.args || {}, status: 'running'
          })
          if (assistantMsgIndex === -1) {
            assistantMsgIndex = messages.value.length
            messages.value.push({
              id: Date.now(), role: 'assistant', content: '',
              timestamp: new Date(), segments: currentSegments
            })
          } else {
            updateMessageSegments(assistantMsgIndex, currentSegments)
          }
          scrollToBottom()
        } else if (event.type === 'tool_finish') {
          const lastToolSegment = [...currentSegments].reverse().find(s => s.type === 'tool' && s.status === 'running') as ToolSegment | undefined
          if (lastToolSegment) {
            lastToolSegment.result = event.result
            lastToolSegment.status = 'done'
          } else {
            currentSegments.push({
              type: 'tool', id: Date.now(),
              tool: event.tool || '', args: {}, result: event.result, status: 'done'
            })
          }
          updateMessageSegments(assistantMsgIndex, currentSegments)
          scrollToBottom()
        } else if (event.type === 'done') {
          if (event.session_id) currentSessionId.value = event.session_id
          configApi.getAgentInfo().then(agentInfo => {
            if (agentInfo.name) assistantName.value = agentInfo.name
          }).catch(() => {})
        } else if (event.type === 'error') {
          message.error(event.error || '发送消息失败')
        }
      },
      abortController.value.signal
    )
    await scrollToBottom()
  } catch (error: unknown) {
    if (error instanceof Error && error.name === 'AbortError') {
      console.log('用户取消了请求')
    } else {
      message.error('发送消息失败')
      if (assistantMsgIndex !== -1) {
        messages.value.splice(assistantMsgIndex, 1)
      }
      messages.value.splice(userMsgIndex, 1)
    }
  } finally {
    loading.value = false
    abortController.value = null
  }
}

const createNewSession = async () => {
  try {
    const res = await sessionApi.create()
    saveCurrentSession(res.session_id)
    router.push({ name: 'chat', query: { session: res.session_id } })
  } catch {
    message.error('新建会话失败')
  }
}
</script>

<template>
  <div class="chat-view">
    <div class="chat-messages" ref="messagesContainer">
      <!-- 初始化加载 -->
      <div v-if="initializing" class="empty-state">
        <img :src="ClawIcon" alt="TinyClaw" class="empty-icon loading" />
        <p class="empty-hint">加载中...</p>
      </div>

      <!-- 消息列表 -->
      <template v-else-if="messages.length > 0">
        <MessageGroup
          v-for="(group, groupIndex) in messageGroups"
          :key="groupIndex"
          :group="group"
          :assistant-name="assistantName"
          :loading="loading"
        />
      </template>

      <!-- 空状态 -->
      <div v-else class="empty-state">
        <img :src="ClawIcon" alt="TinyClaw" class="empty-icon" />
        <p class="empty-hint">发送消息开始对话</p>
      </div>

      <!-- 加载指示器 -->
      <div v-if="loading && shouldShowLoadingIndicator" class="message-group assistant loading-group">
        <div class="group-avatar">
          <img :src="ClawIcon" alt="TinyClaw" />
        </div>
        <div class="group-content">
          <div class="message-bubble">
            <div class="loading-dots">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="chat-input-wrapper">
      <div class="chat-input">
        <Input.TextArea
          v-model:value="inputMessage"
          placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
          :auto-size="{ minRows: 1, maxRows: 4 }"
          @press-enter="(e: KeyboardEvent) => { if (!e.shiftKey) { e.preventDefault(); sendMessage() } }"
        />
        <div class="input-actions">
          <Button class="icon-btn" @click="createNewSession" title="新建会话">
            <template #icon><PlusOutlined /></template>
          </Button>
          <button v-if="loading" class="stop-btn" @click="stopGeneration" title="停止生成">
            <div class="stop-icon"></div>
          </button>
          <button v-else-if="inputMessage.trim()" class="send-btn active" @click="sendMessage" title="发送消息">
            <SendOutlined />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  box-sizing: border-box;
  background-color: var(--color-background);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 空状态 */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.empty-icon {
  width: auto;
  height: 96px;
  opacity: 0.4;
}

.empty-icon.loading {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.25; transform: scale(0.96); }
  50% { opacity: 0.5; transform: scale(1); }
}

.empty-hint {
  color: var(--color-text-secondary);
  font-size: 14px;
  letter-spacing: 0.04em;
}

/* 加载指示器 */
.loading-group {
  display: flex;
  gap: 12px;
  max-width: 85%;
  align-self: flex-start;
}

.loading-group .group-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
}

.loading-group .group-avatar img {
  width: 36px;
  height: 36px;
  object-fit: contain;
  border-radius: 6px;
}

.loading-group .group-content {
  display: flex;
  flex-direction: column;
}

.loading-group .message-bubble {
  padding: 14px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.loading-dots {
  display: flex;
  gap: 5px;
  align-items: center;
}

.loading-dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: var(--color-primary);
  animation: loading-pulse 1.4s ease-in-out infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes loading-pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1); }
}

/* 输入区域 */
.chat-input-wrapper {
  padding: 14px 24px 28px;
  background-color: var(--color-surface);
  border-top: 1px solid var(--color-border);
}

.chat-input {
  display: flex;
  gap: 12px;
  align-items: center;
  max-width: 800px;
  margin: 0 auto;
}

.chat-input :deep(.ant-input) {
  flex: 1;
  border-radius: 20px;
  padding: 10px 18px;
  resize: none;
  border-color: var(--color-border);
  background: var(--color-background);
  transition: border-color 0.25s ease, box-shadow 0.25s ease;
}

.chat-input :deep(.ant-input:focus) {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-glow);
}

.input-actions {
  flex-shrink: 0;
  display: flex;
  gap: 10px;
  align-items: center;
  width: 92px;
}

.input-actions .icon-btn {
  width: 38px;
  height: 38px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  transition: all 0.2s ease;
}

.input-actions .icon-btn:hover {
  background: var(--color-primary-light);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.input-actions .send-btn {
  width: 38px;
  height: 38px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.25s ease;
  color: var(--color-text-secondary);
}

.input-actions .send-btn:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}

.input-actions .send-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
  box-shadow: 0 2px 8px rgba(212, 137, 156, 0.3);
}

.input-actions .send-btn.active:hover {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  box-shadow: 0 3px 12px rgba(212, 137, 156, 0.35);
}

.input-actions .stop-btn {
  width: 38px;
  height: 38px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: var(--color-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.25s ease;
  box-shadow: 0 2px 8px rgba(212, 137, 156, 0.3);
}

.input-actions .stop-btn:hover {
  background: var(--color-primary-hover);
}

.stop-icon {
  width: 13px;
  height: 13px;
  background: #fff;
  border-radius: 3px;
}
</style>
