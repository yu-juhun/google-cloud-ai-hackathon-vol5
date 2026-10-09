# 体験画像グラウンディング + UI入口変更 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Veo video generation use the report's own generated scene image (not a generic avatar) as its grounding image, and move the feature's entry point from a standalone dropdown-based form into the already-open experience-story card the user picked.

**Architecture:** `backend/michibiki/michibiki/video.py`'s `create_video_job` already fetches the report row (`db.get_report`); the teammate's `experience_images.py` feature already persists `experience_image: {status, object_name, place_id, scene_kind}` inside that same report body when generation succeeded. Read that field first, fall back to the existing avatar-image path unchanged when it's absent/not ready. On the frontend, expose the already-existing `twin.report_id` value through `travelersFor` (it's silently dropped today), then render `VideoRequest` inline inside the "ALL EXPERIENCE NOTES" section's already-open story card instead of a separate section with its own report picker.

**Tech Stack:** FastAPI/Python (backend, existing), React (frontend, existing). No new dependencies, no new GCP IAM (backend's service account already has `roles/storage.objectUser` on the experience bucket via `infra/terraform/backend/experience-images.tf`).

**Spec:** No separate spec file — this plan's design was agreed directly with the user in conversation (summarized in Global Constraints below); there is no separate design doc to cross-check against.

## Global Constraints

- When `reports.body.experience_image.status == "ready"`, Veo must receive that image (downloaded from `EXPERIENCE_BUCKET` via `object_name`), not the avatar image.
- When `experience_image` is missing, or present but `status != "ready"` (e.g. `"failed"`, `"generating"`, or the key absent entirely), behavior must fall back to exactly the existing avatar-image logic — no regression for reports that never got a scene image.
- The experience image's real mime type is never persisted (`experience_images.py`'s metadata dict has no `mime_type` key) — default to `"image/png"` when using it, since this codebase's own `experience_images.generate` always requests `response_modalities=["IMAGE"]` from Gemini and in practice receives PNG; document this assumption with a one-line comment, don't silently guess without saying so.
- `report_text` grounding (`assessments[0].experience`) is already correct — do not change `_report_text`.
- The frontend's report picker (a `<select>` of all completed twins) is removed entirely — `VideoRequest` must only ever be shown for one already-chosen report at a time.
- No new backend test runner or frontend test runner is introduced — frontend changes are verified by `npm run build` plus manual reasoning against the real code (no test runner exists for `frontend/`, confirmed in an earlier plan on this same branch).

## Review Focus

- A report whose `experience_image` key is present but `status == "failed"` or `"generating"` (not just totally absent) — must still fall back to the avatar path, not crash or send a half-generated image.
- A report with `experience_image.status == "ready"` but whose `object_name` points to an object that no longer exists in the bucket (deleted, bucket lifecycle rule, etc.) — the download would raise; this should surface as the existing generic 502-ish failure path (caught by `create_video_job`'s existing `except Exception: db.update_video_job(..., "failed")`), not an unhandled 500 that leaves the job row stuck. (Already covered structurally by existing code wrapping the whole flow — pin it with a test for this task's new code path specifically.)
- Switching which story card is open (`openAgent` changes) while the video-request form is showing for the previous report — the form must reset/hide, not keep showing stale state for a report the user no longer has open.
- A report with no `experience_image` key at all (older missions created before the teammate's feature existed, or this plan's own backend not yet deployed when the mission ran) — must take the fallback path exactly like a present-but-not-ready one, not throw a `KeyError`.
- The video-request entry button appearing for a report whose avatar is ALSO not ready (no scene image AND no avatar) — must still show the existing "まずアバター画像の生成を完了してください。" 404 message when submitted, not a confusing new error about the missing experience image.

---

### Task 1: Prefer the experience image over the avatar in `create_video_job`

**Files:**
- Modify: `backend/michibiki/michibiki/video.py`
- Test: `backend/tests/test_video_router.py`

**Interfaces:**
- Produces: `_download_experience_image(experience_image: dict) -> bytes` (new helper, mirrors `_download_avatar_image`'s shape).
- Consumes: nothing new from other tasks — this task is self-contained.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_video_router.py`, right after the existing `_avatar_row` helper function:

```python
def _report_row_with_experience_image(status="ready"):
    row = _report_row()
    row["body"]["experience_image"] = {
        "status": status, "object_name": "experiences/mission-1/twin-1.image",
        "place_id": "place-1", "scene_kind": "experience",
    }
    return row
```

Then add these test functions, placed after `test_create_video_job_success`:

```python
@patch("michibiki.db.get_mission_profile", return_value=None)
@patch("michibiki.video._download_experience_image", return_value=b"fake-scene-bytes")
@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.get_report")
def test_create_video_job_prefers_ready_experience_image_over_avatar(
    mock_get_report, mock_update, mock_find_active, mock_create, mock_guard, mock_rpc, mock_download, mock_profile,
):
    mock_get_report.return_value = _report_row_with_experience_image(status="ready")
    mock_create.return_value = {"id": "job-1", "status": "queued"}
    mock_rpc.return_value = {"operation_name": "operations/abc123"}

    with patch("michibiki.db.find_latest_ready_avatar_set") as mock_find_avatar:
        response = client.post("/api/videos", json={
            "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
            "tone": "calm", "consent": True,
        }, headers=HEADERS)

    assert response.status_code == 200
    mock_download.assert_called_once_with(mock_get_report.return_value["body"]["experience_image"])
    mock_find_avatar.assert_not_called()
    body = mock_rpc.await_args.args[1]
    assert body["image_mime_type"] == "image/png"


@patch("michibiki.db.get_mission_profile", return_value=None)
@patch("michibiki.video._download_avatar_image", return_value=b"fake-avatar-bytes")
@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_latest_ready_avatar_set")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.get_report")
def test_create_video_job_falls_back_to_avatar_when_experience_image_not_ready(
    mock_get_report, mock_update, mock_find_active, mock_find_avatar, mock_create, mock_guard, mock_rpc, mock_download, mock_profile,
):
    mock_get_report.return_value = _report_row_with_experience_image(status="generating")
    mock_find_avatar.return_value = _avatar_row(mime_type="image/jpeg")
    mock_create.return_value = {"id": "job-1", "status": "queued"}
    mock_rpc.return_value = {"operation_name": "operations/abc123"}

    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
        "tone": "calm", "consent": True,
    }, headers=HEADERS)

    assert response.status_code == 200
    mock_download.assert_called_once()
    body = mock_rpc.await_args.args[1]
    assert body["image_mime_type"] == "image/jpeg"


@patch("michibiki.db.get_mission_profile", return_value=None)
@patch("michibiki.video._download_avatar_image", return_value=b"fake-avatar-bytes")
@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_latest_ready_avatar_set")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.get_report")
def test_create_video_job_falls_back_to_avatar_when_experience_image_key_absent(
    mock_get_report, mock_update, mock_find_active, mock_find_avatar, mock_create, mock_guard, mock_rpc, mock_download, mock_profile,
):
    mock_get_report.return_value = _report_row()  # no experience_image key at all
    mock_find_avatar.return_value = _avatar_row(mime_type="image/png")
    mock_create.return_value = {"id": "job-1", "status": "queued"}
    mock_rpc.return_value = {"operation_name": "operations/abc123"}

    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
        "tone": "calm", "consent": True,
    }, headers=HEADERS)

    assert response.status_code == 200
    mock_download.assert_called_once()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_video_router.py -v -k experience_image`
Expected: FAIL — `AttributeError: module 'michibiki.video' has no attribute '_download_experience_image'` (the new helper doesn't exist yet, so `@patch` fails to find it to patch).

- [ ] **Step 3: Implement the change in `video.py`**

Add `_download_experience_image` right after the existing `_download_avatar_image` function:

```python
def _download_experience_image(experience_image):
    # experience_images.py never persists the real mime type (its metadata dict
    # has status/place_id/prompt_version/scene_kind/object_name only) — default
    # to image/png, matching how it always requests response_modalities=["IMAGE"]
    # from Gemini and in practice receives PNG.
    bucket = storage.Client().bucket(os.environ["EXPERIENCE_BUCKET"])
    return bucket.blob(experience_image["object_name"]).download_as_bytes()
```

Replace the image-selection block inside `create_video_job` — find this existing code:

```python
    avatar_record = await asyncio.to_thread(db.find_latest_ready_avatar_set, owner)
    if not avatar_record:
        raise HTTPException(404, "まずアバター画像の生成を完了してください。")
    image_asset = avatar_record["assets"]["assets"][0]
    image_bytes = await asyncio.to_thread(_download_avatar_image, avatar_record)
```

Replace it with:

```python
    experience_image = report["body"].get("experience_image") or {}
    if experience_image.get("status") == "ready":
        image_bytes = await asyncio.to_thread(_download_experience_image, experience_image)
        image_mime_type = "image/png"
    else:
        avatar_record = await asyncio.to_thread(db.find_latest_ready_avatar_set, owner)
        if not avatar_record:
            raise HTTPException(404, "まずアバター画像の生成を完了してください。")
        image_asset = avatar_record["assets"]["assets"][0]
        image_bytes = await asyncio.to_thread(_download_avatar_image, avatar_record)
        image_mime_type = image_asset.get("mime_type", "image/png")
```

Then find the `video_rpc` call a few lines below it, which currently reads:

```python
    try:
        result = await video_rpc("/video-jobs", {
            "image_bytes_b64": base64.b64encode(image_bytes).decode("ascii"),
            "image_mime_type": image_asset.get("mime_type", "image/png"),
```

Change the `image_mime_type` line to use the new local variable instead of re-deriving it from `image_asset` (which no longer exists on the experience-image path):

```python
            "image_mime_type": image_mime_type,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_video_router.py -v -k experience_image`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `cd backend && uv run pytest -v`
Expected: PASS — every test in the backend suite, including the pre-existing `test_create_video_job_success` (which uses `_report_row()` with no `experience_image` key, so it must now take the fallback-to-avatar path and still pass unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/michibiki/michibiki/video.py backend/tests/test_video_router.py
git commit -m "feat: ground Veo video generation in the report's own scene image when ready"
```

---

### Task 2: Move the video-request entry point into the open experience-story card

**Files:**
- Modify: `frontend/src/trip-view.js`
- Modify: `frontend/src/VideoRequest.jsx`
- Modify: `frontend/src/main.jsx`

**Interfaces:**
- Consumes: `POST /api/videos` (existing, unchanged — Task 1 only changed server-side image selection, not the request/response shape), `WS /api/video-jobs/{job_id}/progress` (existing, unchanged).
- Produces: `travelersFor(...)`'s returned objects now include `report_id`; `VideoRequest({ reportId })` (prop renamed/changed from `{ twins }`).

No automated test for this task — `frontend/` has no test runner (confirmed in an earlier plan on this branch: `package.json` has no test script, no vitest/jest dependency). Verification is `npm run build` plus reading the real code paths touched, not TDD.

- [ ] **Step 1: Expose `report_id` on `travelersFor`'s returned objects**

In `frontend/src/trip-view.js`, find the `travelersFor` function's returned object (it currently starts with `id: twin?.id || i, name: ...`). Add a `report_id` field right after `id`:

```js
    return {
      id: twin?.id || i, report_id: twin?.report_id, name: `わたし ${i + 1}`, ordinal: i + 1,
```

(This is the only change to this function — `twin.report_id` already exists on the raw API data via `finish_mission`'s `twin["id"], twin["report_id"] = twin_id, report_id`; it was just never copied onto the object this function builds for React.)

- [ ] **Step 2: Simplify `VideoRequest.jsx` to take a single `reportId` instead of a `twins` array**

Replace the full contents of `frontend/src/VideoRequest.jsx` with:

```jsx
import { useEffect, useState } from 'react'
import { api, clientToken } from './api'
import './video-request.css'

const STYLES = [['cinematic', 'シネマティック'], ['long_take', 'ロングテイク'], ['narrated', 'ナレーション付き']]
const TONES = [['calm', '穏やかな'], ['dramatic', 'ドラマチックな'], ['relaxed', '落ち着いた']]

export default function VideoRequest({ reportId }) {
  const [feedback, setFeedback] = useState('')
  const [style, setStyle] = useState('cinematic')
  const [tone, setTone] = useState('calm')
  const [consent, setConsent] = useState(false)
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState('')
  const [videoUrl, setVideoUrl] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = async () => {
    if (!consent || submitting) return
    setSubmitting(true); setError('')
    try {
      const job = await api('/api/videos', { method: 'POST', body: { report_id: reportId, feedback, style, tone, consent } })
      setJobId(job.id); setStatus(job.status)
    } catch (err) { setError(err.message) }
    finally { setSubmitting(false) }
  }

  useEffect(() => {
    if (!jobId || videoUrl) return
    const origin = (import.meta.env.VITE_API_URL || window.MICHIBIKI_API_URL || '').replace(/\/$/, '')
    const wsUrl = origin.replace(/^http/, 'ws') + `/api/video-jobs/${jobId}/progress`
    const socket = new WebSocket(wsUrl)
    socket.onopen = () => socket.send(JSON.stringify({ type: 'hello', client_token: clientToken() }))
    socket.onmessage = event => {
      const message = JSON.parse(event.data)
      if (message.type === 'status') {
        setStatus(message.status)
        if (message.status === 'ready') setVideoUrl(message.video_url)
        if (message.status === 'failed') setError(message.message)
      }
    }
    socket.onerror = () => setError('動画の進行状況を取得できませんでした。')
    return () => socket.close()
  }, [jobId, videoUrl])

  return <section className="video-request">
    {!jobId && <>
      <label>フィードバック<textarea maxLength={500} value={feedback} onChange={e => setFeedback(e.target.value)} disabled={submitting} />
        <small>{feedback.length}/500</small></label>
      <label>動画スタイル<select value={style} onChange={e => setStyle(e.target.value)} disabled={submitting}>
        {STYLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>感情トーン<select value={tone} onChange={e => setTone(e.target.value)} disabled={submitting}>
        {TONES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label className="video-consent"><input type="checkbox" checked={consent} disabled={submitting}
        onChange={e => setConsent(e.target.checked)} />
        <span>あなたのアバター画像とこの体験談をもとに、Veoへ送信して動画を生成することに同意します。</span></label>
      <button type="button" className="journey-button" disabled={!consent || submitting} onClick={submit}>
        {submitting ? '依頼を送信中…' : '動画を作る →'}</button>
    </>}
    {jobId && !videoUrl && !error &&
      <p aria-live="polite">動画生成には数分かかります。生成依頼は保存されるので、ページを再読み込みしても続きから確認できます。(現在: {status})</p>}
    {videoUrl && <video controls src={videoUrl} />}
    {error && <p className="video-warning" role="alert">{error}</p>}
  </section>
}
```

(Only the report picker `<select>` and the `completedTwins` filtering are gone — the rest of the component, including the consent/style/tone/submit/WS-progress/video-playback behavior, is unchanged. `!reportId` is dropped from the submit button's `disabled` check since `reportId` is now always provided by the caller, never empty — the caller only renders this component once a report is actually chosen.)

- [ ] **Step 3: Wire the new entry point into `main.jsx`'s `Results` component**

First, add a reset-on-switch state. Find this line inside `Results`:

```js
  const [openAgent, setOpenAgent] = useState(agents[0])
```

Add a sibling state line right after it:

```js
  const [showVideoForm, setShowVideoForm] = useState(false)
```

Then find the story-grid buttons, which currently read:

```jsx
{agents.map(agent => <button key={agent.id} className={openAgent.id === agent.id ? 'selected' : ''} onClick={() => setOpenAgent(agent)}>
```

Change the `onClick` so switching cards also resets the video form (so it never shows stale state for the previously-open report):

```jsx
{agents.map(agent => <button key={agent.id} className={openAgent.id === agent.id ? 'selected' : ''} onClick={() => { setOpenAgent(agent); setShowVideoForm(false) }}>
```

Next, remove the standalone `story-video` section entirely. Find and delete this exact block (it sits between the `day-plan` section and the `tuning-section`):

```jsx
<section className="story-video"><div><p className="eyebrow">EXPERIENCE STORY / PREVIEW</p><h2>この一日を、<br />体験の物語で見る。</h2></div><VideoRequest twins={result.twins} /></section>
```

Finally, find the `open-story` article inside the `experience-stories` section:

```jsx
<article className="open-story"><img src={openAgent.detail.image} alt="" /><ExperienceReport agent={openAgent} /></article>
```

Replace it with a version that adds the entry button and conditionally renders `VideoRequest`:

```jsx
<article className="open-story"><img src={openAgent.detail.image} alt="" /><ExperienceReport agent={openAgent} />{openAgent.report_id && <>{!showVideoForm ? <button type="button" className="journey-button" onClick={() => setShowVideoForm(true)}>この体験を動画にする →</button> : <VideoRequest reportId={openAgent.report_id} />}</>}</article>
```

(`openAgent.report_id` is undefined while a twin is still loading/failed — the entry button is hidden in that case, consistent with the existing `ExperienceReport` component's own `if (!report) return ...` early-out for an incomplete agent.)

- [ ] **Step 4: Run the build to verify no syntax/import errors**

Run: `cd frontend && npm run build`
Expected: builds successfully (no errors), same as it did before this task's changes — compare against the build output from before this task to confirm no new warnings were introduced.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/trip-view.js frontend/src/VideoRequest.jsx frontend/src/main.jsx
git commit -m "feat: enter video generation from the open experience-story card, not a separate picker"
```
