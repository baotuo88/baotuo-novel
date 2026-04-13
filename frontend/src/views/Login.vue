<!-- AIMETA P=登录页_用户登录|R=登录表单_认证|NR=不含注册功能|E=route:/login#component:Login|X=ui|A=登录表单|D=vue|S=dom,net,storage|RD=./README.ai -->
<template>
  <div class="platform-shell auth-shell">
    <div class="auth-container page-enter">
      <section class="auth-brand-panel stagger-in" style="animation-delay: 20ms;">
        <div class="platform-brand-mark w-12 h-12">
          <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
        </div>
        <p class="md-label-large mb-3" style="color: var(--md-primary);">宝拓小说平台</p>
        <h1 class="md-display-small mb-3" style="color: var(--md-on-surface);">专业创作工作流</h1>
        <p class="md-body-large mb-8" style="color: var(--md-on-surface-variant);">
          统一完成灵感发散、蓝图构建、章节生成与内容管理。
        </p>

        <div class="auth-feature-grid">
          <div class="auth-feature-card">
            <p class="platform-stat-label">创作链路</p>
            <p class="platform-stat-value">端到端</p>
            <p class="platform-stat-hint">从构思到成稿一体化</p>
          </div>
          <div class="auth-feature-card">
            <p class="platform-stat-label">协作方式</p>
            <p class="platform-stat-value">AI 助手</p>
            <p class="platform-stat-hint">对话驱动高质量输出</p>
          </div>
        </div>
      </section>

      <section class="md-card md-card-elevated auth-form-panel stagger-in" style="border-radius: var(--md-radius-xl); animation-delay: 90ms;">
        <div class="mb-8">
          <TypewriterEffect text="宝拓小说" />
          <h2 class="md-headline-medium mt-4" style="color: var(--md-on-surface);">欢迎回来</h2>
          <p class="md-body-medium mt-2" style="color: var(--md-on-surface-variant);">登录后继续你的创作项目。</p>
        </div>

        <form @submit.prevent="handleLogin" class="space-y-5">
          <div class="md-text-field">
            <label for="username" class="md-text-field-label">用户名</label>
            <input
              v-model="username"
              id="username"
              name="username"
              type="text"
              required
              class="md-text-field-input"
              placeholder="请输入用户名"
            />
          </div>

          <div class="md-text-field">
            <label for="password" class="md-text-field-label">密码</label>
            <input
              v-model="password"
              id="password"
              name="password"
              type="password"
              required
              class="md-text-field-input"
              placeholder="请输入密码"
            />
          </div>

          <div class="flex justify-end">
            <button
              type="button"
              class="md-btn md-btn-text md-ripple px-2"
              @click="openForgotPasswordModal"
            >
              忘记密码？
            </button>
          </div>

          <div v-if="error" class="flex items-center gap-2 p-3 rounded-lg" style="background-color: var(--md-error-container);">
            <svg class="w-5 h-5 flex-shrink-0" style="color: var(--md-error);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span class="md-body-medium" style="color: var(--md-on-error-container);">{{ error }}</span>
          </div>

          <button
            type="submit"
            :disabled="isLoading"
            class="md-btn md-btn-filled md-ripple w-full h-12"
          >
            <svg v-if="isLoading" class="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span v-if="isLoading">正在登录...</span>
            <span v-else>登录</span>
          </button>
        </form>

        <div class="relative flex items-center justify-center my-7">
          <div class="w-full" style="height: 1px; background-color: var(--md-outline-variant);"></div>
          <span class="absolute px-4 md-body-small md-surface" style="color: var(--md-on-surface-variant);">或</span>
        </div>

        <div v-if="enableLinuxdoLogin">
          <a href="/api/auth/linuxdo/login" class="md-btn md-btn-outlined md-ripple w-full h-12">
            <svg class="w-5 h-5" aria-hidden="true" viewBox="0 0 496 512">
              <path fill="currentColor" d="M248 8C111 8 0 119 0 256s111 248 248 248 248-111 248-248S385 8 248 8zm0 448c-110.5 0-200-89.5-200-200S137.5 56 248 56s200 89.5 200 200-89.5 200-200 200z"></path>
            </svg>
            使用 Linux DO 登录
          </a>
        </div>

        <p v-if="allowRegistration" class="mt-7 text-center md-body-medium" style="color: var(--md-on-surface-variant);">
          还没有账户？
          <router-link to="/register" class="md-label-large" style="color: var(--md-primary);">立即注册</router-link>
        </p>
      </section>
    </div>

    <div v-if="showForgotPasswordModal" class="md-dialog-overlay" @click.self="closeForgotPasswordModal">
      <div class="md-dialog w-full max-w-lg">
        <div class="md-dialog-header">
          <h3 class="md-dialog-title">找回密码</h3>
          <p class="md-body-medium mt-2" style="color: var(--md-on-surface-variant);">输入注册邮箱并完成验证码验证后即可重置密码。</p>
        </div>

        <div class="md-dialog-content pb-4 space-y-4">
          <div class="md-text-field">
            <label for="resetEmail" class="md-text-field-label">邮箱</label>
            <input
              v-model="resetEmail"
              id="resetEmail"
              name="resetEmail"
              type="email"
              class="md-text-field-input"
              placeholder="请输入注册邮箱"
            />
          </div>

          <div>
            <label for="resetVerificationCode" class="md-text-field-label">验证码</label>
            <div class="flex gap-2 items-center mt-1">
              <input
                v-model="resetVerificationCode"
                id="resetVerificationCode"
                name="resetVerificationCode"
                type="text"
                class="md-text-field-input flex-1"
                placeholder="请输入验证码"
              />
              <button
                type="button"
                class="md-btn md-btn-tonal md-ripple whitespace-nowrap"
                :disabled="sendingResetCode || resetCountdown > 0"
                @click="sendResetCode"
              >
                <span v-if="sendingResetCode">发送中...</span>
                <span v-else>{{ resetCountdown > 0 ? `${resetCountdown}秒后重试` : '发送验证码' }}</span>
              </button>
            </div>
          </div>

          <div class="md-text-field">
            <label for="resetNewPassword" class="md-text-field-label">新密码</label>
            <input
              v-model="resetNewPassword"
              id="resetNewPassword"
              name="resetNewPassword"
              type="password"
              class="md-text-field-input"
              placeholder="至少 8 位"
            />
          </div>

          <div v-if="resetError" class="flex items-center gap-2 p-3 rounded-lg" style="background-color: var(--md-error-container);">
            <svg class="w-5 h-5 flex-shrink-0" style="color: var(--md-error);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span class="md-body-medium" style="color: var(--md-on-error-container);">{{ resetError }}</span>
          </div>

          <div v-if="resetSuccess" class="flex items-center gap-2 p-3 rounded-lg" style="background-color: var(--md-success-container);">
            <svg class="w-5 h-5 flex-shrink-0" style="color: var(--md-success);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <span class="md-body-medium" style="color: var(--md-on-success-container);">{{ resetSuccess }}</span>
          </div>
        </div>

        <div class="md-dialog-actions">
          <button type="button" class="md-btn md-btn-text md-ripple" @click="closeForgotPasswordModal">取消</button>
          <button
            type="button"
            class="md-btn md-btn-filled md-ripple"
            :disabled="resettingPassword"
            @click="submitResetPassword"
          >
            <span v-if="resettingPassword">重置中...</span>
            <span v-else>确认重置</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import TypewriterEffect from '@/components/TypewriterEffect.vue';

const username = ref('');
const password = ref('');
const error = ref('');
const isLoading = ref(false);
const showForgotPasswordModal = ref(false);
const resetEmail = ref('');
const resetVerificationCode = ref('');
const resetNewPassword = ref('');
const sendingResetCode = ref(false);
const resetCountdown = ref(0);
const resettingPassword = ref(false);
const resetError = ref('');
const resetSuccess = ref('');
const router = useRouter();
const authStore = useAuthStore();
const allowRegistration = computed(() => authStore.allowRegistration);
const enableLinuxdoLogin = computed(() => authStore.enableLinuxdoLogin);
let resetCountdownTimer: ReturnType<typeof setInterval> | null = null;

// 首屏自动拉取认证配置，确保登录页动态展示开关
onMounted(() => {
  authStore.fetchAuthOptions().catch((error) => {
    console.error('初始化认证配置失败', error);
  });
});

onBeforeUnmount(() => {
  clearResetCountdown();
});

const handleLogin = async () => {
  error.value = '';
  isLoading.value = true;
  try {
    const mustChange = await authStore.login(username.value, password.value);
    const user = authStore.user;
    if (user?.is_admin && (authStore.mustChangePassword || mustChange)) {
      router.push({ name: 'admin', query: { tab: 'password' } });
    } else {
      router.push('/');
    }
  } catch (err) {
    error.value = '登录失败，请检查您的用户名和密码。';
    console.error(err);
  } finally {
    isLoading.value = false;
  }
};

const clearResetCountdown = () => {
  if (resetCountdownTimer) {
    clearInterval(resetCountdownTimer);
    resetCountdownTimer = null;
  }
};

const openForgotPasswordModal = () => {
  showForgotPasswordModal.value = true;
  resetError.value = '';
  resetSuccess.value = '';
};

const closeForgotPasswordModal = () => {
  showForgotPasswordModal.value = false;
  sendingResetCode.value = false;
  resettingPassword.value = false;
  resetError.value = '';
  resetSuccess.value = '';
  clearResetCountdown();
  resetCountdown.value = 0;
};

const sendResetCode = async () => {
  resetError.value = '';
  resetSuccess.value = '';

  if (!resetEmail.value) {
    resetError.value = '请输入注册邮箱';
    return;
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(resetEmail.value)) {
    resetError.value = '邮箱格式不正确';
    return;
  }

  sendingResetCode.value = true;
  try {
    await authStore.forgotPassword(resetEmail.value);
    resetSuccess.value = '验证码已发送，请查收邮箱';
    resetCountdown.value = 60;
    clearResetCountdown();
    resetCountdownTimer = setInterval(() => {
      resetCountdown.value -= 1;
      if (resetCountdown.value <= 0) {
        clearResetCountdown();
      }
    }, 1000);
  } catch (err: any) {
    resetError.value = err.message || '发送验证码失败';
  } finally {
    sendingResetCode.value = false;
  }
};

const submitResetPassword = async () => {
  resetError.value = '';
  resetSuccess.value = '';

  if (!resetEmail.value || !resetVerificationCode.value || !resetNewPassword.value) {
    resetError.value = '请完整填写邮箱、验证码和新密码';
    return;
  }

  if (resetNewPassword.value.length < 8) {
    resetError.value = '新密码至少 8 位';
    return;
  }

  resettingPassword.value = true;
  try {
    await authStore.resetPassword({
      email: resetEmail.value,
      verification_code: resetVerificationCode.value,
      new_password: resetNewPassword.value,
    });
    resetSuccess.value = '密码重置成功，请使用新密码登录';
    setTimeout(() => {
      closeForgotPasswordModal();
    }, 1200);
  } catch (err: any) {
    resetError.value = err.message || '重置密码失败';
  } finally {
    resettingPassword.value = false;
  }
};
</script>
