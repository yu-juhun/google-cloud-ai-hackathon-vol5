export const apiOrigin = (import.meta.env.VITE_API_URL || window.MICHIBIKI_API_URL || '').replace(/\/$/, '')
const origin = apiOrigin

export function clientToken() {
  let token = localStorage.getItem('michibiki-media-client')
  if (!token) { token = crypto.randomUUID(); localStorage.setItem('michibiki-media-client', token) }
  return token
}

export async function api(path, { method = 'GET', body } = {}) {
  if (!origin) throw new Error('実APIの接続先が未設定です。モック結果には切り替えません。')
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 255000)
  try {
    const response = await fetch(origin + path, {
      method, signal: controller.signal,
      headers: { 'X-Michibiki-Client': clientToken(), ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
    const data = await response.json()
    if (!response.ok) {
      const detail = data.detail
      const message = typeof detail === 'string' ? detail : detail?.message || `APIエラー (${response.status})`
      const error = new Error(message)
      error.missionId = detail?.mission_id
      throw error
    }
    return data
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('通信の待機期限を超えました。保存済みの結果を確認してください。')
    throw error
  } finally {
    clearTimeout(timer)
  }
}

export function serverProfile(profile) {
  const { chair, width, step, stamina, companion, home, notes, priorities } = profile
  return { chair, width: Number(width), step: Number(step), stamina: Number(stamina), companion,
    home: home === '出発地を設定してください' ? '' : home, notes, priorities }
}
