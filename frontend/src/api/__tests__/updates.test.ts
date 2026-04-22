import { beforeEach, describe, expect, it, vi } from 'vitest'

const { httpRequestMock } = vi.hoisted(() => ({
  httpRequestMock: vi.fn(),
}))

vi.mock('../http', () => ({
  httpRequest: httpRequestMock,
}))

import { getLatestUpdates } from '../updates'

describe('updates api', () => {
  beforeEach(() => {
    httpRequestMock.mockReset()
  })

  it('requests the public latest updates endpoint through the shared http client', async () => {
    httpRequestMock.mockResolvedValueOnce([
      {
        id: 1,
        content: '新增增强分析入口',
        created_at: '2026-04-21T10:00:00Z',
      },
    ])

    const updates = await getLatestUpdates()

    expect(httpRequestMock).toHaveBeenCalledWith('http://127.0.0.1:8000/api/updates/latest', {})
    expect(updates).toEqual([
      {
        id: 1,
        content: '新增增强分析入口',
        created_at: '2026-04-21T10:00:00Z',
      },
    ])
  })
})
