import logging

from fastapi import FastAPI

app = FastAPI(title="video-agent")
logger = logging.getLogger(__name__)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
