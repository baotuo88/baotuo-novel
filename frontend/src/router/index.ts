// AIMETA P=路由配置_所有页面路由定义|R=路由表_导航守卫_权限控制|NR=不含组件实现|E=router:index|X=internal|A=router实例|D=vue-router|S=none|RD=./README.ai
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const WorkspaceEntry = () => import('../views/WorkspaceEntry.vue')
const NovelWorkspace = () => import('../views/NovelWorkspace.vue')
const InspirationMode = () => import('../views/InspirationMode.vue')
const WritingDesk = () => import('../views/WritingDesk.vue')
const NovelDetail = () => import('../views/NovelDetail.vue')
const Login = () => import('../views/Login.vue')
const Register = () => import('../views/Register.vue')

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'workspace-entry',
      component: WorkspaceEntry,
      meta: { requiresAuth: true },
    },
    {
      path: '/workspace',
      name: 'novel-workspace',
      component: NovelWorkspace,
      meta: { requiresAuth: true },
    },
    {
      path: '/inspiration',
      name: 'inspiration-mode',
      component: InspirationMode,
      meta: { requiresAuth: true },
    },
    {
      path: '/detail/:id',
      name: 'novel-detail',
      component: NovelDetail,
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/novel/:id',
      name: 'writing-desk',
      component: WritingDesk,
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/login',
      name: 'login',
      component: Login,
    },
    {
      path: '/register',
      name: 'register',
      component: Register,
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../views/AdminView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/novel/:id',
      name: 'admin-novel-detail',
      component: () => import('../views/AdminNovelDetail.vue'),
      props: true,
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

const CHUNK_RELOAD_ONCE_KEY = 'baotuo_chunk_reload_once'

const isChunkLoadError = (error: unknown): boolean => {
  const message = String((error as { message?: string })?.message || error || '')
  const lowered = message.toLowerCase()
  return (
    lowered.includes('failed to fetch dynamically imported module') ||
    lowered.includes('importing a module script failed') ||
    lowered.includes('loading chunk') ||
    lowered.includes('chunkloaderror')
  )
}

router.onError((error, to) => {
  if (!isChunkLoadError(error)) {
    return
  }
  const alreadyReloaded = window.sessionStorage.getItem(CHUNK_RELOAD_ONCE_KEY) === '1'
  if (alreadyReloaded) {
    window.sessionStorage.removeItem(CHUNK_RELOAD_ONCE_KEY)
    console.error('动态资源加载失败且自动刷新未恢复，请手动清理浏览器缓存。', error)
    return
  }
  window.sessionStorage.setItem(CHUNK_RELOAD_ONCE_KEY, '1')
  window.location.replace(to?.fullPath || window.location.pathname)
})

router.afterEach(() => {
  if (window.sessionStorage.getItem(CHUNK_RELOAD_ONCE_KEY) === '1') {
    window.sessionStorage.removeItem(CHUNK_RELOAD_ONCE_KEY)
  }
})

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()
  
  // Attempt to fetch user info if token exists but user info is not loaded
  if (authStore.token && !authStore.user) {
    await authStore.fetchUser()
  }

  const requiresAuth = to.matched.some(record => record.meta.requiresAuth)
  const requiresAdmin = to.matched.some(record => record.meta.requiresAdmin)
  const isAuthenticated = authStore.isAuthenticated
  const isAdmin = authStore.user?.is_admin

  const mustChangePassword = authStore.user?.is_admin && authStore.mustChangePassword

  if (requiresAuth && !isAuthenticated) {
    next('/login')
  } else if (requiresAdmin && !isAdmin) {
    next('/') // Redirect to a non-admin page if not an admin
  } else if (isAuthenticated && mustChangePassword) {
    if (to.name !== 'admin' || to.query.tab !== 'password') {
      next({ name: 'admin', query: { tab: 'password' } })
    } else {
      next()
    }
  }
  else {
    next()
  }
})

export default router
