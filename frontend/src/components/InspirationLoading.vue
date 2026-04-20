<!-- AIMETA P=灵感加载_加载动画组件|R=加载动画|NR=不含业务逻辑|E=component:InspirationLoading|X=internal|A=加载组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="inspiration-loading">
    <div class="inspiration-loading-mark">
      <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707m12.728 0l-.707-.707"></path>
      </svg>
    </div>
    <h2 class="inspiration-loading-title">正在为你准备灵感空间...</h2>
    <div class="inspiration-loading-steps">
      <p>连接创作模型与上下文</p>
      <p>整理已知设定与历史对话</p>
      <p>准备下一轮问题引导</p>
    </div>
  </div>
</template>

<script setup lang="ts">
// This is a purely presentational component.
</script>

<style scoped>
.inspiration-loading {
  position: absolute;
  inset: 0;
  z-index: 2;
  background: color-mix(in srgb, var(--md-surface) 90%, #ffffff 10%);
  backdrop-filter: blur(2px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px;
}

.inspiration-loading-mark {
  width: 78px;
  height: 78px;
  border-radius: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--md-on-primary);
  background: linear-gradient(135deg, var(--md-primary-light), var(--md-primary-dark));
  box-shadow: 0 12px 24px color-mix(in srgb, var(--md-primary) 24%, transparent);
  animation: loading-float 1.6s ease-in-out infinite;
}

.inspiration-loading-title {
  margin-top: 16px;
  margin-bottom: 10px;
  font-size: var(--md-headline-small);
  font-weight: 700;
  color: var(--md-on-surface);
}

.inspiration-loading-steps {
  display: flex;
  flex-direction: column;
  gap: 5px;
  color: var(--md-on-surface-variant);
  font-size: var(--md-body-medium);
}

.inspiration-loading-steps p {
  animation: loading-pulse 1.8s ease-in-out infinite;
}

.inspiration-loading-steps p:nth-child(2) {
  animation-delay: 0.2s;
}

.inspiration-loading-steps p:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes loading-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}

@keyframes loading-pulse {
  0%,
  100% {
    opacity: 0.45;
  }
  50% {
    opacity: 1;
  }
}
</style>
