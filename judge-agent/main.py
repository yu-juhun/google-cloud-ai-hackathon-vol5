"""Gemini-backed accessibility judgement service."""
import json
from fastapi import FastAPI
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
app = FastAPI(title="judge-agent")
class Request(BaseModel):
    wheelchair_width_cm: float = Field(gt=0)
    candidates: list[dict]
@app.post('/execute')
def execute(request: Request):
    client = genai.Client(vertexai=True, project='storied-shelter-471306-a3', location='global')
    assessments = []
    for c in request.candidates:
        prompt = f"車椅子横幅{request.wheelchair_width_cm}cmで利用可否を、証拠だけで判定。JSONのみでstatus(accessible|uncertain|not_accessible),confidence(high|medium|low),evidence(日本語)を返す。証拠:{json.dumps({'reviews':c.get('reviews', []),'photo_count':c.get('photo_count',0),'accessibility_options':c.get('accessibility_options',{})}, ensure_ascii=False)}"
        result = json.loads(client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=types.GenerateContentConfig(response_mime_type='application/json')).text)
        assessments.append({'place_id': c['place_id'], 'status': result['status'], 'confidence': result['confidence'], 'reasons': [{'condition':'wheelchair_width_cm','result':result['status'],'evidence':result['evidence']}]})
    return {'candidates': request.candidates, 'assessments': assessments}
