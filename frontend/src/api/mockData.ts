import type { RestaurantRecommendation } from './types'

// 店舗名・住所・座標・Place IDは、2026-09-12時点のPlaces API掲載情報を使用する。
// 入店可否と推薦理由はデモ用の判定であり、最新状況は店舗への確認を前提とする。
export const mockRecommendations: RestaurantRecommendation[] = [
  {
    rank: 1,
    place_id: 'ChIJq_z8lPGRQTURbZkTEIGlpQs',
    name: 'リタの農園',
    address: '福岡県福岡市博多区築港本町13-6 1F',
    location: { latitude: 33.6033538, longitude: 130.3993869 },
    maps_url:
      'https://www.google.com/maps/search/?api=1&query=%E3%83%AA%E3%82%BF%E3%81%AE%E8%BE%B2%E5%9C%92&query_place_id=ChIJq_z8lPGRQTURbZkTEIGlpQs',
    accessibility: {
      status: 'accessible',
      confidence: 'medium',
      reasons: [
        {
          condition: 'entrance',
          result: 'supported',
          evidence: 'Google Mapsの掲載属性で、車いす対応の入口ありとされています。',
        },
        {
          condition: 'restroom',
          result: 'supported',
          evidence: 'Google Mapsの掲載属性で、車いす対応トイレありとされています。',
        },
        {
          condition: 'parking',
          result: 'supported',
          evidence: 'Google Mapsの掲載属性で、車いす対応駐車場ありとされています。',
        },
        {
          condition: 'aisle',
          result: 'unknown',
          evidence: '店内の通路幅と座席周辺の寸法は確認できていません。',
        },
      ],
    },
    recommendation_reason:
      '入口・トイレ・駐車場の対応情報があります。通路幅は未確認のため、来店前の確認をおすすめします。',
  },
  {
    rank: 2,
    place_id: 'ChIJubcxBKuRQTURl9Rk1qtIEB0',
    name: 'パックスロマーナ',
    address: '福岡県福岡市中央区天神3-7-3 タワーズ天神 6F/7F',
    location: { latitude: 33.5936495, longitude: 130.3957651 },
    maps_url:
      'https://www.google.com/maps/search/?api=1&query=%E3%83%91%E3%83%83%E3%82%AF%E3%82%B9%E3%83%AD%E3%83%9E%E3%83%BC%E3%83%8A&query_place_id=ChIJubcxBKuRQTURl9Rk1qtIEB0',
    accessibility: {
      status: 'uncertain',
      confidence: 'medium',
      reasons: [
        {
          condition: 'entrance',
          result: 'supported',
          evidence: 'Google Mapsの掲載属性で、車いす対応の入口ありとされています。',
        },
        {
          condition: 'seating',
          result: 'supported',
          evidence: 'Google Mapsの掲載属性で、車いす対応の座席ありとされています。',
        },
        {
          condition: 'restroom',
          result: 'unsupported',
          evidence: 'Google Mapsの掲載属性では、車いす対応トイレなしとされています。',
        },
      ],
    },
    recommendation_reason:
      '入口と座席は対応情報がありますが、トイレは希望条件に合わない可能性があるため事前確認が必要です。',
  },
  {
    rank: 3,
    place_id: 'ChIJ78dm0oeRQTURvB4gHDXNJ7A',
    name: 'Ristorante fanfare',
    address: '福岡県福岡市中央区大名2-10-39 サンマリノビル 2F',
    location: { latitude: 33.5901856, longitude: 130.3929018 },
    maps_url:
      'https://www.google.com/maps/search/?api=1&query=Ristorante%20fanfare&query_place_id=ChIJ78dm0oeRQTURvB4gHDXNJ7A',
    accessibility: {
      status: 'not_accessible',
      confidence: 'high',
      reasons: [
        {
          condition: 'entrance',
          result: 'unsupported',
          evidence: 'Google Mapsの掲載属性では、車いす対応の入口なしとされています。',
        },
        {
          condition: 'seating',
          result: 'unsupported',
          evidence: 'Google Mapsの掲載属性では、車いす対応の座席なしとされています。',
        },
        {
          condition: 'restroom',
          result: 'unknown',
          evidence: '車いす対応トイレについては掲載情報を確認できていません。',
        },
      ],
    },
    recommendation_reason:
      '入口と座席の対応が確認できないため、現在の公開情報では利用が難しい見込みです。',
  },
]
