"""Places API backed restaurant search service."""
import os
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
app = FastAPI(title="search-agent")
FIELDS = "places.id,places.displayName,places.formattedAddress,places.location,places.googleMapsUri,places.reviews,places.photos,places.accessibilityOptions"
class Request(BaseModel):
    area: str = Field(min_length=1)
    cuisine: str | None = None
    wheelchair_width_cm: float = Field(gt=0)
    prompt: str | None = None
    limit: int = Field(default=5, ge=1, le=20)
@app.post('/execute')
async def execute(request: Request):
    key = os.environ.get('PLACES_API_KEY', '').strip()
    if not key: raise HTTPException(500, 'PLACES_API_KEY is not configured')
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post('https://places.googleapis.com/v1/places:searchText', headers={'X-Goog-Api-Key': key, 'X-Goog-FieldMask': FIELDS}, json={'textQuery': f"{request.area} {request.cuisine or '飲食店'}", 'languageCode': 'ja', 'pageSize': request.limit})
    if response.is_error: raise HTTPException(502, f'Places API error: {response.status_code}')
    candidates = []
    for p in response.json().get('places', []):
        loc = p.get('location', {})
        candidates.append({'place_id': p['id'], 'name': p.get('displayName', {}).get('text', ''), 'address': p.get('formattedAddress', ''), 'location': {'latitude': loc.get('latitude'), 'longitude': loc.get('longitude')}, 'maps_url': p.get('googleMapsUri', ''), 'reviews': [r.get('text', {}).get('text', '') for r in p.get('reviews', [])], 'photo_count': len(p.get('photos', [])), 'accessibility_options': p.get('accessibilityOptions', {})})
    return {'candidates': candidates}
