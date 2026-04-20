<!-- AIMETA P=关于页_应用介绍页面|R=关于信息展示|NR=不含业务逻辑|E=route:/about#component:AboutView|X=ui|A=静态页面|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="platform-shell about-shell">
    <div class="platform-container page-enter">
      <section class="platform-panel about-panel">
        <p class="platform-kicker">BaoTuo Novel</p>
        <h1 class="md-display-small about-title">创作系统简介</h1>
        <p class="md-body-large about-copy">
          宝拓小说平台围绕“灵感生成 - 蓝图沉淀 - 章节生产 - 质量回路”构建统一创作工作流，
          支持从灵感到发布的全流程协作。
        </p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.about-shell {
  display: flex;
  align-items: center;
}

.about-panel {
  max-width: 760px;
  margin: 0 auto;
}

.about-title {
  margin-top: 10px;
}

.about-copy {
  margin-top: 14px;
  color: var(--md-on-surface-variant);
}
</style>
