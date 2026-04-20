<!-- AIMETA P=首页_应用首页|R=首页内容展示|NR=不含业务逻辑|E=route:/home#component:HomeView|X=ui|A=首页|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="platform-shell home-shell">
    <div class="platform-container page-enter">
      <header class="platform-topbar">
        <div class="platform-brand">
          <div class="platform-brand-mark">
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          <div>
            <h1 class="app-page-title">宝拓小说平台</h1>
            <p class="app-page-subtitle">创作入口页</p>
          </div>
        </div>
        <div class="home-top-actions">
          <button type="button" class="md-btn md-btn-text md-ripple" @click="goAbout">关于系统</button>
          <button type="button" class="md-btn md-btn-outlined md-ripple" @click="goSettings">系统设置</button>
        </div>
      </header>

      <section class="platform-hero-grid">
        <article class="platform-panel stagger-in" style="animation-delay: 30ms;">
          <p class="platform-kicker">Writer Dashboard</p>
          <h2 class="md-display-small home-title">面向长篇创作的工程化工作台</h2>
          <p class="md-body-large home-copy">
            将灵感、蓝图、章节与发布收敛在同一条创作链路中，提升持续写作效率。
          </p>
          <div class="home-hero-actions">
            <button type="button" class="md-btn md-btn-filled md-ripple" @click="handlePrimaryAction">
              {{ primaryActionText }}
            </button>
            <button type="button" class="md-btn md-btn-tonal md-ripple" @click="goInspiration">
              进入灵感模式
            </button>
          </div>
        </article>

        <aside class="platform-panel stagger-in" style="animation-delay: 90ms;">
          <h3 class="platform-section-title">快速入口</h3>
          <div class="home-command-list">
            <button type="button" class="platform-command home-command md-ripple" @click="goWorkspace">
              <p class="home-command-title">小说工作台</p>
              <p class="home-command-copy">管理项目、章节与版本迭代</p>
            </button>
            <button type="button" class="platform-command home-command md-ripple" @click="goAdmin">
              <p class="home-command-title">管理后台</p>
              <p class="home-command-copy">用户、策略与运行观测</p>
            </button>
          </div>
        </aside>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const primaryActionText = computed(() => (authStore.isAuthenticated ? '进入工作区' : '登录开始创作'))

const handlePrimaryAction = () => {
  router.push(authStore.isAuthenticated ? '/' : '/login')
}

const goWorkspace = () => {
  router.push('/workspace')
}

const goInspiration = () => {
  router.push('/inspiration')
}

const goAdmin = () => {
  router.push('/admin')
}

const goSettings = () => {
  router.push('/settings')
}

const goAbout = () => {
  router.push('/about')
}
</script>

<style scoped>
.home-shell {
  position: relative;
}

.home-top-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.home-title {
  margin-top: 10px;
}

.home-copy {
  margin-top: 14px;
  max-width: 700px;
  color: var(--md-on-surface-variant);
}

.home-hero-actions {
  margin-top: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.home-command-list {
  margin-top: 14px;
  display: grid;
  gap: 10px;
}

.home-command {
  min-height: 120px;
  text-align: left;
}

.home-command-title {
  margin: 0;
  font-size: var(--md-title-medium);
  color: var(--md-on-surface);
  font-weight: 650;
}

.home-command-copy {
  margin: 8px 0 0;
  font-size: var(--md-body-small);
  color: var(--md-on-surface-variant);
}

@media (max-width: 768px) {
  .home-top-actions {
    width: 100%;
  }
}
</style>
