<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown, formatTime } from '@/utils/markdown'
import { getToolConfig } from '@/utils/toolDisplay'
import ToolCard from './ToolCard.vue'
import ClawIcon from '@/assets/tinyclaw_logo.svg'

export interface TextSegment {
  type: 'text'
  id: number
  content: string
}

export interface ToolSegment {
  type: 'tool'
  id: number
  tool: string
  args: Record<string, unknown>
  result?: string
  status: 'running' | 'done' | 'error'
}

export type MessageSegment = TextSegment | ToolSegment

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  segments?: MessageSegment[]
}

export interface MessageGroup {
  role: 'user' | 'assistant'
  messages: Message[]
}

const props = defineProps<{
  group: MessageGroup
  assistantName: string
  loading: boolean
}>()

const hasVisibleContent = (msg: Message): boolean => {
  if (!msg.segments || msg.segments.length === 0) {
    return !!msg.content
  }
  for (const segment of msg.segments) {
    if (segment.type === 'text' && segment.content) return true
    if (segment.type === 'tool' && !getToolConfig(segment.tool).hidden) return true
  }
  return false
}

const hasTextContent = (msg: Message): boolean => {
  if (!msg.segments || msg.segments.length === 0) {
    return !!msg.content
  }
  for (const segment of msg.segments) {
    if (segment.type === 'text' && segment.content) return true
  }
  return false
}

const groupVisible = computed(() => {
  return props.group.role !== 'assistant' || props.group.messages.some(hasVisibleContent)
})

const hasToolWithoutText = computed(() => {
  if (props.group.role !== 'assistant') return false
  let hasTool = false
  let hasText = false
  for (const msg of props.group.messages) {
    if (!msg.segments) continue
    for (const segment of msg.segments) {
      if (segment.type === 'tool' && !getToolConfig(segment.tool).hidden) hasTool = true
      if (segment.type === 'text' && segment.content?.trim()) hasText = true
    }
  }
  return hasTool && !hasText
})

const isWaiting = computed(() => {
  if (props.group.role !== 'assistant' || !props.loading) return false
  return props.group.messages.every(msg => !hasTextContent(msg))
})

const lastTimestamp = computed(() => {
  const msgs = props.group.messages
  return msgs[msgs.length - 1]?.timestamp || new Date()
})
</script>

<template>
  <div v-show="groupVisible" :class="['message-group', group.role]">
    <!-- 头像 -->
    <div class="group-avatar">
      <img v-if="group.role === 'assistant'" :src="ClawIcon" alt="TinyClaw" />
      <div v-else class="user-avatar">你</div>
    </div>

    <!-- 消息内容 -->
    <div class="group-content">
      <template v-for="msg in group.messages" :key="msg.id">
        <!-- 有分段 -->
        <template v-if="msg.segments && msg.segments.length > 0">
          <template v-for="segment in msg.segments" :key="segment.id">
            <div v-if="segment.type === 'text' && segment.content" class="message-bubble">
              <div class="message-text" v-html="renderMarkdown(segment.content)"></div>
            </div>
            <ToolCard v-if="segment.type === 'tool'" :segment="segment as ToolSegment" />
          </template>
        </template>
        <!-- 无分段（历史消息） -->
        <div v-else-if="msg.content" class="message-bubble">
          <div class="message-text" v-html="renderMarkdown(msg.content)"></div>
        </div>
      </template>

      <!-- 等待状态（有工具但没有文本） -->
      <div v-if="loading && hasToolWithoutText" class="message-bubble">
        <div class="loading-dots">
          <span></span><span></span><span></span>
        </div>
      </div>

      <!-- 组底部 -->
      <div v-if="!isWaiting" class="group-footer">
        <span class="group-name">{{ group.role === 'user' ? '你' : assistantName }}</span>
        <span class="group-time">{{ formatTime(lastTimestamp) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-group {
  display: flex;
  gap: 12px;
  max-width: 82%;
}

.message-group.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.message-group.assistant {
  align-self: flex-start;
}

.group-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  margin-top: 2px;
}

.group-avatar img {
  width: 36px;
  height: 36px;
  object-fit: contain;
  border-radius: 6px;
  opacity: 0.9;
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background-color: var(--color-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.02em;
}

.group-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.message-bubble {
  display: inline-block;
  max-width: 100%;
}

.message-text {
  padding: 10px 16px;
  border-radius: var(--radius-lg);
  background-color: var(--color-surface);
  box-shadow: var(--shadow-sm);
  line-height: 1.7;
  word-wrap: break-word;
  border: 1px solid var(--color-border);
}

.message-group.user .message-text {
  background-color: var(--color-primary-light);
  border: 1px solid rgba(212, 137, 156, 0.18);
}

.message-text :deep(p) {
  margin: 0;
}

.message-text :deep(p + p) {
  margin-top: 8px;
}

.message-text :deep(code) {
  background-color: rgba(62, 58, 54, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', monospace;
}

.message-text :deep(pre) {
  background-color: #2D2A26;
  color: #E8E0D8;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: 10px 0;
  font-size: 13px;
}

.message-text :deep(pre code) {
  background-color: transparent;
  padding: 0;
  color: inherit;
}

.message-text :deep(ul),
.message-text :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}

.message-text :deep(blockquote) {
  border-left: 3px solid var(--color-primary);
  padding-left: 14px;
  margin: 10px 0;
  color: var(--color-text-secondary);
  font-style: italic;
}

.message-text :deep(a) {
  color: var(--color-primary);
  text-decoration: none;
  border-bottom: 1px solid rgba(212, 137, 156, 0.3);
  transition: border-color 0.2s ease;
}

.message-text :deep(a:hover) {
  border-bottom-color: var(--color-primary);
}

.group-footer {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 4px;
  padding-left: 4px;
}

.group-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  letter-spacing: 0.03em;
}

.group-time {
  font-size: 11px;
  color: var(--color-text-secondary);
  opacity: 0.7;
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

.loading-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.loading-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes loading-pulse {
  0%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
