from unittest.mock import MagicMock

import pytest

import youcam_client


@pytest.mark.parametrize("results", [None, {}, {"output": [{"url": "partial"}]}])
def test_pending_task_does_not_unpack_or_publish_partial_results(monkeypatch, results):
    response = MagicMock()
    response.json.return_value = {"data": {"task_status": "running", "results": results}}
    monkeypatch.setattr(youcam_client, "_get_access_token", lambda: "test-token")
    monkeypatch.setattr(youcam_client.requests, "get", lambda *args, **kwargs: response)
    assert youcam_client.avatar_task_status("test-task") == ("running", [])


def test_completed_task_returns_images(monkeypatch):
    outputs = [{"url": "https://example.com/image.jpg"}]
    response = MagicMock()
    response.json.return_value = {"data": {"task_status": "success", "results": {"output": outputs}}}
    monkeypatch.setattr(youcam_client, "_get_access_token", lambda: "test-token")
    monkeypatch.setattr(youcam_client.requests, "get", lambda *args, **kwargs: response)
    assert youcam_client.avatar_task_status("test-task") == ("success", outputs)
