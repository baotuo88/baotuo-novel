export const DEFAULT_REQUEST_TIMEOUT_MS = Math.max(
  5000,
  Number(import.meta.env.VITE_API_TIMEOUT_MS || 95000)
)

export type HttpRequestOptions = RequestInit & {
  timeoutMs?: number
  token?: string | null
  onUnauthorized?: (() => void | Promise<void>) | null
}

const isLikelyHtml = (value: string): boolean => {
  const trimmed = value.trim().toLowerCase()
  if (!trimmed) return false
  return (
    trimmed.startsWith('<!doctype html') ||
    trimmed.startsWith('<html') ||
    (trimmed.startsWith('<') && trimmed.includes('</'))
  )
}

export const extractErrorMessage = async (response: Response): Promise<string> => {
  const rawText = await response.text().catch(() => '')
  if (!rawText) return ''

  try {
    const errorData = JSON.parse(rawText)
    const detail = errorData?.detail || errorData?.message || ''
    return typeof detail === 'string' ? detail.trim() : ''
  } catch {
    const trimmed = rawText.trim()
    if (!trimmed || isLikelyHtml(trimmed)) {
      return ''
    }
    return trimmed.slice(0, 240)
  }
}

export const normalizeErrorMessage = (status: number, detail: string): string => {
  if ([502, 503, 504].includes(status)) {
    return '上游 AI 服务响应超时或暂时不可用，请稍后重试'
  }
  if (status === 429) {
    return detail || '请求过于频繁，请稍后再试'
  }
  if (status >= 500) {
    return detail || '服务器内部错误，请稍后重试'
  }
  return detail || `请求失败，状态码: ${status}`
}

export const parseResponsePayload = async <T>(response: Response): Promise<T> => {
  if (response.status === 204) {
    return null as T
  }

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return (await response.json()) as T
  }

  const text = await response.text()
  if (!text.trim()) {
    return null as T
  }
  try {
    return JSON.parse(text) as T
  } catch {
    return text as T
  }
}

export const parseDownloadFilename = (contentDisposition: string | null, fallback: string): string => {
  if (!contentDisposition) return fallback
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return utf8Match[1]
    }
  }
  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  if (plainMatch?.[1]) {
    return plainMatch[1]
  }
  return fallback
}

const shouldSetJsonContentType = (body: BodyInit | null | undefined): boolean => {
  if (!body) return false
  return !(body instanceof FormData) && !(body instanceof URLSearchParams) && !(body instanceof Blob)
}

export const httpFetchResponse = async (url: string, options: HttpRequestOptions = {}): Promise<Response> => {
  const timeoutMs = options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS
  const controller = new AbortController()
  const timeoutId = globalThis.setTimeout(() => {
    controller.abort(new Error('Request timeout'))
  }, timeoutMs)

  const headers = new Headers(options.headers || undefined)
  if (shouldSetJsonContentType(options.body) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (options.body instanceof FormData) {
    headers.delete('Content-Type')
  }

  if (options.token) {
    headers.set('Authorization', `Bearer ${options.token}`)
  }

  if (options.signal) {
    if (options.signal.aborted) {
      controller.abort()
    } else {
      options.signal.addEventListener('abort', () => controller.abort(), { once: true })
    }
  }

  let response: Response
  try {
    response = await fetch(url, { ...options, headers, signal: controller.signal })
  } catch (error) {
    const isAbort = (error as DOMException)?.name === 'AbortError'
    if (isAbort) {
      if (options.signal?.aborted) {
        throw new Error('请求已取消')
      }
      throw new Error(`请求超时（>${Math.ceil(timeoutMs / 1000)}秒），请稍后重试`)
    }
    throw new Error('网络连接失败，请检查网络或服务状态')
  } finally {
    globalThis.clearTimeout(timeoutId)
  }

  if (response.status === 401 && options.onUnauthorized) {
    await options.onUnauthorized()
  }

  if (!response.ok) {
    const detail = await extractErrorMessage(response)
    throw new Error(normalizeErrorMessage(response.status, detail))
  }

  return response
}

export const httpRequest = async <T = unknown>(url: string, options: HttpRequestOptions = {}): Promise<T> => {
  const response = await httpFetchResponse(url, options)

  return parseResponsePayload<T>(response)
}

export const saveBlobAsFile = (blob: Blob, filename: string): void => {
  const href = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = href
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(href)
}

export const downloadFile = async (
  url: string,
  options: HttpRequestOptions & { fallbackName: string }
): Promise<void> => {
  const { fallbackName, ...requestOptions } = options
  const response = await httpFetchResponse(url, requestOptions)
  const blob = await response.blob()
  const filename = parseDownloadFilename(response.headers.get('content-disposition'), fallbackName)
  saveBlobAsFile(blob, filename)
}
