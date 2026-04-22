import { describe, expect, it } from 'vitest'

import type { WriterTaskCenterItem } from '@/api/novel'
import { buildTaskRecoveryPlan } from '@/components/writing-desk/taskRecovery'

const createTask = (partial: Partial<WriterTaskCenterItem>): WriterTaskCenterItem => ({
  task_id: 'task-1',
  chapter_id: 1,
  project_id: 'project-1',
  chapter_number: 3,
  status: 'failed',
  queue_state: 'failed',
  progress_percent: 0,
  stage_label: '生成失败',
  status_message: '任务失败',
  can_cancel: false,
  can_retry: true,
  word_count: 0,
  updated_at: '2026-04-22T10:00:00',
  age_minutes: 5,
  ...partial,
})

describe('buildTaskRecoveryPlan', () => {
  it('returns config guidance for config/auth failures', () => {
    const plan = buildTaskRecoveryPlan(createTask({ failure_category: 'config' }))

    expect(plan.summary).toContain('模型配置')
    expect(plan.actions[0]?.label).toBe('修正后重试')
    expect(plan.actions[0]?.payload?.resume_from_checkpoint).toBe(false)
  })

  it('returns resume and fresh retry actions for transient failures', () => {
    const plan = buildTaskRecoveryPlan(createTask({ failure_category: 'network' }))

    expect(plan.actions.map((item) => item.label)).toEqual(['继续重试', '全量重试'])
    expect(plan.actions[1]?.requiresConfirm).toBe(true)
  })

  it('prioritizes consistency guidance when manual review is required', () => {
    const plan = buildTaskRecoveryPlan(
      createTask({
        failure_category: 'timeout',
        consistency_guard_status: 'review_required',
      }),
    )

    expect(plan.summary).toContain('人工确认')
    expect(plan.actions[0]?.payload?.writing_notes).toContain('既有设定')
  })
})
