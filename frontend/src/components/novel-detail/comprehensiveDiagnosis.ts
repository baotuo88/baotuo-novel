import type { ComprehensiveActionAnchor } from '@/api/novel'

export const trajectoryShapeLabel = (shape: string): string => {
  const mapping: Record<string, string> = {
    rags_to_riches: '逆袭',
    riches_to_rags: '坠落',
    man_in_hole: '跌落再爬升',
    icarus: '高飞坠落',
    cinderella: '先抑后扬',
    oedipus: '先扬后抑',
    flat: '平稳线',
  }
  return mapping[String(shape || '').trim()] || shape || '-'
}

export const severityLabel = (severity: string): string => {
  const mapping: Record<string, string> = {
    critical: '紧急',
    high: '高优先',
    medium: '中优先',
    low: '低优先',
  }
  return mapping[String(severity || '').trim().toLowerCase()] || String(severity || '建议')
}

export const foreshadowingStatusLabel = (status: string): string => {
  if (status === 'resolved') return '已回收'
  if (status === 'abandoned') return '已放弃'
  return '未闭环'
}

export const buildNavigatePayload = (anchor: ComprehensiveActionAnchor) => ({
  section: String(anchor.section || 'overview'),
  chapterNumber: anchor.chapter_number ?? undefined,
  eventId: anchor.timeline_event_id ?? undefined,
  foreshadowingId: anchor.foreshadowing_id ?? undefined,
  term: anchor.term ?? undefined,
  query: anchor.query ?? undefined,
})
