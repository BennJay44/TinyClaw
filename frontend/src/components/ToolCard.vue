<script setup lang="ts">
import { ref } from 'vue'
import { Tag } from 'ant-design-vue'
import { LoadingOutlined } from '@ant-design/icons-vue'
import { getToolConfig, formatToolArgs, formatToolResult } from '@/utils/toolDisplay'

export interface ToolSegment {
  type: 'tool'
  id: number
  tool: string
  args: Record<string, unknown>
  result?: string
  status: 'running' | 'done' | 'error'
}

const props = defineProps<{
  segment: ToolSegment
}>()

const expanded = ref(false)

const toggle = () => {
  if (props.segment.status !== 'running') {
    expanded.value = !expanded.value
  }
}
</script>

<template>
  <div
    v-if="!getToolConfig(segment.tool).hidden"
    :class="['tool-card', segment.status]"
  >
    <div class="tool-header" @click="toggle">
      <span class="tool-icon">{{ getToolConfig(segment.tool).icon }}</span>
      <span class="tool-name">
        <template v-if="!expanded">使用了</template>
        {{ getToolConfig(segment.tool).name }}
      </span>
      <Tag v-if="segment.status === 'running'" color="processing" class="tool-tag">
        <LoadingOutlined /> 执行中
      </Tag>
      <Tag v-else-if="segment.status === 'done'" color="success" class="tool-tag">完成</Tag>
      <Tag v-else-if="segment.status === 'error'" color="error" class="tool-tag">失败</Tag>
      <span v-if="segment.status !== 'running'" class="collapse-indicator">
        {{ expanded ? '▼' : '▶' }}
      </span>
    </div>
    <div v-if="expanded" class="tool-details">
      <div v-if="segment.args && Object.keys(segment.args).length > 0" class="tool-args">
        <div class="tool-detail-label">入参</div>
        <pre class="tool-detail-content">{{ formatToolArgs(segment.args) }}</pre>
      </div>
      <div v-if="segment.result" class="tool-result-wrapper">
        <div class="tool-detail-label">结果</div>
        <pre class="tool-detail-content">{{ formatToolResult(segment.result) }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  font-size: 13px;
  transition: all 0.25s ease;
}

.tool-card.running {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
  box-shadow: 0 0 0 1px var(--color-primary-glow);
}

.tool-card.running .tool-icon,
.tool-card.running .tool-name {
  color: var(--color-primary);
}

.tool-card.done {
  border-color: var(--color-border);
  background: var(--color-surface);
}

.tool-card.error {
  border-color: #E8A0B2;
  background: rgba(212, 137, 156, 0.06);
}

.tool-card.error .tool-icon,
.tool-card.error .tool-name {
  color: var(--color-primary);
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.tool-header:hover {
  opacity: 0.85;
}

.tool-icon {
  font-size: 14px;
  line-height: 1;
}

.tool-name {
  font-weight: 500;
  color: var(--color-text);
  flex: 1;
}

.tool-tag {
  font-size: 11px;
  padding: 0 6px;
  line-height: 18px;
  border-radius: 4px;
}

.collapse-indicator {
  font-size: 10px;
  color: var(--color-text-secondary);
  margin-left: auto;
  transition: transform 0.2s ease;
}

.tool-details {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--color-border);
}

.tool-args,
.tool-result-wrapper {
  margin-bottom: 8px;
}

.tool-result-wrapper:last-child {
  margin-bottom: 0;
}

.tool-detail-label {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.tool-detail-content {
  margin: 0;
  padding: 10px 12px;
  background: rgba(62, 58, 54, 0.03);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--color-text);
  max-height: 150px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', monospace;
  line-height: 1.5;
}
</style>
