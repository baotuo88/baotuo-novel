import type { WriterTaskCenterItem, WriterTaskRetryPayload } from '@/api/novel'

export interface TaskRecoveryAction {
  key: string
  label: string
  description: string
  payload?: WriterTaskRetryPayload
  requiresConfirm?: boolean
}

export interface TaskRecoveryPlan {
  summary: string
  actions: TaskRecoveryAction[]
}

export const buildTaskRecoveryPlan = (item: WriterTaskCenterItem): TaskRecoveryPlan => {
  const category = String(item.failure_category || '').trim().toLowerCase()

  if (item.consistency_guard_status === 'review_required') {
    return {
      summary: '一致性守护要求人工确认，建议带上明确的修订说明再重试，避免重复生成相同问题。',
      actions: [
        {
          key: 'consistency_retry',
          label: '带修订重试',
          description: '提示模型优先遵守既有设定、术语与时间线。',
          payload: {
            force: true,
            resume_from_checkpoint: true,
            writing_notes: '请优先修复与既有设定、术语词典、时间线和伏笔状态冲突的内容，再继续生成。',
          },
        },
      ],
    }
  }

  if (category === 'config' || category === 'auth') {
    return {
      summary: '这类失败通常来自模型配置、鉴权或环境变量。建议先修正配置，再回到当前章节重新提交。',
      actions: [
        {
          key: 'retry_after_fix',
          label: '修正后重试',
          description: '修正配置后，基于现有章节重新发起任务。',
          payload: {
            force: true,
            resume_from_checkpoint: false,
            writing_notes: '配置已修正，请从当前章节状态重新生成并校验依赖配置。',
          },
        },
      ],
    }
  }

  if (category === 'rate_limit' || category === 'network' || category === 'upstream') {
    return {
      summary: '这类失败多半是暂时性问题，优先复用已有检查点并稍后重试，不建议立刻清空上下文。',
      actions: [
        {
          key: 'resume_retry',
          label: '继续重试',
          description: '尽量复用已生成内容和检查点。',
          payload: {
            force: true,
            resume_from_checkpoint: true,
          },
        },
        {
          key: 'fresh_retry',
          label: '全量重试',
          description: '放弃旧检查点，完整重新生成一次。',
          payload: {
            force: true,
            resume_from_checkpoint: false,
          },
          requiresConfirm: true,
        },
      ],
    }
  }

  if (category === 'timeout' || category === 'stale') {
    return {
      summary: '任务可能卡住或执行超时，优先强制拉起一次继续重试；若仍失败，再改用全量重试。',
      actions: [
        {
          key: 'force_resume',
          label: '强制继续',
          description: '强制取消旧任务并继续复用检查点。',
          payload: {
            force: true,
            resume_from_checkpoint: true,
          },
          requiresConfirm: true,
        },
        {
          key: 'force_fresh',
          label: '强制重跑',
          description: '完全放弃旧检查点，重新拉起任务。',
          payload: {
            force: true,
            resume_from_checkpoint: false,
          },
          requiresConfirm: true,
        },
      ],
    }
  }

  return {
    summary: '建议先定位章节确认上下文，再执行标准重试；若多次失败，可改用强制重试。',
    actions: [
      {
        key: 'default_retry',
        label: '标准重试',
        description: '默认复用检查点继续执行。',
        payload: {
          force: true,
          resume_from_checkpoint: true,
        },
      },
    ],
  }
}
