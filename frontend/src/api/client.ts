import { mockRecommendations } from './mockData'
import type {
  AssessmentResult,
  RecommendationRequest,
  RecommendationResponse,
  ValidationError,
} from './types'

const DEFAULT_API_BASE_URL =
  'https://backend-api-378214973378.asia-northeast1.run.app'

export interface RecommendationClient {
  readonly mode: 'mock' | 'http'
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
    mode: 'mock',
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

function normalizeAssessmentResult(result: string): AssessmentResult {
  const aliases: Record<string, AssessmentResult> = {
    supported: 'supported',
    unsupported: 'unsupported',
    unknown: 'unknown',
    accessible: 'supported',
    not_accessible: 'unsupported',
    uncertain: 'unknown',
  }

  return aliases[result] ?? 'unknown'
}

/**
 * 検証用backend-apiは判定根拠にも店舗全体のstatus値を返すことがある。
 * OpenAPIを画面側の正本に保ったまま、通信境界で互換値へ変換する。
 */
function normalizeResponse(response: RecommendationResponse): RecommendationResponse {
  return {
    recommendations: response.recommendations.map((recommendation) => ({
      ...recommendation,
      accessibility: {
        ...recommendation.accessibility,
        reasons: recommendation.accessibility.reasons.map((reason) => ({
          ...reason,
          result: normalizeAssessmentResult(reason.result as string),
        })),
      },
    })),
  }
}

function createHttpClient(baseUrl: string): RecommendationClient {
  return {
    mode: 'http',
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

      return normalizeResponse((await response.json()) as RecommendationResponse)
    },
  }
}

export function createRecommendationClient({
  mode = import.meta.env.VITE_API_MODE ?? 'http',
  baseUrl = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL,
  mockDelayMs = 650,
}: ClientOptions = {}): RecommendationClient {
  return mode === 'http' ? createHttpClient(baseUrl) : createMockClient(mockDelayMs)
}
