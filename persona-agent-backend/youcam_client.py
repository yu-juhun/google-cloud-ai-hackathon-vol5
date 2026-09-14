# persona-agent-backend/youcam_client.py
"""Perfect Corp YouCam AI Avatar Generator client.

Auth flow, request/response shapes, and field names below were verified
against the real API on 2026-09-14 (see this plan's Task 2 header for the
exact verification notes) — the third-party OpenAPI mirror this was first
drafted from had the response envelope key wrong (documented "result",
actual "data" for every endpoint except /client/auth) and the task-create
param name wrong ("output_cnt" vs the real "output_count").
"""
import base64
import os
import time

import requests
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

BASE_URL = "https://yce-api-01.makeupar.com"
POLL_INTERVAL_SECONDS = 3
MAX_POLL_ATTEMPTS = 40


def _get_access_token() -> str:
    client_id = os.environ["PERFECTCORP_API_KEY"]
    public_key_b64 = os.environ["PERFECTCORP_API_SECRET"]

    public_key_der = base64.b64decode(public_key_b64)
    public_key = load_der_public_key(public_key_der)

    timestamp_ms = int(time.time() * 1000)
    payload = f"client_id={client_id}&timestamp={timestamp_ms}".encode()
    encrypted = public_key.encrypt(payload, padding.PKCS1v15())
    id_token = base64.b64encode(encrypted).decode()

    resp = requests.post(
        f"{BASE_URL}/s2s/v1.0/client/auth",
        json={"client_id": client_id, "id_token": id_token},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["result"]["access_token"]


def generate_base_avatar(
    photo_bytes: bytes,
    content_type: str,
    template_id: str = "female_manga_mood",
) -> tuple[bytes, str]:
    """Runs the full YouCam AI Avatar Generator flow synchronously and
    returns the generated avatar image bytes together with the actual
    Content-Type YouCam served them as (it serves JPEG, not PNG, despite
    the request photo possibly being PNG). Raises requests.HTTPError or
    RuntimeError (on task failure/timeout) rather than returning a
    sentinel — callers decide how to fall back."""
    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    file_resp = requests.post(
        f"{BASE_URL}/s2s/v2.0/file",
        headers=headers,
        json={"files": [{"content_type": content_type, "file_name": "photo", "file_size": len(photo_bytes)}]},
        timeout=15,
    )
    file_resp.raise_for_status()
    file_info = file_resp.json()["data"]["files"][0]
    file_id = file_info["file_id"]
    upload_req = file_info["requests"][0]

    upload_resp = requests.request(
        upload_req["method"],
        upload_req["url"],
        headers=upload_req.get("headers", {}),
        data=photo_bytes,
        timeout=30,
    )
    upload_resp.raise_for_status()

    task_resp = requests.post(
        f"{BASE_URL}/s2s/v2.0/task/ai-avatar",
        headers=headers,
        json={"src_file_id": file_id, "template_id": template_id, "output_count": 1},
        timeout=15,
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["data"]["task_id"]

    for _ in range(MAX_POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SECONDS)
        poll_resp = requests.get(f"{BASE_URL}/s2s/v2.0/task/ai-avatar/{task_id}", headers=headers, timeout=15)
        poll_resp.raise_for_status()
        poll_data = poll_resp.json()["data"]
        status = poll_data.get("task_status")
        if status == "success":
            result_url = poll_data["results"]["output"][0]["url"]
            image_resp = requests.get(result_url, timeout=30)
            image_resp.raise_for_status()
            content_type = image_resp.headers.get("Content-Type", "image/jpeg")
            return image_resp.content, content_type
        if status == "error":
            raise RuntimeError(f"YouCam ai-avatar task {task_id} failed: {poll_data}")

    raise RuntimeError(f"YouCam ai-avatar task {task_id} did not finish within {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS}s")
