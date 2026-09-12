import { useState, type FormEvent } from 'react'
import type { FieldError, RecommendationRequest } from '../api/types'

interface SearchFormProps {
  initialValue: RecommendationRequest
  isLoading: boolean
  fieldErrors: FieldError[]
  onSubmit: (request: RecommendationRequest) => void
}

export function SearchForm({
  initialValue,
  isLoading,
  fieldErrors,
  onSubmit,
}: SearchFormProps) {
  const [area, setArea] = useState(initialValue.area)
  const [cuisine, setCuisine] = useState(initialValue.cuisine ?? '')
  const [wheelchairWidth, setWheelchairWidth] = useState(
    String(initialValue.wheelchair_width_cm),
  )
  const [prompt, setPrompt] = useState(initialValue.prompt ?? '')

  const areaError = fieldErrors.find((error) => error.field === 'area')
  const wheelchairWidthError = fieldErrors.find(
    (error) => error.field === 'wheelchair_width_cm',
  )

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit({
      area: area.trim(),
      ...(cuisine.trim() ? { cuisine: cuisine.trim() } : {}),
      wheelchair_width_cm: Number(wheelchairWidth),
      ...(prompt.trim() ? { prompt: prompt.trim() } : {}),
      limit: 5,
    })
  }

  return (
    <form className="search-form" onSubmit={handleSubmit} noValidate>
      <div className="form-grid">
        <label className="field field--area">
          <span className="field-label">
            行きたいエリア
            <span className="required-mark" aria-hidden="true">*</span>
            {areaError && (
              <span className="label-error" id="area-error">
                {areaError.code === 'REQUIRED' ? '未入力' : '入力値を確認'}
              </span>
            )}
          </span>
          <span className="input-shell">
            <LocationIcon />
            <input
              name="area"
              required
              value={area}
              onChange={(event) => setArea(event.target.value)}
              aria-invalid={Boolean(areaError)}
              aria-describedby={areaError ? 'area-error' : undefined}
              placeholder="例：福岡市中央区"
            />
          </span>
        </label>

        <div className="field">
          <label htmlFor="cuisine">料理ジャンル</label>
          <input
            id="cuisine"
            name="cuisine"
            list="cuisine-options"
            value={cuisine}
            onChange={(event) => setCuisine(event.target.value)}
            placeholder="例：イタリアン"
          />
          <datalist id="cuisine-options">
            <option value="和食">和食</option>
            <option value="イタリアン">イタリアン</option>
            <option value="カフェ">カフェ</option>
            <option value="中華">中華</option>
          </datalist>
        </div>

        <label className="field">
          <span className="field-label">
            車いすの横幅
            <span className="required-mark" aria-hidden="true">*</span>
            {wheelchairWidthError && (
              <span className="label-error" id="wheelchair-error">
                {wheelchairWidthError.code === 'REQUIRED'
                  ? '未入力'
                  : '0より大きい値'}
              </span>
            )}
          </span>
          <span className="input-with-unit">
            <input
              name="wheelchair_width_cm"
              type="number"
              required
              inputMode="decimal"
              min="1"
              step="0.5"
              value={wheelchairWidth}
              onChange={(event) => setWheelchairWidth(event.target.value)}
              aria-invalid={Boolean(wheelchairWidthError)}
              aria-describedby={
                wheelchairWidthError ? 'wheelchair-error' : undefined
              }
            />
            <span>cm</span>
          </span>
        </label>

        <label className="field field--prompt">
          <span>ほかに大切なこと</span>
          <input
            name="prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="例：入口に段差がなく、トイレも使いやすい店"
          />
        </label>

        <button className="search-button" type="submit" disabled={isLoading}>
          <SearchIcon />
          {isLoading ? 'AIが確認しています…' : '行けるお店を探す'}
        </button>
      </div>
    </form>
  )
}

function LocationIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M12 21s7-6.1 7-12a7 7 0 1 0-14 0c0 5.9 7 12 7 12Z" />
      <circle cx="12" cy="9" r="2.4" />
    </svg>
  )
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m15.5 15.5 5 5" />
    </svg>
  )
}
