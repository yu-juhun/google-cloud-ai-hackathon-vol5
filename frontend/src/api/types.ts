import type { components } from './schema'

/** `api/openapi.yaml` から生成した型に、画面用の短い別名を付ける。 */
export type RecommendationRequest = components['schemas']['RecommendationRequest']
export type RecommendationResponse = components['schemas']['RecommendationResponse']
export type RestaurantRecommendation = components['schemas']['RestaurantRecommendation']
export type AccessibilityAssessment = components['schemas']['AccessibilityAssessment']
export type AssessmentReason = components['schemas']['AssessmentReason']
export type Location = components['schemas']['Location']
export type ValidationError = components['schemas']['ValidationError']
export type FieldError = components['schemas']['FieldError']

export type AccessibilityStatus = AccessibilityAssessment['status']
export type Confidence = AccessibilityAssessment['confidence']
export type AssessmentResult = AssessmentReason['result']
