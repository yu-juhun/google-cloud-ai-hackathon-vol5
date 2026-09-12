"""Public REST API that validates the frontend contract and calls the private agent."""

import os
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from pydantic import BaseModel, ConfigDict, Field


AGENT_URLS = [
    os.getenv("SEARCH_AGENT_URL", "").rstrip("/"),
    os.getenv("JUDGE_AGENT_URL", "").rstrip("/"),
    os.getenv("RECOMMEND_AGENT_URL", "").rstrip("/"),
]
app = FastAPI(title="Barrier-Free Restaurant Recommendation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOW_ORIGINS", "*").split(","),
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: str = Field(min_length=1)
    cuisine: str | None = Field(default=None, min_length=1)
    wheelchair_width_cm: float = Field(gt=0)
    prompt: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=5, ge=1)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    fields = []
    for error in exc.errors():
        location = [str(item) for item in error["loc"] if item != "body"]
        field = ".".join(location) or "request"
        missing = error["type"] == "missing"
        fields.append(
            {
                "field": field,
                "code": "REQUIRED" if missing else "INVALID_VALUE",
                "message": (
                    f"{field} を入力してください。"
                    if missing
                    else f"{field} の値が不正です。"
                ),
            }
        )
    return JSONResponse(
        status_code=400,
        content={
            "code": "VALIDATION_ERROR",
            "message": "入力内容を確認してください。",
            "fields": fields,
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "backend-api", "status": "healthy"}


@app.post("/v1/recommendations")
async def create_recommendations(request: RecommendationRequest) -> dict[str, Any]:
    if not all(AGENT_URLS):
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "agent URLs are not configured."},
        )

    payload: dict[str, Any] = request.model_dump()
    async with httpx.AsyncClient(timeout=30) as client:
        for agent_url in AGENT_URLS:
            token = id_token.fetch_id_token(GoogleAuthRequest(), agent_url)
            response = await client.post(
                f"{agent_url}/execute",
                headers={"Authorization": f"Bearer {token}"}, json=payload,
            )
            if response.is_error:
                return JSONResponse(status_code=502, content={
                    "code": "UPSTREAM_ERROR", "message": "agent service did not return a recommendation."
                })
            payload.update(response.json())
    return {"recommendations": payload["recommendations"]}
