import { describe, expect, it } from 'vitest'

import {
  buildNavigatePayload,
  foreshadowingStatusLabel,
  severityLabel,
  trajectoryShapeLabel,
} from '@/components/novel-detail/comprehensiveDiagnosis'

describe('comprehensive diagnosis helpers', () => {
  it('maps known labels to readable text', () => {
    expect(trajectoryShapeLabel('man_in_hole')).toBe('跌落再爬升')
    expect(severityLabel('high')).toBe('高优先')
    expect(foreshadowingStatusLabel('resolved')).toBe('已回收')
  })

  it('builds navigation payloads with fine-grained anchors', () => {
    expect(
      buildNavigatePayload({
        section: 'timeline',
        chapter_number: 8,
        timeline_event_id: 42,
        query: '背叛',
      }),
    ).toEqual({
      section: 'timeline',
      chapterNumber: 8,
      eventId: 42,
      foreshadowingId: undefined,
      term: undefined,
      query: '背叛',
    })
  })
})
