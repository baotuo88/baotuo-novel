<!-- AIMETA P=工作区入口_应用主入口|R=入口导航|NR=不含具体功能|E=route:/#component:WorkspaceEntry|X=ui|A=入口页|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="platform-shell relative">
    <!-- Material 3 Update Log Modal -->
    <div v-if="showModal" class="md-dialog-overlay" @click.self="closeModal">
      <div class="md-dialog entry-log-dialog w-full max-w-4xl mx-4 max-h-[90vh] flex flex-col">
        <!-- Header -->
        <div class="md-dialog-header border-b" style="border-color: var(--md-outline-variant);">
          <h1 class="md-headline-medium text-center" style="color: var(--md-on-surface);">更新日志</h1>
        </div>
        
        <!-- Community Section -->
        <div v-if="communityLog" class="px-6 pt-6">
          <div class="p-4 rounded-lg entry-community-card" style="background-color: var(--md-primary-container);">
            <div class="prose max-w-none prose-sm" style="color: var(--md-on-primary-container);" v-html="renderMarkdown(communityLog.content)"></div>
          </div>
        </div>

        <!-- Timeline Content -->
        <div class="px-6 py-6 overflow-y-auto flex-1">
          <div class="flow-root">
            <ul role="list" class="-mb-8">
              <li v-for="(log, index) in pagedUpdateLogs" :key="log.id">
                <div class="relative pb-8">
                  <!-- Connector Line -->
                  <span 
                    v-if="index < pagedUpdateLogs.length - 1" 
                    class="absolute left-2.5 top-4 -ml-px h-full w-0.5" 
                    style="background-color: var(--md-outline-variant);"
                    aria-hidden="true"
                  ></span>
                  <div class="relative flex items-start space-x-4">
                    <!-- Timeline Dot -->
                    <div class="entry-timeline-dot"></div>
                    <!-- Card Content -->
                    <div class="min-w-0 flex-1">
                      <div class="md-card md-card-outlined p-4 entry-log-card">
                        <time class="md-label-large" style="color: var(--md-on-surface-variant);">
                          {{ new Date(log.created_at).toLocaleDateString() }}
                        </time>
                        <div class="mt-3 prose max-w-none prose-sm" style="color: var(--md-on-surface);" v-html="renderMarkdown(log.content)"></div>
                      </div>
                    </div>
                  </div>
                </div>
              </li>
            </ul>
          </div>

          <div v-if="timelinePageCount > 1" class="entry-log-pagination mt-4">
            <button
              class="md-btn md-btn-text md-ripple"
              :disabled="timelinePage <= 1"
              @click="timelinePage -= 1"
            >
              上一页
            </button>
            <span class="md-label-medium" style="color: var(--md-on-surface-variant);">
              第 {{ timelinePage }} / {{ timelinePageCount }} 页
            </span>
            <button
              class="md-btn md-btn-text md-ripple"
              :disabled="timelinePage >= timelinePageCount"
              @click="timelinePage += 1"
            >
              下一页
            </button>
          </div>
        </div>
        
        <!-- Footer Actions -->
        <div class="md-dialog-actions border-t" style="border-color: var(--md-outline-variant); background-color: var(--md-surface-container-low);">
          <button @click="hideModalToday" class="md-btn md-btn-text md-ripple">
            今日不再显示
          </button>
          <button @click="closeModal" class="md-btn md-btn-filled md-ripple">
            关闭
          </button>
        </div>
      </div>
    </div>

    <div class="platform-container page-enter">
      <header class="platform-topbar entry-topbar">
        <div class="platform-brand">
          <div class="platform-brand-mark">
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          <div>
            <p class="md-title-medium m-0" style="color: var(--md-on-surface);">宝拓小说平台</p>
            <div class="platform-topbar-meta">
              <span class="md-label-medium" style="color: var(--md-on-surface-variant);">{{ todayLabel }}</span>
              <span class="md-label-medium" style="color: var(--md-on-surface-variant);">{{ accountLabel }}</span>
            </div>
          </div>
        </div>
        <div class="platform-actions">
          <button @click="openModal" class="md-btn md-btn-text md-ripple">
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M7 8h10M7 12h10m-7 4h7M5 4h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2z" />
            </svg>
            更新日志
          </button>
          <router-link to="/settings" class="md-btn md-btn-text md-ripple">
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            设置
          </router-link>
          <button @click="handleLogout" class="md-btn md-btn-text md-ripple">
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            退出登录
          </button>
        </div>
      </header>

      <section class="platform-hero-grid">
        <article class="platform-panel stagger-in" style="animation-delay: 30ms;">
          <p class="platform-kicker mb-3">专业小说创作工作流</p>
          <h1 class="platform-section-title mb-4">创作控制台</h1>
          <p class="md-body-large mb-6" style="color: var(--md-on-surface-variant);">
            从灵感采集到章节交付，统一管理写作流程、蓝图构建与项目执行。
          </p>

          <div class="platform-topbar-meta mb-6">
            <span class="md-chip md-chip-assist">AI 引导灵感</span>
            <span class="md-chip md-chip-assist">蓝图驱动创作</span>
            <span class="md-chip md-chip-assist">项目状态追踪</span>
          </div>

          <div class="flex flex-wrap gap-3">
            <button @click="goToInspiration" class="md-btn md-btn-filled md-ripple">
              开启灵感模式
            </button>
            <button @click="goToWorkspace" class="md-btn md-btn-tonal md-ripple">
              进入工作台
            </button>
          </div>
        </article>

        <aside class="platform-panel stagger-in" style="animation-delay: 90ms;">
          <h2 class="platform-section-title mb-2">快速入口</h2>
          <p class="md-body-medium mb-5" style="color: var(--md-on-surface-variant);">根据当前阶段选择入口。</p>

          <div class="space-y-3">
            <button @click="goToInspiration" class="platform-command entry-command w-full text-left md-ripple">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <p class="md-title-medium m-0" style="color: var(--md-on-surface);">灵感模式</p>
                  <p class="md-body-small mt-1 mb-0" style="color: var(--md-on-surface-variant);">对话式创作引导，快速生成故事雏形</p>
                </div>
                <svg class="w-5 h-5 flex-shrink-0" style="color: var(--md-primary);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>
            <button @click="goToWorkspace" class="platform-command entry-command w-full text-left md-ripple">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <p class="md-title-medium m-0" style="color: var(--md-on-surface);">小说工作台</p>
                  <p class="md-body-small mt-1 mb-0" style="color: var(--md-on-surface-variant);">统一管理项目、章节进度与版本演进</p>
                </div>
                <svg class="w-5 h-5 flex-shrink-0" style="color: var(--md-success);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>
          </div>

          <div class="grid grid-cols-2 gap-3 mt-5">
            <MetricCard
              label="更新条目"
              :value="filteredUpdateLogs.length"
              hint="最近发布"
            />
            <MetricCard
              label="账号状态"
              :value="authStore.user?.is_admin ? 'Admin' : 'User'"
              :hint="authStore.user?.username || '未命名用户'"
            />
          </div>
        </aside>
      </section>
    </div>    
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { marked } from 'marked'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { getLatestUpdates } from '../api/updates'
import type { UpdateLog } from '../api/updates'
import MetricCard from '@/components/shared/MetricCard.vue'

marked.setOptions({
  gfm: true,
  breaks: true
})

const renderMarkdown = (md: string) => marked.parse(md)

const router = useRouter()
const authStore = useAuthStore()

const showModal = ref(false)
const updateLogs = ref<UpdateLog[]>([])
const timelinePage = ref(1)
const timelinePageSize = 6

const todayLabel = computed(() => {
  return `今日 ${new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(new Date())}`
})

const accountLabel = computed(() => {
  return authStore.user?.is_admin ? '管理员账号' : '创作者账号'
})

// 查找包含"交流群"的日志
const communityLog = computed(() => {
  return updateLogs.value.find(log => /交流群/.test(log.content))
})

// 过滤掉包含"交流群"的日志，用于时间线显示
const filteredUpdateLogs = computed(() => {
  if (!communityLog.value) {
    return updateLogs.value
  }
  return updateLogs.value.filter(log => log.id !== communityLog.value!.id)
})

const timelinePageCount = computed(() =>
  Math.max(1, Math.ceil(filteredUpdateLogs.value.length / timelinePageSize))
)

const pagedUpdateLogs = computed(() => {
  const start = (timelinePage.value - 1) * timelinePageSize
  return filteredUpdateLogs.value.slice(start, start + timelinePageSize)
})

onMounted(async () => {
  const hideUntil = localStorage.getItem('hideAnnouncement')
  if (hideUntil !== new Date().toDateString()) {
    try {
      updateLogs.value = await getLatestUpdates()
      if (updateLogs.value.length > 0) {
        timelinePage.value = 1
        showModal.value = true
      }
    } catch (error) {
      console.error('Failed to fetch update logs:', error)
    }
  }
})

const closeModal = () => {
  showModal.value = false
  timelinePage.value = 1
}

const openModal = async () => {
  if (updateLogs.value.length === 0) {
    try {
      updateLogs.value = await getLatestUpdates()
    } catch (error) {
      console.error('Failed to fetch update logs:', error)
    }
  }
  showModal.value = true
  timelinePage.value = 1
}

const hideModalToday = () => {
  localStorage.setItem('hideAnnouncement', new Date().toDateString())
  closeModal()
}

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}

const goToInspiration = () => {
  router.push('/inspiration')
}

const goToWorkspace = () => {
  router.push('/workspace')
}
</script>

<style scoped>
.entry-topbar {
  backdrop-filter: blur(14px);
}

.entry-log-dialog {
  border-radius: calc(var(--md-radius-xl) + 2px);
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 84%, transparent);
  background:
    radial-gradient(620px 180px at -12% -36%, color-mix(in srgb, var(--md-primary-container) 56%, transparent), transparent 70%),
    radial-gradient(420px 140px at 108% -18%, color-mix(in srgb, var(--md-secondary-container) 46%, transparent), transparent 70%),
    color-mix(in srgb, var(--md-surface) 95%, #ffffff 5%);
  box-shadow: var(--md-elevation-3);
}

.entry-community-card {
  border: 1px solid color-mix(in srgb, var(--md-primary) 18%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, #ffffff 70%, transparent);
}

.entry-timeline-dot {
  width: 20px;
  height: 20px;
  margin-top: 4px;
  border-radius: 50%;
  background: linear-gradient(145deg, var(--md-primary), color-mix(in srgb, var(--md-primary) 68%, #ffffff 32%));
  border: 4px solid color-mix(in srgb, var(--md-surface) 92%, #ffffff 8%);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--md-primary) 18%, transparent);
  flex-shrink: 0;
}

.entry-log-card {
  border-color: color-mix(in srgb, var(--md-outline-variant) 84%, transparent);
  background:
    linear-gradient(145deg, color-mix(in srgb, var(--md-surface) 90%, #ffffff 10%), color-mix(in srgb, var(--md-surface-container-low) 86%, #ffffff 14%));
}

.entry-command {
  min-height: 114px;
}

.entry-log-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .entry-log-dialog {
    margin-inline: 12px;
    max-height: calc(100vh - 24px);
  }
}
</style>
