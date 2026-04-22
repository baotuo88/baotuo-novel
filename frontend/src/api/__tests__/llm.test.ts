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
    token: 'llm-token',
    logout: logoutMock,
  }),
}))

vi.mock('@/router', () => ({
  default: {
    push: pushMock,
  },
}))

import {
  createOrUpdateLLMConfig,
  downloadMySubscriptionBillingCsv,
  getAvailableModels,
  getLLMConfig,
  getMySubscriptionBilling,
} from '../llm'

describe('llm api', () => {
  beforeEach(() => {
    httpRequestMock.mockReset()
    downloadFileMock.mockReset()
    logoutMock.mockReset()
    pushMock.mockReset()
  })

  it('returns null when llm config endpoint responds with 404-style error', async () => {
    httpRequestMock.mockRejectedValueOnce(new Error('请求失败，状态码: 404'))

    await expect(getLLMConfig()).resolves.toBeNull()
  })

  it('returns an empty model list when model discovery fails', async () => {
    httpRequestMock.mockRejectedValueOnce(new Error('network failed'))

    await expect(
      getAvailableModels({
        llm_provider_api_key: 'secret',
      }),
    ).resolves.toEqual([])
  })

  it('builds billing query strings and subscription csv download requests correctly', async () => {
    httpRequestMock.mockResolvedValueOnce({
      user_id: 1,
      hours: 72,
      total_calls: 2,
      success_calls: 2,
      total_estimated_cost_usd: 1.23,
      items: [],
    })
    downloadFileMock.mockResolvedValueOnce(undefined)

    await getMySubscriptionBilling({ hours: 72, limit: 20 })
    await downloadMySubscriptionBillingCsv({ hours: 24, limit: 5 })

    expect(httpRequestMock).toHaveBeenCalledWith(
      '/api/auth/subscription/billing?hours=72&limit=20',
      expect.objectContaining({
        method: 'GET',
        token: 'llm-token',
      }),
    )
    expect(downloadFileMock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/api\/auth\/subscription\/billing\/export\.csv\?hours=24&limit=5$/),
      expect.objectContaining({
        method: 'GET',
        token: 'llm-token',
        fallbackName: expect.stringMatching(/^subscription_billing_\d+\.csv$/),
        onUnauthorized: expect.any(Function),
      }),
    )
  })

  it('sends put requests for llm config upserts through the unified client', async () => {
    httpRequestMock.mockResolvedValueOnce({
      user_id: 1,
      llm_provider_url: 'https://api.example.com',
      llm_provider_api_key: 'masked',
      llm_provider_model: 'gpt-5.4',
    })

    await createOrUpdateLLMConfig({
      llm_provider_url: 'https://api.example.com',
      llm_provider_api_key: 'secret',
      llm_provider_model: 'gpt-5.4',
    })

    expect(httpRequestMock).toHaveBeenCalledWith(
      '/api/llm-config',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({
          llm_provider_url: 'https://api.example.com',
          llm_provider_api_key: 'secret',
          llm_provider_model: 'gpt-5.4',
        }),
        token: 'llm-token',
      }),
    )
  })
})
