import { describe, expect, it, vi } from 'vitest'
import { ApiValidationError, createRecommendationClient } from './client'

describe('recommendation client', () => {
  it('returns OpenAPI-compatible mock recommendations', async () => {
    const client = createRecommendationClient({ mode: 'mock', mockDelayMs: 0 })

    const response = await client.createRecommendations({
      area: '福岡市中央区',
      wheelchair_width_cm: 63,
      limit: 2,
    })

    expect(response.recommendations).toHaveLength(2)
    expect(response.recommendations[0]).toMatchObject({
      rank: 1,
      accessibility: { status: 'accessible', confidence: 'high' },
    })
  })

  it('uses the same field-error shape as the API for invalid input', async () => {
    const client = createRecommendationClient({ mode: 'mock', mockDelayMs: 0 })

    await expect(
      client.createRecommendations({ area: '', wheelchair_width_cm: 0 }),
    ).rejects.toMatchObject<ApiValidationError>({
      name: 'ApiValidationError',
      message: expect.any(String),
      payload: {
        code: 'VALIDATION_ERROR',
        message: expect.any(String),
        fields: expect.arrayContaining([
          expect.objectContaining({ field: 'area' }),
          expect.objectContaining({ field: 'wheelchair_width_cm' }),
        ]),
      },
    })
  })

  it('calls the Cloud Run API when HTTP mode is selected', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ recommendations: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const client = createRecommendationClient({
      mode: 'http',
      baseUrl: 'https://example.run.app/',
    })

    await client.createRecommendations({
      area: '福岡市中央区',
      wheelchair_width_cm: 63,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'https://example.run.app/v1/recommendations',
      expect.objectContaining({ method: 'POST' }),
    )
    fetchMock.mockRestore()
  })
})
