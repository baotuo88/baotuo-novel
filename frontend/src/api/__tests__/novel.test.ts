import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  httpRequestMock,
  downloadFileMock,
  logoutMock,
  pushMock,
} = vi.hoisted(() => ({
  httpRequestMock: vi.fn(),
  downloadFileMock: vi.fn(),
  logoutMock: vi.fn(),
  pushMock: vi.fn(),
}))

vi.mock('../http', () => ({
  httpRequest: httpRequestMock,
  downloadFile: downloadFileMock,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    isAuthenticated: true,
    token: 'test-token',
    logout: logoutMock,
  }),
}))

vi.mock('@/router', () => ({
  default: {
    push: pushMock,
  },
}))

import { NovelAPI } from '../novel'

describe('NovelAPI.getEmotionCurve', () => {
  beforeEach(() => {
    httpRequestMock.mockReset()
    downloadFileMock.mockReset()
    logoutMock.mockReset()
    pushMock.mockReset()
  })

  it('adapts enhanced analytics points into the unified emotion curve model', async () => {
    httpRequestMock.mockResolvedValueOnce([
      {
        chapter_number: 3,
        chapter_id: 'c-3',
        title: '转折',
        primary_emotion: 'surprise',
        primary_intensity: 8.567,
        secondary_emotions: [['fear', 4.2]],
        narrative_phase: 'climax',
        pace: 'fast',
        is_turning_point: true,
        turning_point_type: 'revelation',
        description: '关键真相揭晓带来强烈震惊',
      },
      {
        chapter_number: 4,
        chapter_id: 'c-4',
        title: '余波',
        primary_emotion: 'trust',
        primary_intensity: 5,
        secondary_emotions: [],
        narrative_phase: 'falling_action',
        pace: 'medium',
        is_turning_point: false,
        turning_point_type: null,
        description: '人物关系开始修复',
      },
    ])

    const response = await NovelAPI.getEmotionCurve('project-1', 'enhanced')

    expect(httpRequestMock).toHaveBeenCalledTimes(1)
    expect(httpRequestMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/analytics/enhanced/projects/project-1/emotion-curve-enhanced',
      expect.objectContaining({
        token: 'test-token',
        onUnauthorized: expect.any(Function),
      }),
    )
    expect(response).toEqual({
      project_id: 'project-1',
      project_title: '',
      total_chapters: 2,
      emotion_points: [
        {
          chapter_number: 3,
          title: '转折',
          emotion_type: '惊讶',
          intensity: 8.57,
          narrative_phase: 'climax',
          description: '关键真相揭晓带来强烈震惊',
        },
        {
          chapter_number: 4,
          title: '余波',
          emotion_type: '信任',
          intensity: 5,
          narrative_phase: 'falling_action',
          description: '人物关系开始修复',
        },
      ],
      average_intensity: 6.785,
      emotion_distribution: {
        惊讶: 1,
        信任: 1,
      },
    })
  })

  it('uses the AI analytics endpoint with POST when mode is ai', async () => {
    httpRequestMock.mockResolvedValueOnce({ project_id: 'project-ai' })

    await NovelAPI.getEmotionCurve('project-ai', 'ai')

    expect(httpRequestMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/analytics/project-ai/analyze-emotion-ai',
      expect.objectContaining({
        method: 'POST',
        token: 'test-token',
      }),
    )
  })
})
