<!-- AIMETA P=注册页_用户注册|R=注册表单|NR=不含登录功能|E=route:/register#component:Register|X=ui|A=注册表单|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="platform-shell auth-shell">
    <div class="auth-container page-enter">
      <section class="auth-brand-panel stagger-in" style="animation-delay: 20ms;">
        <div class="platform-brand-mark w-12 h-12">
          <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
        </div>
        <p class="md-label-large mb-3" style="color: var(--md-primary);">创作者入驻</p>
        <h1 class="md-display-small mb-3" style="color: var(--md-on-surface);">建立你的创作空间</h1>
        <p class="md-body-large mb-8" style="color: var(--md-on-surface-variant);">
          注册后即可使用灵感模式、蓝图生成和章节协作能力。
        </p>

        <div class="auth-feature-grid">
          <div class="auth-feature-card">
            <p class="platform-stat-label">创作引擎</p>
            <p class="platform-stat-value">AI 驱动</p>
            <p class="platform-stat-hint">对话生成与结构化蓝图</p>
          </div>
          <div class="auth-feature-card">
            <p class="platform-stat-label">管理方式</p>
            <p class="platform-stat-value">项目化</p>
            <p class="platform-stat-hint">工程式管理每本小说</p>
          </div>
        </div>
      </section>

      <section v-if="allowRegistration" class="md-card md-card-elevated auth-form-panel stagger-in" style="border-radius: var(--md-radius-xl); animation-delay: 90ms;">
        <h2 class="md-headline-medium" style="color: var(--md-on-surface);">注册账号</h2>
        <p class="md-body-medium mt-2 mb-6" style="color: var(--md-on-surface-variant);">创建账号并开始你的第一部作品。</p>

        <form @submit.prevent="handleRegister" class="space-y-4">
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
            <label for="email" class="md-text-field-label">邮箱</label>
            <input
              v-model="email"
              id="email"
              name="email"
              type="email"
              required
              class="md-text-field-input"
              placeholder="请输入邮箱"
            />
          </div>

          <div>
            <label for="verificationCode" class="md-text-field-label">验证码</label>
            <div class="flex gap-2 items-center mt-1">
              <input
                v-model="verificationCode"
                id="verificationCode"
                name="verificationCode"
                type="text"
                required
                class="md-text-field-input flex-1"
                placeholder="请输入验证码"
              />
              <button
                type="button"
                @click="sendCode"
                :disabled="countdown > 0 || sending"
                class="md-btn md-btn-tonal md-ripple whitespace-nowrap"
              >
                <span v-if="sending">发送中...</span>
                <span v-else>{{ countdown > 0 ? countdown + '秒后重试' : '发送验证码' }}</span>
              </button>
            </div>
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
              placeholder="至少 8 位"
            />
          </div>

          <div v-if="error" class="flex items-center gap-2 p-3 rounded-lg" style="background-color: var(--md-error-container);">
            <svg class="w-5 h-5 flex-shrink-0" style="color: var(--md-error);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span class="md-body-medium" style="color: var(--md-on-error-container);">{{ error }}</span>
          </div>

          <div v-if="success" class="flex items-center gap-2 p-3 rounded-lg" style="background-color: var(--md-success-container);">
            <svg class="w-5 h-5 flex-shrink-0" style="color: var(--md-success);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <span class="md-body-medium" style="color: var(--md-on-success-container);">{{ success }}</span>
          </div>

          <button type="submit" class="md-btn md-btn-filled md-ripple w-full h-12">注册</button>
        </form>

        <p class="mt-7 text-center md-body-medium" style="color: var(--md-on-surface-variant);">
          已有账户？
          <router-link to="/login" class="md-label-large" style="color: var(--md-primary);">立即登录</router-link>
        </p>
      </section>

      <section v-else class="md-card md-card-elevated auth-form-panel stagger-in" style="border-radius: var(--md-radius-xl); animation-delay: 90ms;">
        <h2 class="md-headline-small" style="color: var(--md-on-surface);">暂未开放注册</h2>
        <p class="md-body-medium mt-3" style="color: var(--md-on-surface-variant);">请联系管理员或稍后再试。</p>
        <router-link to="/login" class="md-btn md-btn-tonal md-ripple mt-6 inline-flex">返回登录</router-link>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const username = ref('');
const email = ref('');
const verificationCode = ref('');
const password = ref('');
const countdown = ref(0);
const sending = ref(false);
const error = ref('');
const success = ref('');
const router = useRouter();
const authStore = useAuthStore();
const allowRegistration = computed(() => authStore.allowRegistration);

// 进入页面即拉取认证开关，避免展示无效注册表单
onMounted(async () => {
  try {
    await authStore.fetchAuthOptions();
  } catch (error) {
    console.error('加载认证开关失败', error);
  }
  if (!allowRegistration.value) {
    success.value = '';
    error.value = '当前已关闭注册，请稍后再试。';
  }
});

const validateInput = () => {
  // Password validation
  if (password.value.length < 8) {
    return '密码必须至少8个字符';
  }

  // Username validation
  const usernameVal = username.value;
  const hasChinese = /[\u4e00-\u9fa5]/.test(usernameVal);
  const isNumeric = /^\d+$/.test(usernameVal);
  const isAlphanumeric = /^[a-zA-Z0-9]+$/.test(usernameVal);

  if (isNumeric) {
    return '用户名不能是纯数字';
  }

  if (hasChinese && usernameVal.length <= 1) {
    return '户名长度必须大于2个汉字';
  }

  if (isAlphanumeric && !hasChinese && usernameVal.length <= 6) {
    return '用户名长度必须大于6个字母或数字';
  }

  return null; // No validation errors
};

const sendCode = async () => {
  error.value = '';
  success.value = '';

  if (!allowRegistration.value) {
    error.value = '当前已关闭注册，请联系管理员。';
    return;
  }

  if (!email.value) {
    error.value = '请输入邮箱';
    return;
  }
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email.value)) {
    error.value = '邮箱格式不正确';
    return;
  }

  sending.value = true;
  try {
    const res = await fetch(`/api/auth/send-code?email=${encodeURIComponent(email.value)}`, {
      method: 'POST'
    });
    if (!res.ok) {
      const errMsg = await res.json();
      throw new Error(errMsg.detail || '发送验证码失败');
    }
    success.value = '验证码已发送，请查收邮箱';
    // 等接口返回成功后再开始倒计时
    countdown.value = 60;
    const timer = setInterval(() => {
      countdown.value--;
      if (countdown.value <= 0) clearInterval(timer);
    }, 1000);
  } catch (err: any) {
    error.value = err.message;
  } finally {
    sending.value = false;
  }
};

const handleRegister = async () => {
  error.value = '';
  success.value = '';

  const validationError = validateInput();
  if (validationError) {
    error.value = validationError;
    return;
  }

  if (!allowRegistration.value) {
    error.value = '当前已关闭注册，请联系管理员。';
    return;
  }

  try {
    const res = await fetch('/api/auth/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value,
        email: email.value,
        password: password.value,
        verification_code: verificationCode.value
      })
    });
    if (!res.ok) {
      const errMsg = await res.json();
      throw new Error(errMsg.detail || '注册失败');
    }
    success.value = '注册成功！正在跳转到登录页面...';
    setTimeout(() => {
      router.push('/login');
    }, 2000);
  } catch (err: any) {
    error.value = err.message || '注册失败，请稍后再试。';
    console.error(err);
  }
};
</script>
