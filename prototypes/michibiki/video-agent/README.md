# video-agent

Stateless Cloud Run service wrapping the Veo API for michibiki's体験動画生成.
Never touches Cloud SQL — `backend/michibiki` owns all persistence and polls
this service's `/video-jobs/{operation_name}/status` on demand (see
`docs/superpowers/specs/2026-10-05-michibiki-video-generation-design.md`
and its implementation plan for why).

## Local run

```sh
cp .env.example .env   # fill in VERTEX_PROJECT_ID
pip install -r requirements.txt
set -a; source .env; set +a
uvicorn main:app --reload --port 8080
```
