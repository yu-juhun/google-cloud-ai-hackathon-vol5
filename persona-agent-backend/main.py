from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="persona-agent-backend")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "persona-agent-backend", "status": "healthy"}


@app.websocket("/ws/converse")
async def converse(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            await websocket.send_json({"type": "echo", "payload": data})
    except WebSocketDisconnect:
        pass
