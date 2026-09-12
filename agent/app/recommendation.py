"""Internal recommendation endpoint used by backend-api during infrastructure smoke tests."""

from hashlib import sha256
from urllib.parse import quote_plus

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field


router = APIRouter()


class RecommendationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: str = Field(min_length=1)
    cuisine: str | None = Field(default=None, min_length=1)
    wheelchair_width_cm: float = Field(gt=0)
    prompt: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=5, ge=1)


class AssessmentReason(BaseModel):
    condition: str
    result: str
    evidence: str


class AccessibilityAssessment(BaseModel):
    status: str
    confidence: str
    reasons: list[AssessmentReason]


class RestaurantRecommendation(BaseModel):
    rank: int
    place_id: str
    name: str
    address: str
    location: dict[str, float]
    maps_url: str
    accessibility: AccessibilityAssessment
    recommendation_reason: str


class RecommendationOutput(BaseModel):
    recommendations: list[RestaurantRecommendation]


@router.post("/recommend", response_model=RecommendationOutput)
async def recommend(request: RecommendationInput) -> RecommendationOutput:
    """Return a deterministic result until Places and Gemini are connected."""
    cuisine = request.cuisine or "飲食店"
    name = f"{request.area} バリアフリー {cuisine}"
    place_id = f"smoke-{sha256(name.encode()).hexdigest()[:16]}"
    maps_query = quote_plus(f"{request.area} {cuisine}")
    extra = f" 要望: {request.prompt}" if request.prompt else ""

    recommendation = RestaurantRecommendation(
        rank=1,
        place_id=place_id,
        name=name,
        address=request.area,
        location={"latitude": 33.5904, "longitude": 130.4017},
        maps_url=f"https://www.google.com/maps/search/?api=1&query={maps_query}",
        accessibility=AccessibilityAssessment(
            status="uncertain",
            confidence="low",
            reasons=[
                AssessmentReason(
                    condition="wheelchair_width_cm",
                    result="unknown",
                    evidence=(
                        f"車椅子の横幅 {request.wheelchair_width_cm:g}cm に対する"
                        "店舗の実測情報は、まだ取得していません。"
                    ),
                )
            ],
        ),
        recommendation_reason=(
            f"{request.area}で{cuisine}を探すための、外部情報連携前の検証用候補です。{extra}"
        ),
    )
    return RecommendationOutput(recommendations=[recommendation])
