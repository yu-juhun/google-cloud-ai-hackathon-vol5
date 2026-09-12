"""Gemini-backed recommendation service."""
import json
import os
from fastapi import FastAPI
from google import genai
from google.genai import types
from pydantic import BaseModel
app = FastAPI(title="recommend-agent")
class Request(BaseModel):
    candidates: list[dict]
    assessments: list[dict]
    prompt: str | None = None
@app.post('/execute')
def execute(request: Request):
    client = genai.Client(vertexai=True, project=os.environ['VERTEX_PROJECT_ID'], location=os.environ.get('VERTEX_LOCATION', 'global'))
    p = f"車椅子利用者向けに候補を順位づける。JSONのみでordered_place_idsとreasons(place_idをキー、短い日本語理由)を返す。候補:{json.dumps(request.candidates, ensure_ascii=False)} 判定:{json.dumps(request.assessments, ensure_ascii=False)} 要望:{request.prompt or ''}"
    answer = json.loads(client.models.generate_content(model='gemini-2.5-flash', contents=p, config=types.GenerateContentConfig(response_mime_type='application/json')).text)
    places, assessments = {c['place_id']:c for c in request.candidates}, {a['place_id']:a for a in request.assessments}
    out=[]
    for rank, pid in enumerate(answer['ordered_place_ids'], 1):
        if pid in places:
            c,a=places[pid],assessments[pid]
            out.append({'rank':rank,'place_id':pid,'name':c['name'],'address':c['address'],'location':c['location'],'maps_url':c['maps_url'],'accessibility':{'status':a['status'],'confidence':a['confidence'],'reasons':a['reasons']},'recommendation_reason':answer['reasons'].get(pid,'')})
    return {'recommendations':out}
