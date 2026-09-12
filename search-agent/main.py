"""ADK-backed stage service; AGENT_ROLE selects search, judge, or recommend."""

import os
from hashlib import sha256
from urllib.parse import quote_plus

from fastapi import FastAPI
from google.adk.agents import Agent
from pydantic import BaseModel, Field

ROLE = os.getenv("AGENT_ROLE", "search")
adk_agent = Agent(name=f"{ROLE}_agent", model="gemini-3.7-flash", instruction=f"You are the {ROLE} stage.")
app = FastAPI(title=f"{ROLE}-agent")

class Request(BaseModel):
    area: str = Field(min_length=1)
    cuisine: str | None = None
    wheelchair_width_cm: float = Field(gt=0)
    prompt: str | None = None
    candidate: dict | None = None
    assessment: dict | None = None

@app.get('/health')
def health(): return {'service': f'{ROLE}-agent', 'status': 'healthy'}

@app.post('/execute')
def execute(request: Request):
    cuisine = request.cuisine or '飲食店'
    candidate = request.candidate or {
        'place_id': f"smoke-{sha256(f'{request.area}:{cuisine}'.encode()).hexdigest()[:16]}",
        'name': f'{request.area} バリアフリー {cuisine}', 'address': request.area,
        'location': {'latitude': 33.5904, 'longitude': 130.4017},
        'maps_url': f"https://www.google.com/maps/search/?api=1&query={quote_plus(f'{request.area} {cuisine}')}"
    }
    if ROLE == 'search': return {'candidate': candidate}
    assessment = request.assessment or {'status': 'uncertain', 'confidence': 'low', 'reasons': [{'condition': 'wheelchair_width_cm', 'result': 'unknown', 'evidence': f'車椅子の横幅 {request.wheelchair_width_cm:g}cm に対する店舗の実測情報は、まだ取得していません。'}]}
    if ROLE == 'judge': return {'candidate': candidate, 'assessment': assessment}
    extra = f' 要望: {request.prompt}' if request.prompt else ''
    return {'recommendations': [{**candidate, 'rank': 1, 'accessibility': assessment, 'recommendation_reason': f'{request.area}で{cuisine}を探すための、外部情報連携前の検証用候補です。{extra}'}]}
