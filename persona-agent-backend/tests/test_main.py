from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"service": "persona-agent-backend", "status": "healthy"}


# NOTE: the previous echo-based test_websocket_echoes_text_messages test was
# removed in Task 6. The /ws/converse handler now wires a real
# LiveConversation (Gemini Live API session) instead of echoing messages
# back, so that behavior no longer applies. See tests/test_live_session.py
# for coverage of LiveConversation itself; the handler's wiring is
# exercised end-to-end only via the human voice smoke test (brief Step 7),
# since it requires a live Gemini Live connection.
