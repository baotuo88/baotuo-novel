import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { httpRequestMock } = vi.hoisted(() => ({
  httpRequestMock: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  httpRequest: httpRequestMock,
}))

import { useAuthStore } from '../auth'

type LocalStorageMock = {
  getItem: ReturnType<typeof vi.fn>
  setItem: ReturnType<typeof vi.fn>
  removeItem: ReturnType<typeof vi.fn>
}

describe('auth store', () => {
  let localStorageMock: LocalStorageMock

  beforeEach(() => {
    setActivePinia(createPinia())
    httpRequestMock.mockReset()

    localStorageMock = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    }

    vi.stubGlobal('localStorage', localStorageMock)
  })

  it('logs in, persists token, fetches current user and preserves must-change-password flag', async () => {
    httpRequestMock
      .mockResolvedValueOnce({
        access_token: 'token-123',
        must_change_password: true,
      })
      .mockResolvedValueOnce({
        id: 8,
        username: 'admin',
        is_admin: true,
        must_change_password: false,
      })

    const store = useAuthStore()
    const mustChange = await store.login('admin', 'password-123')

    expect(mustChange).toBe(true)
    expect(store.token).toBe('token-123')
    expect(store.user).toEqual({
      id: 8,
      username: 'admin',
      is_admin: true,
      must_change_password: true,
    })
    expect(localStorageMock.setItem).toHaveBeenCalledWith('token', 'token-123')
    expect(httpRequestMock).toHaveBeenNthCalledWith(
      1,
      'http://127.0.0.1:8000/api/auth/token',
      expect.objectContaining({
        method: 'POST',
        body: expect.any(URLSearchParams),
      }),
    )
    expect(httpRequestMock).toHaveBeenNthCalledWith(
      2,
      'http://127.0.0.1:8000/api/auth/users/me',
      expect.objectContaining({
        token: 'token-123',
      }),
    )
  })

  it('falls back to default auth options when fetching auth options fails', async () => {
    httpRequestMock.mockRejectedValueOnce(new Error('network failed'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const store = useAuthStore()
    await store.fetchAuthOptions()

    expect(store.authOptions).toEqual({
      allow_registration: true,
      enable_linuxdo_login: false,
    })
    expect(store.authOptionsLoaded).toBe(true)

    errorSpy.mockRestore()
  })

  it('logs out and clears persisted token when fetching current user fails', async () => {
    httpRequestMock.mockRejectedValueOnce(new Error('unauthorized'))

    const store = useAuthStore()
    store.token = 'expired-token'

    await store.fetchUser()

    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('token')
  })
})
