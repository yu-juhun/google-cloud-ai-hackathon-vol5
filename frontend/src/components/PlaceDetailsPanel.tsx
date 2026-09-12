import { useEffect, useRef, useState } from 'react'
import { useMapsLibrary } from '@vis.gl/react-google-maps'
import type { RestaurantRecommendation } from '../api/types'

interface PlaceDetailsPanelProps {
  recommendation: RestaurantRecommendation
}

type LoadState =
  | { status: 'loading'; place: null }
  | { status: 'ready'; place: google.maps.places.Place }
  | { status: 'error'; place: null }

const PLACE_FIELDS = [
  'accessibilityOptions',
  'displayName',
  'formattedAddress',
  'googleMapsURI',
  'nationalPhoneNumber',
  'photos',
  'rating',
  'regularOpeningHours',
  'reviews',
  'userRatingCount',
  'websiteURI',
]

function accessibilityLabel(value: boolean | null | undefined) {
  if (value === true) return { symbol: '○', label: '対応あり', className: 'yes' }
  if (value === false) return { symbol: '×', label: '対応なし', className: 'no' }
  return { symbol: '−', label: '情報なし', className: 'unknown' }
}

function AccessibilityItem({ label, value }: { label: string; value: boolean | null | undefined }) {
  const state = accessibilityLabel(value)
  return (
    <li className={`place-accessibility-${state.className}`}>
      <b aria-hidden="true">{state.symbol}</b>
      <span>{label}</span>
      <small>{state.label}</small>
    </li>
  )
}

function StreetViewPreview({ recommendation }: PlaceDetailsPanelProps) {
  const streetView = useMapsLibrary('streetView')
  const containerRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading')

  useEffect(() => {
    if (!streetView) return

    let active = true
    let panorama: google.maps.StreetViewPanorama | null = null
    setStatus('loading')

    const service = new streetView.StreetViewService()
    void service
      .getPanorama({
        location: {
          lat: recommendation.location.latitude,
          lng: recommendation.location.longitude,
        },
        radius: 50,
        preference: 'best',
        sources: ['outdoor'],
      })
      .then(({ data }) => {
        if (!active || !containerRef.current || !data.location?.pano) return
        panorama = new streetView.StreetViewPanorama(containerRef.current, {
          pano: data.location.pano,
          pov: { heading: 0, pitch: 0 },
          zoom: 0,
          addressControl: false,
          fullscreenControl: true,
          motionTracking: false,
          motionTrackingControl: false,
          visible: true,
        })
        setStatus('ready')
      })
      .catch(() => {
        if (active) setStatus('unavailable')
      })

    return () => {
      active = false
      panorama?.setVisible(false)
    }
  }, [recommendation, streetView])

  return (
    <section className="street-view-section" aria-label={`${recommendation.name}周辺のストリートビュー`}>
      <div className="place-section-heading">
        <h4>周辺のストリートビュー</h4>
        <span>店舗位置から50m以内</span>
      </div>
      <div className="street-view-frame">
        <div ref={containerRef} className="street-view-canvas" />
        {status !== 'ready' && (
          <div className="street-view-status" role="status">
            {status === 'loading'
              ? 'ストリートビューを読み込んでいます…'
              : 'この店舗付近のストリートビューは見つかりませんでした。'}
          </div>
        )}
      </div>
    </section>
  )
}

export function PlaceDetailsPanel({ recommendation }: PlaceDetailsPanelProps) {
  const places = useMapsLibrary('places')
  const [loadState, setLoadState] = useState<LoadState>({ status: 'loading', place: null })

  useEffect(() => {
    if (!places) return

    let active = true
    setLoadState({ status: 'loading', place: null })
    const place = new places.Place({
      id: recommendation.place_id,
      requestedLanguage: 'ja',
      requestedRegion: 'JP',
    })

    void place
      .fetchFields({ fields: PLACE_FIELDS })
      .then(({ place: loadedPlace }) => {
        if (active) setLoadState({ status: 'ready', place: loadedPlace })
      })
      .catch(() => {
        if (active) setLoadState({ status: 'error', place: null })
      })

    return () => {
      active = false
    }
  }, [places, recommendation.place_id])

  if (loadState.status === 'loading') {
    return (
      <div className="place-details-loading" role="status">
        Google Mapsの店舗情報を読み込んでいます…
      </div>
    )
  }

  if (loadState.status === 'error') {
    return (
      <div className="place-details-error" role="alert">
        <strong>店舗情報を取得できませんでした</strong>
        <p>Places APIの設定を確認するか、Google Mapsのリンクからご確認ください。</p>
        <a href={recommendation.maps_url} target="_blank" rel="noreferrer">
          Google Mapsで確認 ↗
        </a>
      </div>
    )
  }

  const place = loadState.place
  const photo = place.photos?.[0]
  const review = place.reviews?.[0]
  const photoAttributions = photo?.authorAttributions ?? []
  const reviewAuthor = review?.authorAttribution
  const accessibility = place.accessibilityOptions
  const mapsUrl = place.googleMapsURI ?? recommendation.maps_url

  return (
    <aside className="place-details" aria-label={`${recommendation.name}のGoogle Maps掲載情報`}>
      <header className="place-details-header">
        <div>
          <span className="google-maps-source">Google Maps 掲載情報</span>
          <h3>{place.displayName ?? recommendation.name}</h3>
          <p>{place.formattedAddress ?? recommendation.address}</p>
        </div>
        {place.rating != null && (
          <div className="place-rating" aria-label={`評価 ${place.rating}、${place.userRatingCount ?? 0}件`}>
            <b>★ {place.rating.toFixed(1)}</b>
            <small>{place.userRatingCount?.toLocaleString('ja-JP') ?? 0}件</small>
          </div>
        )}
      </header>

      {photo && (
        <figure className="place-photo">
          <img
            src={photo.getURI({ maxWidth: 720, maxHeight: 420 })}
            alt={`${recommendation.name}のGoogle Maps掲載写真`}
            loading="lazy"
          />
          <figcaption>
            {photoAttributions.length > 0 && (
              <span>
                写真: {photoAttributions.map((author, index) => (
                  <span key={`${author.displayName}-${index}`}>
                    {index > 0 && '、'}
                    {author.uri ? (
                      <a href={author.uri} target="_blank" rel="noreferrer">{author.displayName}</a>
                    ) : author.displayName}
                  </span>
                ))}
              </span>
            )}
            {photo.googleMapsURI && (
              <a href={photo.googleMapsURI} target="_blank" rel="noreferrer">元の写真を表示 ↗</a>
            )}
          </figcaption>
        </figure>
      )}

      <div className="place-contact-grid">
        {place.nationalPhoneNumber && (
          <a href={`tel:${place.nationalPhoneNumber.replace(/[^\d+]/g, '')}`}>
            <span>電話</span>
            <b>{place.nationalPhoneNumber}</b>
          </a>
        )}
        {place.websiteURI && (
          <a href={place.websiteURI} target="_blank" rel="noreferrer">
            <span>公式サイト</span>
            <b>Webサイトを開く ↗</b>
          </a>
        )}
        <a href={mapsUrl} target="_blank" rel="noreferrer">
          <span>Google Maps</span>
          <b>地図アプリで開く ↗</b>
        </a>
      </div>

      {place.regularOpeningHours?.weekdayDescriptions.length ? (
        <details className="place-hours">
          <summary>営業時間を確認</summary>
          <ul>
            {place.regularOpeningHours.weekdayDescriptions.map((description) => (
              <li key={description}>{description}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <section className="place-accessibility">
        <div className="place-section-heading">
          <h4>Google Mapsの車椅子対応情報</h4>
          <span>来店前に店舗へご確認ください</span>
        </div>
        <ul>
          <AccessibilityItem label="入口" value={accessibility?.hasWheelchairAccessibleEntrance} />
          <AccessibilityItem label="座席" value={accessibility?.hasWheelchairAccessibleSeating} />
          <AccessibilityItem label="トイレ" value={accessibility?.hasWheelchairAccessibleRestroom} />
          <AccessibilityItem label="駐車場" value={accessibility?.hasWheelchairAccessibleParking} />
        </ul>
      </section>

      {review && (
        <section className="place-review">
          <div className="place-section-heading">
            <h4>Google Mapsの口コミ</h4>
            <span>関連度順で提供された口コミから1件</span>
          </div>
          <blockquote>
            <div className="review-author">
              {reviewAuthor?.photoURI && (
                <img src={reviewAuthor.photoURI} alt="" loading="lazy" />
              )}
              <span>
                {reviewAuthor?.uri ? (
                  <a href={reviewAuthor.uri} target="_blank" rel="noreferrer">
                    {reviewAuthor.displayName}
                  </a>
                ) : reviewAuthor?.displayName ?? 'Google Mapsユーザー'}
                <small>
                  {review.rating != null ? `★ ${review.rating.toFixed(1)}` : ''}
                  {review.relativePublishTimeDescription
                    ? ` · ${review.relativePublishTimeDescription}`
                    : ''}
                </small>
              </span>
            </div>
            {review.text && <p>{review.text}</p>}
            {review.googleMapsURI && (
              <a href={review.googleMapsURI} target="_blank" rel="noreferrer">
                元の口コミをGoogle Mapsで表示 ↗
              </a>
            )}
          </blockquote>
        </section>
      )}

      <StreetViewPreview recommendation={recommendation} />

      {place.attributions?.length ? (
        <p className="place-attributions">
          情報提供: {place.attributions.map((attribution, index) => (
            <span key={`${attribution.provider}-${index}`}>
              {index > 0 && '、'}
              {attribution.providerURI ? (
                <a href={attribution.providerURI} target="_blank" rel="noreferrer">
                  {attribution.provider}
                </a>
              ) : attribution.provider}
            </span>
          ))}
        </p>
      ) : null}
    </aside>
  )
}
