<!-- AIMETA P=设置页_用户设置|R=用户设置表单|NR=不含管理员设置|E=route:/settings#component:SettingsView|X=ui|A=设置表单|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="app-page-shell settings-shell">
    <div class="app-page-container page-enter">
      <header class="platform-topbar settings-topbar">
        <div class="platform-brand">
          <div class="platform-brand-mark">
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <div>
            <h1 class="app-page-title">系统设置</h1>
            <p class="app-page-subtitle">统一管理模型连接、额度与账单导出。</p>
          </div>
        </div>
        <router-link to="/" class="md-btn md-btn-outlined md-ripple">
          返回入口
        </router-link>
      </header>

      <section class="settings-layout">
        <aside class="settings-nav md-card md-card-outlined">
          <h2 class="md-title-medium settings-nav-title">设置导航</h2>
          <button type="button" class="settings-nav-item settings-nav-item-active">
            LLM 配置
          </button>
        </aside>

        <main class="settings-main">
          <LLMSettings />
        </main>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import LLMSettings from '@/components/LLMSettings.vue'
</script>

<style scoped>
.settings-shell {
  position: relative;
}

.settings-topbar {
  top: 10px;
}

.settings-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: clamp(12px, 1.6vw, 20px);
  min-height: calc(100dvh - 160px);
}

.settings-nav {
  align-self: start;
  position: sticky;
  top: 96px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.settings-nav-title {
  color: var(--md-on-surface);
  margin-bottom: 6px;
}

.settings-nav-item {
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: var(--md-on-surface-variant);
  text-align: left;
  padding: 9px 12px;
  font-size: var(--md-body-medium);
  font-weight: 600;
}

.settings-nav-item-active {
  border-color: color-mix(in srgb, var(--md-primary) 26%, var(--md-outline) 74%);
  background: color-mix(in srgb, var(--md-primary-container) 72%, #ffffff 28%);
  color: var(--md-on-primary-container);
}

.settings-main {
  min-width: 0;
}

@media (max-width: 1024px) {
  .settings-layout {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .settings-nav {
    position: static;
    top: auto;
  }
}
</style>
