import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  httpRequestMock,
  httpFetchResponseMock,
  logoutMock,
  pushMock,
} = vi.hoisted(() => ({
  httpRequestMock: vi.fn(),
  httpFetchResponseMock: vi.fn(),
  logoutMock: vi.fn(),
  pushMock: vi.fn(),
}))

vi.mock('../http', () => ({
  httpRequest: httpRequestMock,
  httpFetchResponse: httpFetchResponseMock,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    isAuthenticated: true,
    token: 'admin-token',
    logout: logoutMock,
  }),
}))

vi.mock('@/router', () => ({
  default: {
    push: pushMock,
  },
}))

import { AdminAPI } from '../admin'

describe('AdminAPI', () => {
  beforeEach(() => {
    httpRequestMock.mockReset()
    httpFetchResponseMock.mockReset()
    logoutMock.mockReset()
    pushMock.mockReset()
  })

  it('requests statistics through the unified admin client and wires unauthorized handling', async () => {
    httpRequestMock.mockResolvedValueOnce({
      novel_count: 12,
      user_count: 5,
      api_request_count: 123,
    })

    const response = await AdminAPI.getStatistics()

    expect(httpRequestMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/admin/stats',
      expect.objectContaining({
        token: 'admin-token',
        onUnauthorized: expect.any(Function),
      }),
    )
    expect(response).toEqual({
      novel_count: 12,
      user_count: 5,
      api_request_count: 123,
    })

    const options = httpRequestMock.mock.calls[0][1]
    await options.onUnauthorized()

    expect(logoutMock).toHaveBeenCalledTimes(1)
    expect(pushMock).toHaveBeenCalledWith('/login')
  })

  it('builds query strings correctly for grouped LLM trend requests', async () => {
    httpRequestMock.mockResolvedValueOnce({
      period_hours: 48,
      group_by: 'model',
      buckets: [],
      series: [],
    })

    await AdminAPI.getLLMHourlyGroupedTrend({
      hours: 48,
      group_by: 'model',
      limit: 10,
      status_filter: 'success',
      request_type: 'writer',
      model: 'gpt-5.4',
      user_id: 9,
      project_id: 'proj-9',
    })

    expect(httpRequestMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/admin/llm-call-logs/hourly-grouped?hours=48&group_by=model&limit=10&status_filter=success&request_type=writer&model=gpt-5.4&user_id=9&project_id=proj-9',
      expect.objectContaining({
        token: 'admin-token',
      }),
    )
  })
})
