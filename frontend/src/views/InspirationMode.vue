<!-- AIMETA P=灵感模式_AI对话创作|R=对话创作界面|NR=不含写作台功能|E=route:/inspiration#component:InspirationMode|X=ui|A=对话界面|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="platform-shell inspiration-shell">
    <div class="inspiration-container page-enter">
      <section v-if="!conversationStarted" class="inspiration-entry md-card md-card-elevated fade-in">
        <div class="inspiration-entry-badge">灵感工坊</div>
        <h1 class="md-display-medium inspiration-entry-title">小说家的新篇章</h1>
        <p class="md-body-large inspiration-entry-copy">
          从一个想法开始，逐轮对话打磨世界观、人物和冲突结构，最后自动沉淀为可执行蓝图。
        </p>
        <div class="inspiration-entry-actions">
          <button
            @click="startConversation"
            :disabled="novelStore.isLoading"
            class="md-btn md-btn-filled md-ripple"
          >
            {{ novelStore.isLoading ? '正在准备...' : '开启灵感模式' }}
          </button>
          <button @click="goBack" class="md-btn md-btn-text md-ripple">返回入口</button>
        </div>
      </section>

      <section
        v-else-if="!showBlueprintConfirmation && !showBlueprint"
        class="inspiration-dialog md-card md-card-elevated fade-in"
      >
        <header class="inspiration-dialog-header">
          <div class="inspiration-dialog-status">
            <span class="inspiration-status-dot"></span>
            <span class="md-label-large">与“文思”协作中</span>
          </div>
          <div class="inspiration-dialog-actions">
            <span v-if="currentTurn > 0" class="md-chip md-chip-assist">第 {{ currentTurn }} 轮</span>
            <button @click="handleRestart" title="重新开始" class="md-icon-btn md-ripple">
              <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"></path>
              </svg>
            </button>
            <button @click="exitConversation" title="退出灵感模式" class="md-icon-btn md-ripple">
              <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </header>

        <div ref="chatArea" class="inspiration-chat-stream">
          <transition name="fade">
            <InspirationLoading v-if="isInitialLoading" />
          </transition>
          <ChatBubble
            v-for="(message, index) in chatMessages"
            :key="index"
            :message="message.content"
            :type="message.type"
          />
        </div>

        <footer class="inspiration-input-panel">
          <div class="inspiration-input-scroll">
            <ConversationInput
              :ui-control="currentUIControl"
              :loading="novelStore.isLoading"
              @submit="handleUserInput"
            />
          </div>
        </footer>
      </section>

      <section v-if="showBlueprintConfirmation" class="inspiration-stage fade-in">
        <BlueprintConfirmation
          :ai-message="confirmationMessage"
          @blueprint-generated="handleBlueprintGenerated"
          @back="backToConversation"
        />
      </section>

      <section v-if="showBlueprint" class="inspiration-stage fade-in">
        <BlueprintDisplay
          :blueprint="completedBlueprint"
          :ai-message="blueprintMessage"
          @confirm="handleConfirmBlueprint"
          @regenerate="handleRegenerateBlueprint"
        />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useNovelStore } from '@/stores/novel'
import type { UIControl, Blueprint } from '@/api/novel'
import ChatBubble from '@/components/ChatBubble.vue'
import ConversationInput from '@/components/ConversationInput.vue'
import BlueprintConfirmation from '@/components/BlueprintConfirmation.vue'
import BlueprintDisplay from '@/components/BlueprintDisplay.vue'
import InspirationLoading from '@/components/InspirationLoading.vue'
import { globalAlert } from '@/composables/useAlert'

interface ChatMessage {
  content: string
  type: 'user' | 'ai'
}

const router = useRouter()
const route = useRoute()
const novelStore = useNovelStore()

const conversationStarted = ref(false)
const isInitialLoading = ref(false)
const showBlueprintConfirmation = ref(false)
const showBlueprint = ref(false)
const chatMessages = ref<ChatMessage[]>([])
const currentUIControl = ref<UIControl | null>(null)
const currentTurn = ref(0)
const completedBlueprint = ref<Blueprint | null>(null)
const confirmationMessage = ref('')
const blueprintMessage = ref('')
const chatArea = ref<HTMLElement>()

const goBack = () => {
  router.push('/')
}

// 清空所有状态，开始新的灵感对话
const resetInspirationMode = () => {
  conversationStarted.value = false
  isInitialLoading.value = false
  showBlueprintConfirmation.value = false
  showBlueprint.value = false
  chatMessages.value = []
  currentUIControl.value = null
  currentTurn.value = 0
  completedBlueprint.value = null
  confirmationMessage.value = ''
  blueprintMessage.value = ''
  
  // 清空 store 中的当前项目和对话状态
  novelStore.setCurrentProject(null)
  novelStore.currentConversationState = {}
}

const exitConversation = async () => {
  const confirmed = await globalAlert.showConfirm('确定要退出灵感模式吗？当前进度可能会丢失。', '退出确认')
  if (confirmed) {
    resetInspirationMode()
    router.push('/')
  }
}

const handleRestart = async () => {
  const confirmed = await globalAlert.showConfirm('确定要重新开始吗？当前对话内容将会丢失。', '重新开始确认')
  if (confirmed) {
    await startConversation()
  }
}

const backToConversation = () => {
  showBlueprintConfirmation.value = false
}

const startConversation = async () => {
  // 重置所有状态，开始全新的对话
  resetInspirationMode()
  conversationStarted.value = true
  isInitialLoading.value = true
  
  try {
    await novelStore.createProject('未命名灵感', '开始灵感模式')
    
    // 发起第一次对话
    await handleUserInput(null)
  } catch (error) {
    console.error('启动灵感模式失败:', error)
    globalAlert.showError(`无法开始灵感模式: ${error instanceof Error ? error.message : '未知错误'}`, '启动失败')
    resetInspirationMode() // 失败时重置回初始状态
  }
}

const restoreConversation = async (projectId: string) => {
  try {
    await novelStore.loadProject(projectId)
    const project = novelStore.currentProject
    if (project && project.conversation_history) {
      conversationStarted.value = true
      chatMessages.value = project.conversation_history.map((item): ChatMessage | null => {
        if (item.role === 'user') {
          try {
            const userInput = JSON.parse(item.content)
            return { content: userInput.value, type: 'user' }
          } catch {
            return { content: item.content, type: 'user' }
          }
        } else { // assistant
          try {
            const assistantOutput = JSON.parse(item.content)
            return { content: assistantOutput.ai_message, type: 'ai' }
          } catch {
            return { content: item.content, type: 'ai' }
          }
        }
      }).filter((msg): msg is ChatMessage => msg !== null && msg.content !== null) // 过滤掉空的 user message

      const lastAssistantMsgStr = project.conversation_history.filter(m => m.role === 'assistant').pop()?.content
      if (lastAssistantMsgStr) {
        const lastAssistantMsg = JSON.parse(lastAssistantMsgStr)
        
        if (lastAssistantMsg.is_complete) {
          // 如果对话已完成，直接显示蓝图确认界面
          confirmationMessage.value = lastAssistantMsg.ai_message
          showBlueprintConfirmation.value = true
        } else {
          // 否则，恢复对话
          currentUIControl.value = lastAssistantMsg.ui_control
        }
      }
      // 计算当前轮次
      currentTurn.value = project.conversation_history.filter(m => m.role === 'assistant').length
      await scrollToBottom()
    }
  } catch (error) {
    console.error('恢复对话失败:', error)
    globalAlert.showError(`无法恢复对话: ${error instanceof Error ? error.message : '未知错误'}`, '加载失败')
    resetInspirationMode()
  }
}

const handleUserInput = async (userInput: any) => {
  try {
    // 如果有用户输入，添加到聊天记录
    if (userInput && userInput.value) {
      chatMessages.value.push({
        content: userInput.value,
        type: 'user'
      })
      await scrollToBottom()
    }

    const response = await novelStore.sendConversation(userInput)

    // 首次加载完成后，关闭加载动画
    if (isInitialLoading.value) {
      isInitialLoading.value = false
    }

    // 添加AI回复到聊天记录
    chatMessages.value.push({
      content: response.ai_message,
      type: 'ai'
    })
    currentTurn.value++

    await scrollToBottom()

    if (response.is_complete && response.ready_for_blueprint) {
      // 对话完成，显示蓝图确认界面
      confirmationMessage.value = response.ai_message
      showBlueprintConfirmation.value = true
    } else if (response.is_complete) {
      // 向后兼容：直接生成蓝图（如果后端还没更新）
      await handleGenerateBlueprint()
    } else {
      // 继续对话
      currentUIControl.value = response.ui_control
    }
  } catch (error) {
    console.error('对话失败:', error)
    // 确保在出错时也停止初始加载状态
    if (isInitialLoading.value) {
      isInitialLoading.value = false
    }
    globalAlert.showError(`抱歉，与AI连接时遇到问题: ${error instanceof Error ? error.message : '未知错误'}`, '通信失败')
    // 停止加载并返回初始界面
    resetInspirationMode()
  }
}

const handleGenerateBlueprint = async () => {
  try {
    const response = await novelStore.generateBlueprint()
    handleBlueprintGenerated(response)
  } catch (error) {
    console.error('生成蓝图失败:', error)
    globalAlert.showError(`生成蓝图失败: ${error instanceof Error ? error.message : '未知错误'}`, '生成失败')
  }
}

const handleBlueprintGenerated = (response: any) => {
  console.log('收到蓝图生成完成事件:', response)
  completedBlueprint.value = response.blueprint
  blueprintMessage.value = response.ai_message
  showBlueprintConfirmation.value = false
  showBlueprint.value = true
}

const handleRegenerateBlueprint = () => {
  showBlueprint.value = false
  showBlueprintConfirmation.value = true
}

const handleConfirmBlueprint = async () => {
  if (!completedBlueprint.value) {
    globalAlert.showError('蓝图数据缺失，请重新生成或稍后重试。', '保存失败')
    return
  }
  try {
    await novelStore.saveBlueprint(completedBlueprint.value)
    // 跳转到写作工作台
    if (novelStore.currentProject) {
      router.push(`/novel/${novelStore.currentProject.id}`)
    }
  } catch (error) {
    console.error('保存蓝图失败:', error)
    globalAlert.showError(`保存蓝图失败: ${error instanceof Error ? error.message : '未知错误'}`, '保存失败')
  }
}

const scrollToBottom = async () => {
  await nextTick()
  if (chatArea.value) {
    chatArea.value.scrollTop = chatArea.value.scrollHeight
  }
}

onMounted(() => {
  const projectId = route.query.project_id as string
  if (projectId) {
    restoreConversation(projectId)
  } else {
    // 每次进入灵感模式都重置状态，确保没有缓存
    resetInspirationMode()
  }
})
</script>

<style scoped>
.inspiration-shell {
  padding: clamp(12px, 2vw, 24px);
}

.inspiration-container {
  width: 100%;
  max-width: 1220px;
  margin: 0 auto;
}

.inspiration-entry {
  border-radius: calc(var(--md-radius-xl) + 2px);
  padding: clamp(22px, 4vw, 40px);
  text-align: center;
  background:
    radial-gradient(620px 220px at -8% -26%, color-mix(in srgb, var(--md-primary-container) 64%, transparent), transparent 74%),
    radial-gradient(520px 220px at 108% -20%, color-mix(in srgb, var(--md-secondary-container) 52%, transparent), transparent 74%),
    color-mix(in srgb, var(--md-surface) 93%, #ffffff 7%);
}

.inspiration-entry-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--md-primary-container) 76%, #ffffff 24%);
  border: 1px solid color-mix(in srgb, var(--md-primary) 22%, transparent);
  color: var(--md-on-primary-container);
  font-size: var(--md-label-medium);
  font-weight: 700;
}

.inspiration-entry-title {
  margin-top: 16px;
}

.inspiration-entry-copy {
  margin: 14px auto 24px;
  max-width: 760px;
  color: var(--md-on-surface-variant);
}

.inspiration-entry-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

.inspiration-dialog {
  height: min(92vh, 960px);
  height: min(92dvh, 960px);
  border-radius: calc(var(--md-radius-xl) + 2px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background:
    radial-gradient(540px 180px at -10% -32%, color-mix(in srgb, var(--md-primary-container) 44%, transparent), transparent 74%),
    color-mix(in srgb, var(--md-surface) 95%, #ffffff 5%);
}

.inspiration-dialog-header {
  height: 72px;
  border-bottom: 1px solid color-mix(in srgb, var(--md-outline-variant) 86%, transparent);
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
}

.inspiration-dialog-status {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--md-primary-dark);
}

.inspiration-status-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: var(--md-primary);
  box-shadow: 0 0 0 0 color-mix(in srgb, var(--md-primary) 46%, transparent);
  animation: inspiration-pulse 1.8s ease-out infinite;
}

.inspiration-dialog-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.inspiration-chat-stream {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: clamp(14px, 2vw, 24px);
  display: flex;
  flex-direction: column;
  gap: clamp(10px, 1.5vw, 16px);
}

.inspiration-input-panel {
  flex-shrink: 0;
  border-top: 1px solid color-mix(in srgb, var(--md-outline-variant) 86%, transparent);
  background: color-mix(in srgb, var(--md-surface-container-low) 78%, #ffffff 22%);
  padding: 12px;
  padding-bottom: max(12px, env(safe-area-inset-bottom));
}

.inspiration-input-scroll {
  max-height: min(42dvh, 340px);
  overflow-y: auto;
  padding-right: 4px;
}

.inspiration-stage {
  border-radius: calc(var(--md-radius-xl) + 2px);
  overflow: hidden;
  box-shadow: var(--md-elevation-3);
}

.inspiration-stage > :deep(div) {
  border-radius: calc(var(--md-radius-xl) + 2px);
  border: 1px solid color-mix(in srgb, var(--md-outline-variant) 84%, transparent);
  background:
    radial-gradient(520px 170px at -10% -30%, color-mix(in srgb, var(--md-primary-container) 46%, transparent), transparent 74%),
    radial-gradient(460px 160px at 108% -18%, color-mix(in srgb, var(--md-secondary-container) 38%, transparent), transparent 74%),
    color-mix(in srgb, var(--md-surface) 94%, #ffffff 6%);
}

@media (max-width: 768px) {
  .inspiration-shell {
    padding: 10px;
  }

  .inspiration-dialog {
    height: calc(100dvh - 20px);
  }

  .inspiration-dialog-header {
    padding: 0 12px;
  }

  .inspiration-dialog-status .md-label-large {
    font-size: var(--md-label-medium);
  }
}

/* vue transition name="fade" */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 220ms var(--md-easing-standard);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@keyframes inspiration-pulse {
  0% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--md-primary) 40%, transparent);
  }
  70% {
    box-shadow: 0 0 0 8px color-mix(in srgb, var(--md-primary) 0%, transparent);
  }
  100% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--md-primary) 0%, transparent);
  }
}
</style>
