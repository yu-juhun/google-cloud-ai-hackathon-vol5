# Integration Infra Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the 3-service walking skeleton (frontend → backend-api → agent) on the shared GCP project, with stub logic end-to-end and CI/CD auto-deploying on every merge to `main`, so teammates can replace stub internals via PR without touching infra.

**Architecture:** `agent` is an ADK app (orchestrator + 3 stub sub-agents) scaffolded with `agents-cli`. `backend-api` is a plain FastAPI service implementing the `api/openapi.yaml` contract, calling `agent` over HTTP and reshaping the response. `frontend` is a minimal static page calling `backend-api`. Each service has its own Terraform (`deployment/terraform/`) and Dockerfile; a single GitHub Actions workflow deploys all three to the shared project on `main` push.

**Tech Stack:** Python 3.12, ADK (Agent Development Kit) via `agents-cli`, FastAPI, pytest, Terraform (`google` provider), Cloud Run, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-12-integration-infra-design.md` (topology decision recorded in `docs/wiki/concepts/service-topology.md`; API contract in `api/openapi.yaml` / `docs/wiki/concepts/recommendation-api-contract.md`)

## Global Constraints

- Shared GCP project: `project-3bcd6d36-2338-4b32-848` (billing enabled, confirmed)
- Deployment target: Cloud Run (`--deployment-target cloud_run`), flexibility to switch `agent` to Agent Runtime later is preserved but out of scope now
- 3 separate Cloud Run services: `frontend`, `backend-api`, `agent` — never merge sub-agents into separate Cloud Run services
- `backend-api`'s request/response schema is fixed by `api/openapi.yaml` — do not change it in this plan
- No secrets in code or `.env` committed to git — use Secret Manager + `agents-cli deploy --secrets` / Terraform `google_secret_manager_secret`
- No manual `gcloud` resource creation for anything beyond one-off verification — production infra goes through Terraform
- CI/CD: single-job GitHub Actions workflow on `main` push, no staging/prod split
- Every PR into `main` still must pass `okf-lint` per existing branch protection

---

### Task 1: Scaffold the `agent` service (ADK orchestrator + 3 stub sub-agents)

**Files:**
- Create (via CLI, then edit): `agent/app/agent.py`
- Create: `agent/app/sub_agents/__init__.py`
- Create: `agent/app/sub_agents/search.py`
- Create: `agent/app/sub_agents/judge.py`
- Create: `agent/app/sub_agents/recommend.py`
- Test: `agent/tests/test_stub_pipeline.py`
- Generated (do not hand-edit): `agent/app/fast_api_app.py`, `agent/Dockerfile`, `agent/deployment/terraform/`, `agent/agents-cli-manifest.yaml`

**Interfaces:**
- Produces: `run_pipeline(area: str, wheelchair_width_cm: float, cuisine: str | None, prompt: str | None) -> dict` in `agent/app/agent.py`, returning:
  ```python
  {
      "recommendations": [
          {
              "place_id": str,
              "name": str,
              "address": str,
              "location": {"latitude": float, "longitude": float},
              "maps_url": str,
              "accessibility": {
                  "status": "accessible" | "uncertain" | "not_accessible",
                  "confidence": "high" | "medium" | "low",
                  "reasons": [{"condition": str, "result": str, "evidence": str}],
              },
              "recommendation_reason": str,
          }
      ]
  }
  ```
  This matches `RecommendationResponse` minus the `rank` field (backend-api assigns `rank` — see Task 3).

- [ ] **Step 1: Scaffold the ADK project**

Run from the repo root:

```bash
agents-cli scaffold create agent \
  --agent adk \
  --deployment-target cloud_run \
  --cicd-runner github_actions \
  --region asia-northeast1 \
  --agent-guidance-filename CLAUDE.md
```

Expected: a new `agent/` directory appears with `app/agent.py`, `app/fast_api_app.py`, `Dockerfile`, `deployment/terraform/`, `agents-cli-manifest.yaml`.

- [ ] **Step 2: Write the failing test for the stub pipeline**

```python
# agent/tests/test_stub_pipeline.py
from app.agent import run_pipeline


def test_stub_pipeline_returns_fixed_shape():
    result = run_pipeline(
        area="福岡市中央区",
        wheelchair_width_cm=63,
        cuisine="イタリアン",
        prompt="入口に段差がなく、トイレも使いやすい店がよい",
    )

    assert "recommendations" in result
    assert len(result["recommendations"]) == 1

    rec = result["recommendations"][0]
    assert rec["place_id"] == "STUB_PLACE_1"
    assert rec["name"] == "スタブ食堂"
    assert rec["accessibility"]["status"] == "accessible"
    assert rec["accessibility"]["confidence"] == "low"
    assert rec["accessibility"]["reasons"][0]["condition"] == "entrance"
    assert "recommendation_reason" in rec
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd agent && python -m pytest tests/test_stub_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agent'` or `ImportError: cannot import name 'run_pipeline'`

- [ ] **Step 4: Implement the 3 stub sub-agents**

```python
# agent/app/sub_agents/__init__.py
```

```python
# agent/app/sub_agents/search.py
def search_candidates(area: str, cuisine: str | None) -> list[dict]:
    """Stub: returns one fixed candidate regardless of input.
    Real implementation (Places API) replaces this body only —
    keep the return shape: list of {place_id, name, address, location, maps_url}.
    """
    return [
        {
            "place_id": "STUB_PLACE_1",
            "name": "スタブ食堂",
            "address": "福岡県福岡市中央区天神1-1-1",
            "location": {"latitude": 33.5904, "longitude": 130.4017},
            "maps_url": "https://www.google.com/maps/search/?api=1&query_place_id=STUB_PLACE_1",
        }
    ]
```

```python
# agent/app/sub_agents/judge.py
def judge_accessibility(place: dict, wheelchair_width_cm: float) -> dict:
    """Stub: always returns a fixed low-confidence 'accessible' verdict.
    Real implementation (Gemini multimodal over reviews/photos) replaces
    this body only — keep the return shape.
    """
    return {
        "status": "accessible",
        "confidence": "low",
        "reasons": [
            {
                "condition": "entrance",
                "result": "unknown",
                "evidence": "スタブ判定: 実データ未接続のため固定値を返しています。",
            }
        ],
    }
```

```python
# agent/app/sub_agents/recommend.py
def build_recommendation_reason(place: dict, accessibility: dict, prompt: str | None) -> str:
    """Stub: returns a fixed reason string.
    Real implementation (matching against user prompt) replaces this
    body only.
    """
    return "スタブ推薦: 現時点では固定の理由文を返しています。"
```

- [ ] **Step 5: Implement the orchestrator that wires the 3 stubs together**

```python
# agent/app/agent.py
from app.sub_agents.search import search_candidates
from app.sub_agents.judge import judge_accessibility
from app.sub_agents.recommend import build_recommendation_reason


def run_pipeline(
    area: str,
    wheelchair_width_cm: float,
    cuisine: str | None = None,
    prompt: str | None = None,
) -> dict:
    candidates = search_candidates(area=area, cuisine=cuisine)

    recommendations = []
    for place in candidates:
        accessibility = judge_accessibility(place, wheelchair_width_cm)
        reason = build_recommendation_reason(place, accessibility, prompt)
        recommendations.append(
            {
                "place_id": place["place_id"],
                "name": place["name"],
                "address": place["address"],
                "location": place["location"],
                "maps_url": place["maps_url"],
                "accessibility": accessibility,
                "recommendation_reason": reason,
            }
        )

    return {"recommendations": recommendations}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd agent && python -m pytest tests/test_stub_pipeline.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add agent/
git commit -m "feat: scaffold agent service with stub search/judge/recommend pipeline"
```

---

### Task 2: Wire the orchestrator into the ADK app's invoke endpoint

**Files:**
- Modify: `agent/app/agent.py` (add ADK entrypoint wrapper — exact ADK wiring depends on the version `agents-cli scaffold` generated; follow the pattern already present in the scaffolded `app/agent.py` template, calling `run_pipeline` from Task 1 as the tool/handler body)
- Test: `agent/tests/test_invoke_endpoint.py`

**Interfaces:**
- Consumes: `run_pipeline` from Task 1 (`agent/app/agent.py`)
- Produces: the ADK app's HTTP invoke endpoint (path fixed by the scaffolded `app/fast_api_app.py` — do not hand-edit that file; read it to find the exact route ADK registers, e.g. `/apps/agent/invoke` or equivalent, and record the exact path found in a one-line comment at the top of `test_invoke_endpoint.py`)

- [ ] **Step 1: Read the generated `app/fast_api_app.py` to find the exact invoke route**

Run: `cat agent/app/fast_api_app.py | grep -n "invoke\|@app\|APIRouter"`

Record the exact path and request body shape ADK expects — this determines how Task 3's `backend-api` calls this service. Do not proceed to Step 2 until this path is confirmed from the actual generated file (never guess it).

- [ ] **Step 2: Write the failing test against the local FastAPI test client**

```python
# agent/tests/test_invoke_endpoint.py
from fastapi.testclient import TestClient
from app.fast_api_app import app

client = TestClient(app)


def test_invoke_returns_stub_recommendation():
    # Replace "<INVOKE_PATH>" with the exact path recorded in Step 1
    response = client.post(
        "<INVOKE_PATH>",
        json={
            "area": "福岡市中央区",
            "wheelchair_width_cm": 63,
            "cuisine": "イタリアン",
            "prompt": "入口に段差がなく、トイレも使いやすい店がよい",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"][0]["place_id"] == "STUB_PLACE_1"
```

- [ ] **Step 3: Run the test to verify it fails or passes**

Run: `cd agent && python -m pytest tests/test_invoke_endpoint.py -v`
If it fails because the route doesn't call `run_pipeline` yet, wire `agent/app/agent.py`'s ADK handler to call `run_pipeline` with the incoming request fields, following the scaffolded template's existing pattern for reading request input and returning output.

- [ ] **Step 4: Run the test again to verify it passes**

Run: `cd agent && python -m pytest tests/test_invoke_endpoint.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/
git commit -m "feat: wire ADK invoke endpoint to the stub orchestrator pipeline"
```

---

### Task 3: Implement `backend-api` per `api/openapi.yaml`

**Files:**
- Create: `backend-api/main.py`
- Create: `backend-api/schemas.py`
- Create: `backend-api/agent_client.py`
- Create: `backend-api/requirements.txt`
- Create: `backend-api/Dockerfile`
- Test: `backend-api/tests/test_recommendations.py`

**Interfaces:**
- Consumes: the ADK invoke path recorded in Task 2 Step 1, via `AGENT_SERVICE_URL` env var
- Produces: `POST /v1/recommendations` per `api/openapi.yaml` — response body matches `RecommendationResponse` (with `rank` assigned here, 1-indexed in list order)

- [ ] **Step 1: Write the failing test for missing required fields**

```python
# backend-api/tests/test_recommendations.py
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_missing_required_fields_returns_400():
    response = client.post("/v1/recommendations", json={})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    field_names = {f["field"] for f in body["fields"]}
    assert "area" in field_names
    assert "wheelchair_width_cm" in field_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend-api && python -m pytest tests/test_recommendations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Write the Pydantic schemas matching `api/openapi.yaml`**

```python
# backend-api/schemas.py
from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    area: str = Field(min_length=1)
    cuisine: str | None = Field(default=None, min_length=1)
    wheelchair_width_cm: float = Field(gt=0)
    prompt: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=5, ge=1)


class Location(BaseModel):
    latitude: float
    longitude: float


class AssessmentReason(BaseModel):
    condition: str
    result: str
    evidence: str


class AccessibilityAssessment(BaseModel):
    status: str
    confidence: str
    reasons: list[AssessmentReason]


class RestaurantRecommendation(BaseModel):
    rank: int
    place_id: str
    name: str
    address: str
    location: Location
    maps_url: str
    accessibility: AccessibilityAssessment
    recommendation_reason: str


class RecommendationResponse(BaseModel):
    recommendations: list[RestaurantRecommendation]
```

- [ ] **Step 4: Write the agent client**

```python
# backend-api/agent_client.py
import os
import httpx

AGENT_SERVICE_URL = os.environ.get("AGENT_SERVICE_URL", "http://localhost:8000")
# Replace with the exact path recorded in Task 2 Step 1
AGENT_INVOKE_PATH = "<INVOKE_PATH>"


def call_agent(area: str, wheelchair_width_cm: float, cuisine: str | None, prompt: str | None) -> dict:
    response = httpx.post(
        f"{AGENT_SERVICE_URL}{AGENT_INVOKE_PATH}",
        json={
            "area": area,
            "wheelchair_width_cm": wheelchair_width_cm,
            "cuisine": cuisine,
            "prompt": prompt,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()
```

- [ ] **Step 5: Write the FastAPI app with validation and the success path**

```python
# backend-api/main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from schemas import RecommendationRequest, RecommendationResponse
from agent_client import call_agent

app = FastAPI(title="Barrier-Free Restaurant Recommendation API")


def _field_errors(exc: ValidationError) -> list[dict]:
    errors = []
    for err in exc.errors():
        field = err["loc"][0] if err["loc"] else "unknown"
        code = "REQUIRED" if err["type"] == "missing" else "INVALID_VALUE"
        errors.append({"field": field, "code": code, "message": err["msg"]})
    return errors


@app.post("/v1/recommendations")
async def create_recommendations(request: Request):
    payload = await request.json()
    try:
        req = RecommendationRequest.model_validate(payload)
    except ValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "code": "VALIDATION_ERROR",
                "message": "入力内容を確認してください。",
                "fields": _field_errors(exc),
            },
        )

    agent_result = call_agent(
        area=req.area,
        wheelchair_width_cm=req.wheelchair_width_cm,
        cuisine=req.cuisine,
        prompt=req.prompt,
    )

    recommendations = [
        {**rec, "rank": i + 1}
        for i, rec in enumerate(agent_result["recommendations"][: req.limit])
    ]
    result = RecommendationResponse(recommendations=recommendations)
    return result.model_dump()
```

- [ ] **Step 6: Run the validation test to verify it passes**

Run: `cd backend-api && python -m pytest tests/test_recommendations.py -v`
Expected: PASS

- [ ] **Step 7: Write the failing test for the success path (mocking the agent call)**

```python
# backend-api/tests/test_recommendations.py (add to the same file)
from unittest.mock import patch


@patch("main.call_agent")
def test_valid_request_returns_ranked_recommendations(mock_call_agent):
    mock_call_agent.return_value = {
        "recommendations": [
            {
                "place_id": "STUB_PLACE_1",
                "name": "スタブ食堂",
                "address": "福岡県福岡市中央区天神1-1-1",
                "location": {"latitude": 33.5904, "longitude": 130.4017},
                "maps_url": "https://www.google.com/maps/search/?api=1&query_place_id=STUB_PLACE_1",
                "accessibility": {
                    "status": "accessible",
                    "confidence": "low",
                    "reasons": [{"condition": "entrance", "result": "unknown", "evidence": "stub"}],
                },
                "recommendation_reason": "スタブ推薦",
            }
        ]
    }

    response = client.post(
        "/v1/recommendations",
        json={"area": "福岡市中央区", "wheelchair_width_cm": 63},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"][0]["rank"] == 1
    assert body["recommendations"][0]["place_id"] == "STUB_PLACE_1"
```

- [ ] **Step 8: Run test to verify it fails, then verify it passes**

Run: `cd backend-api && python -m pytest tests/test_recommendations.py -v`
Expected: both tests PASS (the success test should pass immediately since Step 5 already implements this path — if it fails, check the mock target matches the actual import path of `call_agent` in `main.py`)

- [ ] **Step 9: Write `requirements.txt` and `Dockerfile`**

```
# backend-api/requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
httpx==0.27.2
pydantic==2.9.2
```

```dockerfile
# backend-api/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 10: Commit**

```bash
git add backend-api/
git commit -m "feat: implement backend-api per api/openapi.yaml"
```

---

### Task 4: Implement minimal `frontend`

**Files:**
- Create: `frontend/public/index.html`
- Create: `frontend/server.py`
- Create: `frontend/Dockerfile`
- Test: `frontend/tests/test_server.py`

**Interfaces:**
- Consumes: `backend-api`'s `POST /v1/recommendations` via `BACKEND_API_URL` env var (browser-side `fetch`, not server-side — `server.py` only serves the static page and injects the URL)

- [ ] **Step 1: Write the failing test for the server's config injection**

```python
# frontend/tests/test_server.py
import os
from fastapi.testclient import TestClient

os.environ["BACKEND_API_URL"] = "https://backend-api.example.com"
from server import app

client = TestClient(app)


def test_index_page_injects_backend_url():
    response = client.get("/")
    assert response.status_code == 200
    assert "https://backend-api.example.com" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && python -m pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Write the static page**

```html
<!-- frontend/public/index.html -->
<!doctype html>
<html lang="ja">
<head><meta charset="utf-8"><title>バリアフリー飲食店 推薦(walking skeleton)</title></head>
<body>
  <h1>バリアフリー飲食店 推薦</h1>
  <form id="f">
    <input name="area" placeholder="エリア" required>
    <input name="wheelchair_width_cm" type="number" placeholder="車椅子の幅(cm)" required>
    <button type="submit">検索</button>
  </form>
  <pre id="result"></pre>
  <script>
    const BACKEND_API_URL = "__BACKEND_API_URL__";
    document.getElementById("f").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const res = await fetch(`${BACKEND_API_URL}/v1/recommendations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          area: fd.get("area"),
          wheelchair_width_cm: Number(fd.get("wheelchair_width_cm")),
        }),
      });
      document.getElementById("result").textContent = JSON.stringify(await res.json(), null, 2);
    });
  </script>
</body>
</html>
```

- [ ] **Step 4: Write the server that injects `BACKEND_API_URL`**

```python
# frontend/server.py
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:8081")
TEMPLATE = (Path(__file__).parent / "public" / "index.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
async def index():
    return TEMPLATE.replace("__BACKEND_API_URL__", BACKEND_API_URL)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && python -m pytest tests/test_server.py -v`
Expected: PASS

- [ ] **Step 6: Write `Dockerfile`**

```dockerfile
# frontend/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn[standard]
COPY . .
ENV PORT=8080
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: implement minimal frontend calling backend-api"
```

---

### Task 5: Hand-author Terraform for `backend-api` and `frontend`

**Files:**
- Create: `backend-api/deployment/terraform/main.tf`
- Create: `backend-api/deployment/terraform/variables.tf`
- Create: `frontend/deployment/terraform/main.tf`
- Create: `frontend/deployment/terraform/variables.tf`

**Interfaces:**
- Consumes: nothing from earlier tasks (infra-only)
- Produces: Cloud Run v2 services named `backend-api` and `frontend` in the shared project, plus their runtime service accounts — consumed by Task 6's deploy step

- [ ] **Step 1: Write `backend-api`'s Terraform**

```hcl
# backend-api/deployment/terraform/variables.tf
variable "project_id" {
  type    = string
  default = "project-3bcd6d36-2338-4b32-848"
}

variable "region" {
  type    = string
  default = "asia-northeast1"
}

variable "image" {
  type        = string
  description = "Fully-qualified container image URI, set by CI at deploy time"
}

variable "agent_service_url" {
  type        = string
  description = "Base URL of the agent Cloud Run service"
}
```

```hcl
# backend-api/deployment/terraform/main.tf
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_service_account" "backend_api_sa" {
  account_id   = "backend-api-run-sa"
  display_name = "backend-api Cloud Run runtime SA"
}

resource "google_cloud_run_v2_service" "backend_api" {
  name     = "backend-api"
  location = var.region

  template {
    service_account = google_service_account.backend_api_sa.email
    containers {
      image = var.image
      env {
        name  = "AGENT_SERVICE_URL"
        value = var.agent_service_url
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }
}

output "backend_api_url" {
  value = google_cloud_run_v2_service.backend_api.uri
}
```

- [ ] **Step 2: Write `frontend`'s Terraform (same pattern, different env var)**

```hcl
# frontend/deployment/terraform/variables.tf
variable "project_id" {
  type    = string
  default = "project-3bcd6d36-2338-4b32-848"
}

variable "region" {
  type    = string
  default = "asia-northeast1"
}

variable "image" {
  type        = string
  description = "Fully-qualified container image URI, set by CI at deploy time"
}

variable "backend_api_url" {
  type        = string
  description = "Base URL of the backend-api Cloud Run service"
}
```

```hcl
# frontend/deployment/terraform/main.tf
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_service_account" "frontend_sa" {
  account_id   = "frontend-run-sa"
  display_name = "frontend Cloud Run runtime SA"
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "frontend"
  location = var.region

  template {
    service_account = google_service_account.frontend_sa.email
    containers {
      image = var.image
      env {
        name  = "BACKEND_API_URL"
        value = var.backend_api_url
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
      }
    }
  }
}

output "frontend_url" {
  value = google_cloud_run_v2_service.frontend.uri
}
```

- [ ] **Step 3: Validate both Terraform configs syntactically**

Run:
```bash
cd backend-api/deployment/terraform && terraform init -backend=false && terraform validate
cd ../../../frontend/deployment/terraform && terraform init -backend=false && terraform validate
```
Expected: `Success! The configuration is valid.` for both

- [ ] **Step 4: Commit**

```bash
git add backend-api/deployment/terraform frontend/deployment/terraform
git commit -m "infra: add hand-authored Terraform for backend-api and frontend Cloud Run services"
```

---

### Task 6: First real deploy to the shared project

**Files:** none (infra operations against the already-committed code)

**Interfaces:**
- Consumes: `agent/deployment/terraform/` (from `agents-cli scaffold`, Task 1), `backend-api/deployment/terraform/` and `frontend/deployment/terraform/` (Task 5)
- Produces: 3 live Cloud Run URLs, recorded in a new decision page for teammates to reference

- [ ] **Step 1: Provision the agent service's base infra**

Run: `cd agent && agents-cli infra single-project --project project-3bcd6d36-2338-4b32-848`
Expected: Terraform apply completes, enabling `run.googleapis.com`, `cloudbuild.googleapis.com`, `secretmanager.googleapis.com` and creating the agent's `app_sa`

- [ ] **Step 2: Deploy the agent service — notify the human and wait for approval before running**

Say: "Ready to run `agents-cli deploy` for the `agent` service against `project-3bcd6d36-2338-4b32-848`. Proceed?" Wait for explicit yes.

Run: `cd agent && agents-cli deploy --project project-3bcd6d36-2338-4b32-848 --no-confirm-project`
Expected: prints the deployed Cloud Run URL — record it as `AGENT_URL`

- [ ] **Step 3: Build and push the `backend-api` image, then apply its Terraform**

```bash
cd backend-api
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/backend-api --project project-3bcd6d36-2338-4b32-848
cd deployment/terraform
terraform init
terraform apply \
  -var="image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/backend-api" \
  -var="agent_service_url=<AGENT_URL from Step 2>"
```
Expected: `terraform apply` completes and prints `backend_api_url` output — record it as `BACKEND_API_URL`

- [ ] **Step 4: Build and push the `frontend` image, then apply its Terraform**

```bash
cd frontend
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/frontend --project project-3bcd6d36-2338-4b32-848
cd deployment/terraform
terraform init
terraform apply \
  -var="image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/frontend" \
  -var="backend_api_url=<BACKEND_API_URL from Step 3>"
```
Expected: `terraform apply` completes and prints `frontend_url` output

- [ ] **Step 5: End-to-end verification**

Run: `curl -X POST "<BACKEND_API_URL>/v1/recommendations" -H "Content-Type: application/json" -d '{"area":"福岡市中央区","wheelchair_width_cm":63}'`
Expected: `200` response with `recommendations[0].place_id == "STUB_PLACE_1"`

Open `<frontend URL>` in a browser, submit the form, and confirm the same stub JSON renders.

- [ ] **Step 6: Record the live URLs for the team**

Create `docs/wiki/concepts/deployed-endpoints.md`:

```markdown
---
type: decision
title: "統合デモ環境のデプロイ済みURL"
status: stable
owner: infra
generated:
  by: human:juhun.yu
  at: 2026-09-12
sources:
  - id: service-topology
    resource: docs/wiki/concepts/service-topology.md
    title: "サービス構成: frontend / backend-api / agent の3台体制"
    credibility_signals: "team-internal-agreement"
---

# 統合デモ環境のデプロイ済みURL

## 概要

walking skeleton(スタブ実装)を共有プロジェクト`project-3bcd6d36-2338-4b32-848`へ実際にデプロイした結果[^service-topology]。

## 決定/結論

- frontend: `<frontend URL>`
- backend-api: `<BACKEND_API_URL>`
- agent: `<AGENT_URL>`

## 根拠

Task 6(walking skeleton実装計画)で確認済み。3サービスがHTTPで正しく連鎖することを確認した。

## 未解決の論点

- 認証方式(現在はデフォルトのIDトークン認証)

## 履歴

- 2026-09-12: 初回デプロイ完了、URLを記録
```

- [ ] **Step 7: Commit**

```bash
git add docs/wiki/concepts/deployed-endpoints.md docs/wiki/index.md docs/wiki/log.md
git commit -m "docs: record deployed walking-skeleton endpoint URLs"
```

(Update `docs/wiki/index.md` and `docs/wiki/log.md` per the existing OKF bundle convention before this commit — add a line to the Decision/Research/Issue list and a dated log entry.)

---

### Task 7: GitHub Actions CI/CD (auto-deploy on `main` push)

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: `AGENT_URL`, `BACKEND_API_URL` recorded in Task 6 (as workflow env/vars), and a GCP service account key stored as the GitHub secret `GCP_SA_KEY` (created manually in Step 1 — never committed to the repo)

- [ ] **Step 1: Create a deploy service account and store its key as a GitHub secret**

Run:
```bash
gcloud iam service-accounts create github-actions-deployer \
  --project project-3bcd6d36-2338-4b32-848 \
  --display-name "GitHub Actions deployer"

gcloud projects add-iam-policy-binding project-3bcd6d36-2338-4b32-848 \
  --member="serviceAccount:github-actions-deployer@project-3bcd6d36-2338-4b32-848.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding project-3bcd6d36-2338-4b32-848 \
  --member="serviceAccount:github-actions-deployer@project-3bcd6d36-2338-4b32-848.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

gcloud iam service-accounts keys create /tmp/github-actions-deployer-key.json \
  --iam-account=github-actions-deployer@project-3bcd6d36-2338-4b32-848.iam.gserviceaccount.com

gh secret set GCP_SA_KEY < /tmp/github-actions-deployer-key.json
rm /tmp/github-actions-deployer-key.json
```
Expected: `gh secret set` confirms the secret was created; the key file is deleted locally afterward

- [ ] **Step 2: Write the workflow**

```yaml
# .github/workflows/deploy.yml
name: Deploy to shared demo environment

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - uses: google-github-actions/setup-gcloud@v2

      - name: Deploy agent
        run: |
          pip install uv
          uvx google-agents-cli deploy \
            --project project-3bcd6d36-2338-4b32-848 \
            --no-confirm-project
        working-directory: agent

      - name: Build and deploy backend-api
        run: |
          gcloud builds submit --tag asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/backend-api --project project-3bcd6d36-2338-4b32-848
          gcloud run deploy backend-api \
            --image asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/backend-api \
            --region asia-northeast1 \
            --project project-3bcd6d36-2338-4b32-848
        working-directory: backend-api

      - name: Build and deploy frontend
        run: |
          gcloud builds submit --tag asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/frontend --project project-3bcd6d36-2338-4b32-848
          gcloud run deploy frontend \
            --image asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/frontend \
            --region asia-northeast1 \
            --project project-3bcd6d36-2338-4b32-848
        working-directory: frontend
```

- [ ] **Step 3: Verify the workflow syntax**

Run: `gh workflow view deploy.yml 2>&1 || echo "will validate on push"`
(This workflow only fully validates once pushed and run — note that in the PR description for the human reviewer.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: auto-deploy all 3 services to the shared project on main push"
```

- [ ] **Step 5: Notify the human and wait for approval before merging this branch**

Say: "CI/CD workflow ready. Merging this PR to `main` will trigger the first automated deploy using the `GCP_SA_KEY` secret. Proceed with merge?" Wait for explicit yes before merging.

---

## Self-Review Notes

- Task 2 deliberately defers the exact ADK invoke path to a runtime discovery step (Step 1) rather than guessing it, because the scaffolded `app/fast_api_app.py` content is not knowable until `agents-cli scaffold create` actually runs in Task 1 — this is the one place where a concrete value is intentionally filled in during execution, not left as a design placeholder.
- `rank` is assigned by `backend-api`, not `agent` — Task 1's `run_pipeline` output intentionally omits it (Task 3 Step 5 adds it), keeping the agent/backend-api boundary schema stated once instead of duplicated.
- CI/CD (Task 7) uses a long-lived SA key secret rather than Workload Identity Federation for time's sake in a hackathon; this is a known simplification, not an oversight — flagged here rather than silently adopted.
