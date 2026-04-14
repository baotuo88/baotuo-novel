export type DiffLineType = 'equal' | 'add' | 'remove'

export interface DiffLine {
  type: DiffLineType
  text: string
}

export interface DiffResult {
  lines: DiffLine[]
  added: number
  removed: number
  equal: number
  truncated: boolean
}

const normalizeText = (value: string): string => {
  if (!value) return ''
  return value.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
}

const fallbackDiff = (baseLines: string[], compareLines: string[]): DiffResult => {
  const maxLength = Math.max(baseLines.length, compareLines.length)
  const lines: DiffLine[] = []
  let added = 0
  let removed = 0
  let equal = 0

  for (let i = 0; i < maxLength; i += 1) {
    const left = baseLines[i]
    const right = compareLines[i]

    if (left === right && left !== undefined) {
      lines.push({ type: 'equal', text: left })
      equal += 1
      continue
    }

    if (left !== undefined) {
      lines.push({ type: 'remove', text: left })
      removed += 1
    }

    if (right !== undefined) {
      lines.push({ type: 'add', text: right })
      added += 1
    }
  }

  return {
    lines,
    added,
    removed,
    equal,
    truncated: true
  }
}

export const buildLineDiff = (
  baseText: string,
  compareText: string,
  options: { maxLines?: number; maxMatrixCells?: number } = {}
): DiffResult => {
  const maxLines = options.maxLines ?? 1000
  const maxMatrixCells = options.maxMatrixCells ?? 700_000

  let baseLines = normalizeText(baseText).split('\n')
  let compareLines = normalizeText(compareText).split('\n')

  let truncated = false
  if (baseLines.length > maxLines) {
    baseLines = baseLines.slice(0, maxLines)
    truncated = true
  }
  if (compareLines.length > maxLines) {
    compareLines = compareLines.slice(0, maxLines)
    truncated = true
  }

  const n = baseLines.length
  const m = compareLines.length

  if (n * m > maxMatrixCells) {
    return fallbackDiff(baseLines, compareLines)
  }

  const dp: number[][] = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0))

  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      if (baseLines[i] === compareLines[j]) {
        dp[i][j] = dp[i + 1][j + 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1])
      }
    }
  }

  const lines: DiffLine[] = []
  let i = 0
  let j = 0
  let added = 0
  let removed = 0
  let equal = 0

  while (i < n && j < m) {
    if (baseLines[i] === compareLines[j]) {
      lines.push({ type: 'equal', text: baseLines[i] })
      equal += 1
      i += 1
      j += 1
      continue
    }

    if (dp[i + 1][j] >= dp[i][j + 1]) {
      lines.push({ type: 'remove', text: baseLines[i] })
      removed += 1
      i += 1
    } else {
      lines.push({ type: 'add', text: compareLines[j] })
      added += 1
      j += 1
    }
  }

  while (i < n) {
    lines.push({ type: 'remove', text: baseLines[i] })
    removed += 1
    i += 1
  }

  while (j < m) {
    lines.push({ type: 'add', text: compareLines[j] })
    added += 1
    j += 1
  }

  return {
    lines,
    added,
    removed,
    equal,
    truncated
  }
}
