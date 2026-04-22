import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  downloadFile,
  extractErrorMessage,
  httpFetchResponse,
  normalizeErrorMessage,
  parseDownloadFilename,
  parseResponsePayload,
} from '../http'

describe('http helpers', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('extracts backend detail from json error responses and ignores html payloads', async () => {
    const jsonResponse = new Response(JSON.stringify({ detail: '权限不足' }), {
      status: 403,
      headers: { 'content-type': 'application/json' },
    })
    const htmlResponse = new Response('<!doctype html><html><body>502 Bad Gateway</body></html>', {
      status: 502,
      headers: { 'content-type': 'text/html' },
    })

    await expect(extractErrorMessage(jsonResponse)).resolves.toBe('权限不足')
    await expect(extractErrorMessage(htmlResponse)).resolves.toBe('')
  })

  it('normalizes gateway and rate limit messages', () => {
    expect(normalizeErrorMessage(503, '')).toBe('上游 AI 服务响应超时或暂时不可用，请稍后重试')
    expect(normalizeErrorMessage(429, '')).toBe('请求过于频繁，请稍后再试')
    expect(normalizeErrorMessage(400, '参数错误')).toBe('参数错误')
  })

  it('parses json and empty 204 payloads correctly', async () => {
    const jsonResponse = new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })
    const emptyResponse = new Response(null, { status: 204 })

    await expect(parseResponsePayload<{ ok: boolean }>(jsonResponse)).resolves.toEqual({ ok: true })
    await expect(parseResponsePayload<null>(emptyResponse)).resolves.toBeNull()
  })

  it('calls unauthorized handler on 401 and throws normalized error', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: '登录过期' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const onUnauthorized = vi.fn()

    vi.stubGlobal('fetch', fetchMock)

    await expect(
      httpFetchResponse('/api/test', {
        token: 'token-1',
        onUnauthorized,
      }),
    ).rejects.toThrow('登录过期')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/test',
      expect.objectContaining({
        headers: expect.any(Headers),
        signal: expect.any(AbortSignal),
      }),
    )
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('turns aborted fetch into timeout error when local timeout fires', async () => {
    vi.useFakeTimers()

    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      const signal = init?.signal as AbortSignal
      return new Promise<Response>((_resolve, reject) => {
        signal.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'))
        })
      })
    })

    vi.stubGlobal('fetch', fetchMock)

    const pending = httpFetchResponse('/api/slow', { timeoutMs: 5 })
    const assertion = expect(pending).rejects.toThrow('请求超时（>1秒），请稍后重试')
    await vi.advanceTimersByTimeAsync(10)

    await assertion

    vi.useRealTimers()
  })

  it('parses utf-8 download filenames and uses them in downloadFile', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob(['csv-content']), {
        status: 200,
        headers: {
          'content-disposition': "attachment; filename*=UTF-8''%E6%8A%A5%E8%A1%A8.csv",
        },
      }),
    )
    const createObjectURL = vi.fn(() => 'blob:test')
    const revokeObjectURL = vi.fn()
    const click = vi.fn()
    const appendChild = vi.fn()
    const removeChild = vi.fn()
    const createElement = vi.fn(() => ({
      href: '',
      download: '',
      click,
    }))

    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('URL', {
      createObjectURL,
      revokeObjectURL,
    })
    vi.stubGlobal('document', {
      body: {
        appendChild,
        removeChild,
      },
      createElement,
    })

    await downloadFile('/api/export', {
      method: 'GET',
      fallbackName: 'fallback.csv',
    })

    const link = createElement.mock.results[0].value
    expect(parseDownloadFilename("attachment; filename*=UTF-8''%E6%8A%A5%E8%A1%A8.csv", 'fallback.csv')).toBe('报表.csv')
    expect(link.download).toBe('报表.csv')
    expect(click).toHaveBeenCalledTimes(1)
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
  })
})
