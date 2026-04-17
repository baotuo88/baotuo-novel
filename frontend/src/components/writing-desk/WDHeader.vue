<!-- AIMETA P=写作台头部_顶部导航栏|R=导航_操作按钮|NR=不含内容区域|E=component:WDHeader|X=ui|A=头部组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="md-top-app-bar md-elevation-1 flex-shrink-0 z-30 backdrop-blur-md">
    <div class="w-full px-4 sm:px-5 lg:px-6 xl:px-7 2xl:px-8">
      <div class="flex items-center justify-between h-16">
        <!-- 左侧：项目信息 -->
        <div class="flex items-center gap-2 sm:gap-4 min-w-0">
          <button @click="$emit('goBack')" class="md-icon-btn md-ripple flex-shrink-0">
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L4.414 9H17a1 1 0 110 2H4.414l5.293 5.293a1 1 0 010 1.414z" clip-rule="evenodd"></path>
            </svg>
          </button>
          <div class="min-w-0">
            <h1 class="md-title-large font-semibold truncate">{{ project?.title || '加载中...' }}</h1>
            <div class="hidden sm:flex items-center gap-2 md:gap-4 md-body-small md-on-surface-variant">
              <span>{{ project?.blueprint?.genre || '--' }}</span>
              <span class="hidden md:inline">•</span>
              <span class="hidden md:inline">{{ progress }}% 完成</span>
              <span class="hidden lg:inline">•</span>
              <span class="hidden lg:inline">{{ completedChapters }}/{{ totalChapters }} 章</span>
            </div>
          </div>
        </div>

        <!-- 右侧：操作按钮 -->
        <div class="flex items-center gap-1 sm:gap-2">
          <div
            v-if="showTaskSync"
            class="m3-task-sync-chip hidden md:flex"
            :class="taskSyncConnected ? 'is-ok' : 'is-warn'"
          >
            <span class="m3-task-sync-dot"></span>
            <span class="m3-task-sync-text">{{ taskSyncStatusText }}</span>
            <span class="m3-task-sync-detail hidden xl:inline">{{ taskSyncDetailText }}</span>
            <button
              v-if="showReconnectAction"
              class="md-btn md-btn-text md-ripple m3-task-sync-reconnect"
              :disabled="taskReconnectLoading"
              @click="$emit('reconnectTaskSync')"
            >
              {{ taskReconnectLoading ? '重连中...' : '重连' }}
            </button>
          </div>
          <button @click="$emit('openTaskCenter')" class="md-btn md-btn-text md-ripple flex items-center gap-2">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v2a1 1 0 102 0V6h12v8h-3a1 1 0 100 2h3a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm-1 9a3 3 0 016 0v4a3 3 0 11-6 0v-4zm2 0v4a1 1 0 102 0v-4a1 1 0 10-2 0z" clip-rule="evenodd"></path>
            </svg>
            <span class="hidden md:inline">任务中心</span>
          </button>
          <button @click="$emit('viewProjectDetail')" class="md-btn md-btn-text md-ripple flex items-center gap-2">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 12a2 2 0 100-4 2 2 0 000 4z"></path>
              <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd"></path>
            </svg>
            <span class="hidden md:inline">项目详情</span>
          </button>
          <div class="w-px h-6 hidden sm:block" style="background-color: var(--md-outline-variant);"></div>
          <button @click="handleLogout" class="md-btn md-btn-text md-ripple flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            <span class="hidden md:inline">退出登录</span>
          </button>
          <button
            @click="$emit('toggleSidebar')"
            class="md-icon-btn md-ripple lg:hidden"
          >
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clip-rule="evenodd"></path>
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { NovelProject } from '@/api/novel'

const router = useRouter()
const authStore = useAuthStore()

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}

interface Props {
  project: NovelProject | null
  progress: number
  completedChapters: number
  totalChapters: number
  showTaskSync: boolean
  taskSyncConnected: boolean
  taskSyncStatusText: string
  taskSyncDetailText: string
  taskReconnectLoading: boolean
  showReconnectAction: boolean
}

defineProps<Props>()

defineEmits([
  'goBack',
  'viewProjectDetail',
  'toggleSidebar',
  'openTaskCenter',
  'reconnectTaskSync',
])
</script>

<style scoped>
.m3-task-sync-chip {
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  padding: 5px 10px;
  border: 1px solid var(--md-outline-variant);
  background: color-mix(in srgb, var(--md-surface-container-low) 84%, white 16%);
  max-width: min(40vw, 420px);
}

.m3-task-sync-chip.is-ok {
  border-color: color-mix(in srgb, var(--md-success) 22%, var(--md-outline-variant) 78%);
}

.m3-task-sync-chip.is-warn {
  border-color: color-mix(in srgb, var(--md-warning) 26%, var(--md-outline-variant) 74%);
}

.m3-task-sync-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  flex-shrink: 0;
  background: var(--md-success);
}

.m3-task-sync-chip.is-warn .m3-task-sync-dot {
  background: var(--md-warning);
}

.m3-task-sync-text {
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}

.m3-task-sync-detail {
  font-size: 0.74rem;
  color: var(--md-on-surface-variant);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m3-task-sync-reconnect {
  min-height: auto;
  padding: 2px 6px;
  font-size: 0.72rem;
  line-height: 1.2;
}
</style>
