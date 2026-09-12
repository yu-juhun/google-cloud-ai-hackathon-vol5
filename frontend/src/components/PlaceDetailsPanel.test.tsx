import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mockRecommendations } from '../api/mockData'
import { PlaceDetailsPanel } from './PlaceDetailsPanel'

const mapsMocks = vi.hoisted(() => {
  const fetchFields = vi.fn()
  const setPanoramaVisible = vi.fn()

  return {
    fetchFields,
    setPanoramaVisible,
    placesLibrary: {
      Place: class {
        fetchFields = fetchFields
      },
    },
    streetViewLibrary: {
      StreetViewService: class {
        getPanorama() {
          return Promise.resolve({ data: { location: { pano: 'test-panorama' } } })
        }
      },
      StreetViewPanorama: class {
        setVisible = setPanoramaVisible
      },
    },
  }
})

vi.mock('@vis.gl/react-google-maps', () => ({
  useMapsLibrary: (library: string) => {
    if (library === 'places') return mapsMocks.placesLibrary
    if (library === 'streetView') return mapsMocks.streetViewLibrary
    return null
  },
}))

const loadedPlace = {
  displayName: 'リタの農園',
  formattedAddress: '福岡県福岡市博多区築港本町13-6',
  rating: 4.2,
  userRatingCount: 321,
  nationalPhoneNumber: '092-555-1234',
  websiteURI: 'https://example.com/restaurant',
  googleMapsURI: 'https://maps.google.com/example',
  googleMapsLinks: null,
  regularOpeningHours: {
    weekdayDescriptions: ['月曜日: 11:00～20:00', '火曜日: 11:00～20:00'],
  },
  accessibilityOptions: {
    hasWheelchairAccessibleEntrance: true,
    hasWheelchairAccessibleSeating: null,
    hasWheelchairAccessibleRestroom: true,
    hasWheelchairAccessibleParking: false,
  },
  photos: [
    {
      getURI: () => 'https://example.com/photo.jpg',
      googleMapsURI: 'https://maps.google.com/photo',
      authorAttributions: [
        {
          displayName: 'Photo Author',
          uri: 'https://maps.google.com/author',
        },
      ],
    },
  ],
  reviews: [
    {
      rating: 4,
      text: '入口が広く、店員さんの案内が丁寧でした。',
      relativePublishTimeDescription: '1か月前',
      googleMapsURI: 'https://maps.google.com/review',
      authorAttribution: {
        displayName: 'Review Author',
        uri: 'https://maps.google.com/reviewer',
        photoURI: 'https://example.com/avatar.jpg',
      },
    },
  ],
  attributions: [],
}

describe('PlaceDetailsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mapsMocks.fetchFields.mockResolvedValue({ place: loadedPlace })
  })

  it('shows live place details, attribution links, accessibility and Street View', async () => {
    render(<PlaceDetailsPanel recommendation={mockRecommendations[0]} />)

    expect(
      await screen.findByLabelText('リタの農園のGoogle Maps掲載情報'),
    ).toBeInTheDocument()
    expect(screen.getByText('092-555-1234')).toBeInTheDocument()
    expect(screen.getByAltText('リタの農園のGoogle Maps掲載写真')).toHaveAttribute(
      'src',
      'https://example.com/photo.jpg',
    )
    expect(screen.getByText('Photo Author')).toHaveAttribute(
      'href',
      'https://maps.google.com/author',
    )
    expect(screen.getByText('Review Author')).toHaveAttribute(
      'href',
      'https://maps.google.com/reviewer',
    )
    expect(screen.getByText('入口が広く、店員さんの案内が丁寧でした。')).toBeInTheDocument()
    expect(screen.getByText('入口').closest('li')).toHaveTextContent('対応あり')

    await waitFor(() => {
      expect(
        screen.queryByText('ストリートビューを読み込んでいます…'),
      ).not.toBeInTheDocument()
    })
  })

  it('keeps the Google Maps link available when Place Details fails', async () => {
    mapsMocks.fetchFields.mockRejectedValue(new Error('Places unavailable'))
    render(<PlaceDetailsPanel recommendation={mockRecommendations[0]} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '店舗情報を取得できませんでした',
    )
    expect(screen.getByRole('link', { name: /Google Mapsで確認/ })).toHaveAttribute(
      'href',
      mockRecommendations[0].maps_url,
    )
  })
})
