import type { RestaurantRecommendation } from './types'

// 実在店舗のアクセシビリティ情報と誤解されないよう、すべて架空の名称にする。
export const mockRecommendations: RestaurantRecommendation[] = [
  {
    rank: 1,
    place_id: 'mock-tenjin-table',
    name: '天神みんなのテーブル',
    address: '福岡県福岡市中央区天神1丁目（デモ用）',
    location: { latitude: 33.5906, longitude: 130.4019 },
    maps_url:
      'https://www.google.com/maps/search/?api=1&query=%E5%A4%A9%E7%A5%9E',
    accessibility: {
      status: 'accessible',
      confidence: 'high',
      reasons: [
        {
          condition: 'entrance',
          result: 'supported',
          evidence: '入口は歩道からフラットで、自動ドアの写真を確認できました。',
        },
        {
          condition: 'aisle',
          result: 'supported',
          evidence: '店内通路は約90cmあり、63cm幅の車いすで通行できる見込みです。',
        },
        {
          condition: 'restroom',
          result: 'supported',
          evidence: '車いす対応トイレの設備情報があります。',
        },
      ],
    },
    recommendation_reason:
      '入口・通路・トイレの3項目で利用しやすい根拠が揃っており、ご希望に最も近い候補です。',
  },
  {
    rank: 2,
    place_id: 'mock-hakata-kitchen',
    name: '博多よりみちキッチン',
    address: '福岡県福岡市博多区博多駅中央街（デモ用）',
    location: { latitude: 33.5898, longitude: 130.4207 },
    maps_url:
      'https://www.google.com/maps/search/?api=1&query=%E5%8D%9A%E5%A4%9A%E9%A7%85',
    accessibility: {
      status: 'uncertain',
      confidence: 'medium',
      reasons: [
        {
          condition: 'entrance',
          result: 'supported',
          evidence: 'ビル入口にはスロープがあるというレビューを確認しました。',
        },
        {
          condition: 'aisle',
          result: 'unknown',
          evidence: 'テーブル間の通路幅を判断できる情報が見つかりませんでした。',
        },
        {
          condition: 'restroom',
          result: 'unknown',
          evidence: '店内トイレの広さは確認できていません。',
        },
      ],
    },
    recommendation_reason:
      '入口は利用できる可能性がありますが、通路幅とトイレは来店前の確認をおすすめします。',
  },
  {
    rank: 3,
    place_id: 'mock-daimyo-bistro',
    name: '大名こみちビストロ',
    address: '福岡県福岡市中央区大名2丁目（デモ用）',
    location: { latitude: 33.5879, longitude: 130.3952 },
    maps_url:
      'https://www.google.com/maps/search/?api=1&query=%E7%A6%8F%E5%B2%A1%E5%B8%82%E5%A4%A7%E5%90%8D',
    accessibility: {
      status: 'not_accessible',
      confidence: 'high',
      reasons: [
        {
          condition: 'entrance',
          result: 'unsupported',
          evidence: '入口前に2段の階段があり、スロープは確認できませんでした。',
        },
        {
          condition: 'aisle',
          result: 'unknown',
          evidence: '店内の通路幅を判断できる情報がありません。',
        },
      ],
    },
    recommendation_reason:
      '入口の階段を越える手段が確認できないため、現状では入店が難しい見込みです。',
  },
]
