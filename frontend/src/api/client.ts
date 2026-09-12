import { mockRecommendations } from './mockData'
import type {
  RecommendationRequest,
  RecommendationResponse,
  ValidationError,
} from './types'

export interface RecommendationClient {
  createRecommendations(
    request: RecommendationRequest,
    signal?: AbortSignal,
  ): Promise<RecommendationResponse>
}

export class ApiValidationError extends Error {
  constructor(public readonly payload: ValidationError) {
    super(payload.message)
    this.name = 'ApiValidationError'
  }
}

export class ApiRequestError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message)
    this.name = 'ApiRequestError'
  }
}

interface ClientOptions {
  mode?: 'mock' | 'http'
  baseUrl?: string
  mockDelayMs?: number
}

function validateRequest(request: RecommendationRequest): ValidationError | null {
  const fields: ValidationError['fields'] = []

  if (!request.area.trim()) {
    fields.push({
      field: 'area',
      code: 'REQUIRED',
      message: 'エリアを入力してください。',
    })
  }

  if (!Number.isFinite(request.wheelchair_width_cm) || request.wheelchair_width_cm <= 0) {
    fields.push({
      field: 'wheelchair_width_cm',
      code: 'INVALID_VALUE',
      message: '車いすの横幅は0より大きい数値で入力してください。',
    })
  }

  return fields.length
    ? { code: 'VALIDATION_ERROR', message: '入力内容を確認してください。', fields }
    : null
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }

    const timeout = window.setTimeout(resolve, ms)
    signal?.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timeout)
        reject(new DOMException('Aborted', 'AbortError'))
      },
      { once: true },
    )
  })
}

function createMockClient(mockDelayMs: number): RecommendationClient {
  return {
    async createRecommendations(request, signal) {
      const validationError = validateRequest(request)
      if (validationError) throw new ApiValidationError(validationError)

      await delay(mockDelayMs, signal)

      return {
        recommendations: mockRecommendations
          .slice(0, request.limit ?? 5)
          .map((recommendation, index) => ({ ...recommendation, rank: index + 1 })),
      }
    },
  }
}

function createHttpClient(baseUrl: string): RecommendationClient {
  return {
    async createRecommendations(request, signal) {
      let response: Response
      try {
        response = await fetch(`${baseUrl.replace(/\/$/, '')}/v1/recommendations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(request),
          signal,
        })
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') throw error
        throw new ApiRequestError(
          'サーバーに接続できませんでした。接続先を確認してもう一度お試しください。',
        )
      }

      if (response.status === 400) {
        throw new ApiValidationError((await response.json()) as ValidationError)
      }

      if (!response.ok) {
        throw new ApiRequestError(
          'お店の検索中に問題が発生しました。時間をおいてもう一度お試しください。',
          response.status,
        )
      }

      return (await response.json()) as RecommendationResponse
    },
  }
}

export function createRecommendationClient({
  mode = import.meta.env.VITE_API_MODE ?? 'mock',
  baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080',
  mockDelayMs = 650,
}: ClientOptions = {}): RecommendationClient {
  return mode === 'http' ? createHttpClient(baseUrl) : createMockClient(mockDelayMs)
}
