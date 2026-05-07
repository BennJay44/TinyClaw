<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { Menu, ConfigProvider } from 'ant-design-vue'
import { MessageOutlined, SettingOutlined, HistoryOutlined, BookOutlined } from '@ant-design/icons-vue'
import ClawIcon from '@/assets/tinyclaw_logo.svg'

const route = useRoute()

// 和風主题配置
const customTheme = {
  token: {
    colorPrimary: '#D4899C',
    colorPrimaryHover: '#E8A0B2',
    colorPrimaryActive: '#C07888',
    colorPrimaryBg: 'rgba(212, 137, 156, 0.08)',
    colorPrimaryBgHover: 'rgba(212, 137, 156, 0.14)',
    borderRadius: 6,
    fontFamily: "'Noto Sans SC', 'PingFang SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
}
</script>

<template>
  <ConfigProvider :theme="{ token: customTheme.token }">
    <div class="app-container">
      <aside class="sidebar">
        <div class="logo">
          <img :src="ClawIcon" alt="TinyClaw" class="logo-icon" />
          <span class="logo-text">TinyClaw</span>
        </div>
        <Menu
          mode="inline"
          :selected-keys="[route.name as string]"
          class="sidebar-menu"
        >
          <Menu.Item key="chat">
            <RouterLink to="/">
              <MessageOutlined />
              <span>聊天</span>
            </RouterLink>
          </Menu.Item>
          <Menu.Item key="sessions">
            <RouterLink to="/sessions">
              <HistoryOutlined />
              <span>会话</span>
            </RouterLink>
          </Menu.Item>
          <Menu.Item key="memory">
            <RouterLink to="/memory">
              <BookOutlined />
              <span>记忆</span>
            </RouterLink>
          </Menu.Item>
          <Menu.Item key="config">
            <RouterLink to="/config">
              <SettingOutlined />
              <span>配置</span>
            </RouterLink>
          </Menu.Item>
        </Menu>
      </aside>

      <main class="main-content">
        <RouterView />
      </main>
    </div>
  </ConfigProvider>
</template>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  width: 220px;
  background-color: var(--color-surface);
  border-right: 1px solid var(--color-border);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}

.logo {
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--color-border);
}

.logo-icon {
  width: auto;
  height: 34px;
  opacity: 0.88;
}

.logo-text {
  font-size: 17px;
  font-weight: 600;
  color: var(--color-text);
  letter-spacing: 0.02em;
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  padding-top: 8px;
  background: transparent;
}

.sidebar-menu :deep(.ant-menu-item) {
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  margin: 2px 8px 2px 0;
  transition: all 0.2s ease;
}

.main-content {
  flex: 1;
  background-color: var(--color-background);
  overflow: auto;
  height: 100vh;
}
</style>
