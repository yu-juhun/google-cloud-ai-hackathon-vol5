import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiValidationError,
  createRecommendationClient,
  type RecommendationClient,
} from './api/client'
import type {
  FieldError,
  RecommendationRequest,
  RestaurantRecommendation,
} from './api/types'
import { MapPanel } from './components/MapPanel'
import { RecommendationCard } from './components/RecommendationCard'
import { SearchForm } from './components/SearchForm'

export const initialRequest: RecommendationRequest = {
  area: '福岡市',
  cuisine: 'イタリアン',
  wheelchair_width_cm: 63,
  prompt: '入口に段差がなく、トイレも使いやすい店',
  limit: 5,
}

const defaultClient = createRecommendationClient()

interface AppProps {
  client?: RecommendationClient
  mapsApiKey?: string
  mapsMapId?: string
}

export function App({
  client = defaultClient,
  mapsApiKey,
  mapsMapId,
}: AppProps) {
  const [recommendations, setRecommendations] = useState<RestaurantRecommendation[]>([])
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([])
  const [requestError, setRequestError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [searchedArea, setSearchedArea] = useState(initialRequest.area)
  const activeRequest = useRef<AbortController | null>(null)

  const search = useCallback(
    async (request: RecommendationRequest) => {
      activeRequest.current?.abort()
      const controller = new AbortController()
      activeRequest.current = controller

      setIsLoading(true)
      setFieldErrors([])
      setRequestError(null)

      try {
        const response = await client.createRecommendations(request, controller.signal)
        setRecommendations(response.recommendations)
        setSelectedPlaceId(null)
        setSearchedArea(request.area)
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return

        if (error instanceof ApiValidationError) {
          setFieldErrors(error.payload.fields)
          setRequestError(error.payload.message)
        } else {
          setRequestError(
            error instanceof Error
              ? error.message
              : 'お店を検索できませんでした。もう一度お試しください。',
          )
        }
      } finally {
        if (activeRequest.current === controller) setIsLoading(false)
      }
    },
    [client],
  )

  useEffect(() => {
    void search(initialRequest)
    return () => activeRequest.current?.abort()
  }, [search])

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="wishlan ホーム">
          <span className="brand-mark" aria-hidden="true">w</span>
          <h1>wishlan</h1>
        </a>
      </header>

      <main id="top">
        <SearchForm
          initialValue={initialRequest}
          isLoading={isLoading}
          fieldErrors={fieldErrors}
          onSubmit={(request) => void search(request)}
        />

        {requestError && (
          <div className="error-banner" role="alert">
            <b>
              {fieldErrors.length
                ? '検索条件を確認してください'
                : 'お店を検索できませんでした'}
            </b>
            <span>{requestError}</span>
          </div>
        )}

        <section className="results-section" aria-busy={isLoading}>
          <div className="results-heading">
            <div>
              <h2>{searchedArea}の検索結果</h2>
            </div>
            {!isLoading && (
              <p>
                <b>{recommendations.length}</b>件を比較しました
              </p>
            )}
          </div>

          {isLoading ? (
            <LoadingState />
          ) : recommendations.length ? (
            <div className="results-layout">
              <div className="recommendation-list">
                {recommendations.map((recommendation) => (
                  <RecommendationCard
                    key={recommendation.place_id}
                    recommendation={recommendation}
                    isSelected={recommendation.place_id === selectedPlaceId}
                    onSelect={() => setSelectedPlaceId(recommendation.place_id)}
                  />
                ))}
              </div>
              <MapPanel
                recommendations={recommendations}
                selectedPlaceId={selectedPlaceId}
                onSelect={setSelectedPlaceId}
                apiKey={mapsApiKey}
                mapId={mapsMapId}
              />
            </div>
          ) : (
            <div className="empty-state">
              <span aria-hidden="true">⌕</span>
              <h3>条件に合う候補が見つかりませんでした</h3>
              <p>エリアを広げるか、希望条件を減らしてもう一度お試しください。</p>
            </div>
          )}
        </section>

        <aside className="safety-note">
          <span aria-hidden="true">i</span>
          <p>
            <b>来店前の確認について</b>
            AIによる判定は、公開されている写真やレビューをもとにした見立てです。設備の変更などもあるため、△の店舗は事前にお店へ確認すると安心です。
          </p>
        </aside>
      </main>

      <footer>
        <span>
          {client.mode === 'mock'
            ? '店舗名・所在地は実在情報を使用し、AIの入店可否判定・推薦理由はデモ用です'
            : '検索結果と入店可否判定は、推薦APIが公開情報をもとに生成しています'}
        </span>
      </footer>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="loading-state" role="status">
      <div className="loading-copy">
        <span className="loading-orbit" aria-hidden="true"><i /></span>
        <div>
          <h3>AIが行きやすさを確認中</h3>
          <p>入口、通路、トイレの情報を確認しています（通常15〜40秒）…</p>
        </div>
      </div>
      <div className="skeleton-grid" aria-hidden="true">
        <span /><span /><span />
      </div>
    </div>
  )
}
