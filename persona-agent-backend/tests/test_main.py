from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"service": "persona-agent-backend", "status": "healthy"}


def test_websocket_echoes_text_messages():
    with client.websocket_connect("/ws/converse") as websocket:
        websocket.send_json({"type": "ping"})
        data = websocket.receive_json()
        assert data == {"type": "echo", "payload": {"type": "ping"}}
