<!-- AIMETA P=管理后台_管理员控制台|R=管理面板_子组件切换|NR=不含普通用户功能|E=route:/admin#component:AdminView|X=ui|A=管理面板|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="platform-shell admin-shell">
    <n-layout has-sider class="admin-layout page-enter">
      <n-layout-sider
        collapse-mode="width"
        :collapsed="collapsed"
        :collapsed-width="72"
        :width="260"
        bordered
        show-trigger
        @collapse="collapsed = true"
        @expand="collapsed = false"
      >
        <div class="sider-header">
          <div class="platform-brand-mark admin-mark" v-if="!collapsed">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          <span class="logo" v-if="!collapsed">宝拓小说 管理台</span>
          <span class="logo-small" v-else>管理</span>
        </div>

        <n-menu
          :value="activeKey"
          :options="menuOptions"
          :collapsed="collapsed"
          :collapsed-width="72"
          :accordion="true"
          @update:value="handleMenuSelect"
        />
      </n-layout-sider>

      <n-layout>
        <n-layout-header class="admin-header">
          <div class="admin-header-stack">
            <div class="admin-header-toolbar">
              <n-button
                class="mobile-trigger"
                quaternary
                circle
                size="small"
                @click="collapsed = !collapsed"
              >
                <template #icon>
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                </template>
              </n-button>
              <span class="admin-mobile-title">{{ currentMenuLabel }}</span>
            </div>

            <div class="admin-header-hero">
              <div class="admin-title-group">
                <p class="admin-title-eyebrow">管理员控制台</p>
                <h1 class="admin-title">{{ currentMenuLabel }}</h1>
                <p class="admin-title-subtitle">{{ currentMenuDescription }}</p>
                <div class="admin-meta-row">
                  <span class="md-chip md-chip-assist">模块 {{ menuOptions.length }}</span>
                  <span class="md-chip md-chip-assist">{{ currentDateLabel }}</span>
                </div>
              </div>

              <n-space class="admin-header-actions" :size="10">
                <n-button size="small" tertiary type="primary" @click="handleMenuSelect('statistics')">
                  返回总览
                </n-button>
                <n-button size="small" type="primary" ghost :disabled="mustChangePassword" @click="goBack">
                  {{ mustChangePassword ? '请先修改密码' : '返回业务系统' }}
                </n-button>
              </n-space>
            </div>

            <div class="admin-header-metrics">
              <MetricCard
                v-for="item in quickMetrics"
                :key="item.label"
                :label="item.label"
                :value="item.value"
                :hint="item.hint"
                compact
              />
            </div>
          </div>
        </n-layout-header>
        <n-layout-content class="admin-content">
          <n-scrollbar class="content-scroll">
            <div class="content-inner">
              <component :is="activeComponent" />
            </div>
          </n-scrollbar>
        </n-layout-content>
      </n-layout>
    </n-layout>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  NButton,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NLayoutSider,
  NMenu,
  NScrollbar,
  NSpace,
  type MenuOption
} from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import MetricCard from '@/components/shared/MetricCard.vue'
import { useAuthStore } from '@/stores/auth'

const collapsed = ref(false)
const activeKey = ref<MenuKey>('statistics')
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

type MenuKey =
  | 'statistics'
  | 'llm-observability'
  | 'users'
  | 'prompts'
  | 'novels'
  | 'logs'
  | 'settings'
  | 'password'

const components: Record<MenuKey, ReturnType<typeof defineAsyncComponent>> = {
  statistics: defineAsyncComponent(() => import('../components/admin/Statistics.vue')),
  'llm-observability': defineAsyncComponent(() => import('../components/admin/LLMObservability.vue')),
  users: defineAsyncComponent(() => import('../components/admin/UserManagement.vue')),
  prompts: defineAsyncComponent(() => import('../components/admin/PromptManagement.vue')),
  novels: defineAsyncComponent(() => import('../components/admin/NovelManagement.vue')),
  logs: defineAsyncComponent(() => import('../components/admin/UpdateLogManagement.vue')),
  settings: defineAsyncComponent(() => import('../components/admin/SettingsManagement.vue')),
  password: defineAsyncComponent(() => import('../components/admin/PasswordManagement.vue'))
}

const menuMeta: Record<MenuKey, { label: string; description: string }> = {
  statistics: { label: '数据总览', description: '聚合全站核心指标，快速掌握平台健康度。' },
  'llm-observability': { label: 'LLM观测', description: '追踪模型调用成本、错误分布与任务队列状态。' },
  users: { label: '用户管理', description: '管理用户生命周期、权限分配与账号状态。' },
  prompts: { label: '提示词管理', description: '维护生成策略模板，统一 AI 输出质量。' },
  novels: { label: '小说项目', description: '检视项目进度与创作状态，支持快速跳转详情。' },
  logs: { label: '更新日志', description: '发布运营公告与版本变更，保持团队信息同步。' },
  settings: { label: '系统配置', description: '调整系统参数与配额策略，保障平台稳定运行。' },
  password: { label: '安全中心', description: '强化管理员账户安全，定期更新认证凭据。' }
}

const menuOptions: MenuOption[] = [
  { key: 'statistics', label: menuMeta.statistics.label },
  { key: 'llm-observability', label: menuMeta['llm-observability'].label },
  { key: 'users', label: menuMeta.users.label },
  { key: 'prompts', label: menuMeta.prompts.label },
  { key: 'novels', label: menuMeta.novels.label },
  { key: 'logs', label: menuMeta.logs.label },
  { key: 'settings', label: menuMeta.settings.label },
  { key: 'password', label: menuMeta.password.label }
]

const isMenuKey = (key: string): key is MenuKey => key in components

const syncActiveKeyWithRoute = () => {
  const tab = route.query.tab
  if (typeof tab === 'string' && isMenuKey(tab)) {
    activeKey.value = tab
  }
}

const handleMenuSelect = (key: string) => {
  if (!isMenuKey(key)) {
    return
  }
  activeKey.value = key
  router.replace({ name: 'admin', query: { tab: key } })
}

const activeComponent = computed(() => components[activeKey.value])
const currentMenuLabel = computed(() => menuMeta[activeKey.value].label)
const currentMenuDescription = computed(() => menuMeta[activeKey.value].description)
const currentDateLabel = computed(() => {
  return new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
})
const quickMetrics = computed(() => [
  {
    label: '管理模块',
    value: menuOptions.length,
    hint: '覆盖运营、内容与系统配置'
  },
  {
    label: '当前模块',
    value: currentMenuLabel.value,
    hint: currentMenuDescription.value
  },
  {
    label: '导航状态',
    value: collapsed.value ? '折叠' : '展开',
    hint: collapsed.value ? '更适合移动端视图' : '桌面端全量菜单展示'
  }
])

const mustChangePassword = computed(() => Boolean(authStore.user?.is_admin && authStore.mustChangePassword))

const goBack = () => {
  if (mustChangePassword.value) {
    window.alert('请先在“安全中心”修改初始密码，然后再返回业务系统。')
    router.replace({ name: 'admin', query: { tab: 'password' } })
    return
  }
  router.push('/')
}

const updateCollapsedByWidth = () => {
  collapsed.value = window.innerWidth < 992
}

onMounted(() => {
  updateCollapsedByWidth()
  window.addEventListener('resize', updateCollapsedByWidth)
  syncActiveKeyWithRoute()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateCollapsedByWidth)
})

watch(
  () => route.query.tab,
  () => {
    syncActiveKeyWithRoute()
  }
)
</script>

<style scoped>
.admin-shell {
  padding: 16px;
}

.admin-layout {
  height: calc(100vh - 32px);
  height: calc(100dvh - 32px);
  border-radius: 26px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 82%, transparent);
  box-shadow: var(--md-elevation-3);
  background: color-mix(in srgb, var(--md-surface) 92%, #ffffff 8%);
}

.sider-header {
  height: 70px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0 18px;
  gap: 10px;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: var(--md-on-surface);
  border-bottom: 1px solid color-mix(in srgb, var(--md-outline-variant) 84%, transparent);
  background:
    radial-gradient(320px 120px at -12% -45%, color-mix(in srgb, var(--md-primary-container) 64%, transparent), transparent 74%),
    color-mix(in srgb, var(--md-surface) 95%, #ffffff 5%);
}

.admin-mark {
  width: 30px;
  height: 30px;
  border-radius: 9px;
}

.logo {
  font-size: 1rem;
  color: var(--md-on-surface);
}

.logo-small {
  font-size: 0.85rem;
  color: var(--md-on-surface);
}

.admin-header {
  background: transparent;
  border-bottom: none;
  padding: 16px 20px 0;
}

.admin-header-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.admin-header-toolbar {
  display: none;
  align-items: center;
  gap: 10px;
}

.admin-mobile-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--md-on-surface);
}

.admin-header-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px;
  border-radius: 22px;
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 82%, transparent);
  background:
    radial-gradient(680px 240px at -10% -20%, color-mix(in srgb, var(--md-primary-container) 76%, transparent), transparent 68%),
    radial-gradient(520px 220px at 108% -14%, color-mix(in srgb, var(--md-secondary-container) 64%, transparent), transparent 64%),
    color-mix(in srgb, var(--md-surface) 93%, #ffffff 7%);
  box-shadow: var(--md-elevation-2);
}

.admin-title-group {
  min-width: 0;
}

.admin-title-eyebrow {
  margin: 0;
  color: var(--md-primary);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.admin-title {
  margin: 8px 0 0;
  color: var(--md-on-surface);
  font-size: 1.45rem;
  font-weight: 700;
  line-height: 1.25;
}

.admin-title-subtitle {
  margin: 8px 0 0;
  color: var(--md-on-surface-variant);
  font-size: 0.92rem;
  line-height: 1.45;
}

.admin-meta-row {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.admin-header-actions {
  flex-shrink: 0;
  justify-content: flex-end;
}

.admin-header-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.admin-content {
  background:
    radial-gradient(640px 200px at 10% -10%, color-mix(in srgb, var(--md-primary-container) 48%, transparent), transparent 70%),
    linear-gradient(140deg, #f4f8ff 0%, #f7faff 54%, #eef7f4 100%);
  padding: 16px 20px 22px;
  display: flex;
  min-height: 0;
}

.content-scroll {
  flex: 1;
  min-height: 0;
  height: 100%;
  box-sizing: border-box;
}

.content-inner {
  padding-right: 4px;
}

.mobile-trigger {
  display: none;
}

:deep(.n-layout-sider) {
  background: color-mix(in srgb, var(--md-surface) 95%, #ffffff 5%);
  border-right: 1px solid color-mix(in srgb, var(--md-outline-variant) 84%, transparent);
}

:deep(.n-menu-item-content-header) {
  font-weight: 600;
}

:deep(.n-layout-sider-scroll-container) {
  padding: 8px;
}

:deep(.n-menu-item-content) {
  border-radius: 14px;
  border: 1px solid transparent;
}

:deep(.n-menu-item-content--selected) {
  border-color: color-mix(in srgb, var(--md-primary) 24%, var(--md-outline) 76%);
  background: color-mix(in srgb, var(--md-primary-container) 66%, #ffffff 34%);
  box-shadow: var(--md-elevation-1);
}

:deep(.admin-content .admin-card),
:deep(.admin-content .novel-management-card),
:deep(.admin-content .password-card),
:deep(.admin-content .admin-settings > .n-card) {
  border-radius: 18px;
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 82%, transparent);
  background: color-mix(in srgb, var(--md-surface) 95%, #ffffff 5%);
  box-shadow: var(--md-elevation-1);
}

:deep(.admin-content .card-header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

:deep(.admin-content .card-title) {
  color: var(--md-on-surface);
  font-size: 1.2rem;
  font-weight: 700;
}

:deep(.admin-content .n-data-table .n-data-table-th) {
  background: color-mix(in srgb, var(--md-surface-container-low) 92%, #ffffff 8%);
}

:deep(.admin-content .n-data-table .n-data-table-td) {
  background: transparent;
}

:deep(.admin-content .n-pagination-item) {
  border-radius: 10px;
}

:deep(.admin-content .n-data-table .n-data-table-tr:hover .n-data-table-td) {
  background: color-mix(in srgb, var(--md-primary-container) 24%, transparent);
}

:deep(.admin-content .n-alert) {
  border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 84%, transparent);
}

:deep(.admin-content .n-input .n-input-wrapper),
:deep(.admin-content .n-input-number .n-input-wrapper),
:deep(.admin-content .n-base-selection),
:deep(.admin-content .n-dynamic-tags .n-tag) {
  border-radius: 12px;
  border-color: color-mix(in srgb, var(--md-outline) 88%, transparent);
  background: color-mix(in srgb, var(--md-surface) 92%, #ffffff 8%);
}

:deep(.admin-content .n-input .n-input-wrapper:hover),
:deep(.admin-content .n-input-number .n-input-wrapper:hover),
:deep(.admin-content .n-base-selection:hover) {
  border-color: color-mix(in srgb, var(--md-primary) 26%, var(--md-outline) 74%);
}

:deep(.admin-content .n-input.n-input--focus .n-input-wrapper),
:deep(.admin-content .n-input-number.n-input-number--focus .n-input-wrapper),
:deep(.admin-content .n-base-selection.n-base-selection--active) {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--md-primary) 16%, transparent);
  border-color: color-mix(in srgb, var(--md-primary) 60%, white 40%);
}

:deep(.admin-content .n-button) {
  border-radius: 12px;
  font-weight: 600;
}

:deep(.admin-content .n-tag) {
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--md-outline) 72%, transparent);
}

:deep(.admin-content .admin-kpi-card) {
  border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 82%, transparent);
  background:
    linear-gradient(145deg, color-mix(in srgb, var(--md-primary-container) 34%, transparent), color-mix(in srgb, var(--md-surface) 92%, #ffffff 8%));
}

:deep(.admin-content .admin-kpi-label),
:deep(.admin-content .stat-label) {
  color: var(--md-on-surface-variant);
}

:deep(.admin-content .admin-kpi-value),
:deep(.admin-content .table-title),
:deep(.admin-content .mobile-card-title),
:deep(.admin-content .overview-title) {
  color: var(--md-on-surface);
}

:deep(.admin-content .overview-banner) {
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 82%, transparent);
  background:
    radial-gradient(520px 180px at -8% -30%, color-mix(in srgb, var(--md-primary-container) 60%, transparent), transparent 72%),
    radial-gradient(420px 160px at 108% -24%, color-mix(in srgb, var(--md-secondary-container) 56%, transparent), transparent 68%),
    color-mix(in srgb, var(--md-surface) 95%, #ffffff 5%);
}

:deep(.admin-content .overview-pill),
:deep(.admin-content .mobile-value),
:deep(.admin-content .table-owner),
:deep(.admin-content .table-progress),
:deep(.admin-content .table-date) {
  color: var(--md-on-surface);
}

:deep(.admin-content .overview-eyebrow),
:deep(.admin-content .admin-card-subtitle),
:deep(.admin-content .card-subtitle),
:deep(.admin-content .table-subtitle),
:deep(.admin-content .mobile-label) {
  color: var(--md-on-surface-variant);
}

:deep(.admin-content .log-card),
:deep(.admin-content .form-card),
:deep(.admin-content .novel-card) {
  border-radius: 16px;
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 84%, transparent);
  background: color-mix(in srgb, var(--md-surface) 95%, #ffffff 5%);
}

@media (max-width: 991px) {
  .admin-shell {
    padding: 12px;
  }

  .admin-layout {
    height: calc(100vh - 24px);
    height: calc(100dvh - 24px);
  }

  .admin-header {
    padding: 12px 14px 0;
  }

  .admin-header-toolbar {
    display: flex;
  }

  .admin-header-hero {
    padding: 16px;
    flex-direction: column;
  }

  .admin-header-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .admin-header-metrics {
    grid-template-columns: 1fr;
  }

  .admin-content {
    padding: 12px 14px 14px;
  }

  .content-scroll {
    height: 100%;
  }

  .mobile-trigger {
    display: inline-flex;
  }
}

@media (max-width: 767px) {
  .admin-title {
    font-size: 1.25rem;
  }

  .admin-title-subtitle {
    font-size: 0.88rem;
  }

  .content-scroll {
    height: 100%;
  }
}
</style>
