<!-- AIMETA P=关于页_应用介绍页面|R=关于信息展示|NR=不含业务逻辑|E=route:/about#component:AboutView|X=ui|A=静态页面|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="platform-shell about-shell">
    <div class="platform-container page-enter">
      <header class="platform-topbar about-topbar">
        <div class="platform-brand">
          <div class="platform-brand-mark">
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 5h16v14H4z" />
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 9h8M8 13h8M8 17h5" />
            </svg>
          </div>
          <div>
            <h1 class="app-page-title">关于宝拓小说</h1>
            <p class="app-page-subtitle">统一创作链路，降低长篇小说工程化成本。</p>
          </div>
        </div>
        <button type="button" class="md-btn md-btn-outlined md-ripple" @click="goBack">
          返回入口
        </button>
      </header>

      <section class="platform-hero-grid">
        <article class="platform-panel about-hero stagger-in" style="animation-delay: 30ms;">
          <p class="platform-kicker">BaoTuo Novel Platform</p>
          <h2 class="md-display-small about-title">从灵感到交付的一体化创作工作流</h2>
          <p class="md-body-large about-copy">
            平台围绕“灵感生成 - 蓝图沉淀 - 章节生产 - 质量回路”构建结构化能力，
            让创作过程可追踪、可回滚、可复盘。
          </p>
          <div class="about-chip-row">
            <span class="md-chip md-chip-assist">蓝图驱动</span>
            <span class="md-chip md-chip-assist">章节自动化</span>
            <span class="md-chip md-chip-assist">质量闭环</span>
          </div>
          <div class="about-actions">
            <button type="button" class="md-btn md-btn-filled md-ripple" @click="goWorkspace">
              进入工作台
            </button>
            <button type="button" class="md-btn md-btn-tonal md-ripple" @click="goInspiration">
              开启灵感模式
            </button>
          </div>
        </article>

        <aside class="platform-panel about-principles stagger-in" style="animation-delay: 90ms;">
          <h3 class="platform-section-title">设计原则</h3>
          <ul class="about-principle-list">
            <li>
              <p class="about-principle-title">结构优先</p>
              <p class="about-principle-copy">先建立故事骨架，再展开章节细节，避免后期返工。</p>
            </li>
            <li>
              <p class="about-principle-title">过程可控</p>
              <p class="about-principle-copy">关键操作可追踪、可回滚，支持多人协作校验。</p>
            </li>
            <li>
              <p class="about-principle-title">结果可交付</p>
              <p class="about-principle-copy">发布中心统一导出格式，降低收尾与交付成本。</p>
            </li>
          </ul>
        </aside>
      </section>

      <section class="about-metrics stagger-in" style="animation-delay: 150ms;">
        <MetricCard label="工作流阶段" value="4" hint="灵感 / 蓝图 / 章节 / 发布" />
        <MetricCard label="核心模块" value="12+" hint="覆盖人物、世界观、时间线等" />
        <MetricCard label="管理方式" value="项目化" hint="全链路状态可视化" />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import MetricCard from '@/components/shared/MetricCard.vue'

const router = useRouter()

const goBack = () => {
  router.push('/')
}

const goWorkspace = () => {
  router.push('/workspace')
}

const goInspiration = () => {
  router.push('/inspiration')
}
</script>

<style scoped>
.about-shell {
  position: relative;
}

.about-topbar {
  top: 10px;
}

.about-hero {
  min-height: 100%;
}

.about-title {
  margin-top: 10px;
}

.about-copy {
  margin-top: 14px;
  max-width: 720px;
  color: var(--md-on-surface-variant);
}

.about-chip-row {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.about-actions {
  margin-top: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.about-principles {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.about-principle-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.about-principle-list li {
  border-radius: var(--md-radius-md);
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 82%, transparent);
  background: color-mix(in srgb, var(--md-surface) 92%, #ffffff 8%);
  padding: 12px 14px;
}

.about-principle-title {
  margin: 0;
  font-size: var(--md-title-medium);
  color: var(--md-on-surface);
  font-weight: 650;
}

.about-principle-copy {
  margin: 6px 0 0;
  font-size: var(--md-body-small);
  color: var(--md-on-surface-variant);
}

.about-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 900px) {
  .about-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
