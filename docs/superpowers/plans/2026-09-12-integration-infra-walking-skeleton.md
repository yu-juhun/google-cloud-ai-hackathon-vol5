# Integration Infra Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get the 5-service system (frontend, backend-api, search-agent, judge-agent, recommend-agent) deployed to the shared GCP project with CI/CD auto-deploying on every merge to `main`. This plan is infra-only — application code for all 5 services comes from teammates' own PRs, not from this plan.

**Architecture:** Teammates are implementing the application code directly: `frontend` (React/Vite, merged in PR #11) and `backend-api` + `search-agent` + `judge-agent` + `recommend-agent` (plain FastAPI, no ADK scaffold, in PR #12 as of this writing) both use hand-rolled Dockerfiles, not `agents-cli`-generated ones. This plan hand-authors Terraform for all 5 Cloud Run services, adds the one missing piece (`frontend` has no Dockerfile yet — Vite builds a static SPA, so it needs a static-file-serving container), and wires a single GitHub Actions workflow that deploys all five to the shared project on `main` push.

**Tech Stack:** Terraform (`google` provider), Docker (nginx for the static frontend), Cloud Run, GitHub Actions, `gcloud`.

**Spec:** `docs/superpowers/specs/2026-09-12-integration-infra-design.md` (topology decision recorded in `docs/wiki/concepts/service-topology.md`; API contract in `api/openapi.yaml` / `docs/wiki/concepts/recommendation-api-contract.md`)

## Global Constraints

- Shared GCP project: `project-3bcd6d36-2338-4b32-848` (billing enabled, confirmed)
- Deployment target: Cloud Run for all 5 services
- 5 separate Cloud Run services: `frontend`, `backend-api`, `search-agent`, `judge-agent`, `recommend-agent`
- **This plan does not write or modify any application logic** in `frontend/`, `backend-api/`, `search-agent/`, `judge-agent/`, or `recommend-agent/` beyond adding a missing Dockerfile for `frontend`. Teammates own that code via their own PRs (frontend: PR #11, merged; backend-api + 3 agents: PR #12, open as of this writing).
- `backend-api`'s request/response schema is fixed by `api/openapi.yaml` — this plan never touches it
- `search-agent`/`judge-agent`/`recommend-agent` currently share an identical `main.py` differentiated by the `AGENT_ROLE` env var (per PR #12) — Terraform must set this env var per service
- Auth between `backend-api` and each agent uses Cloud Run ID tokens (already implemented in PR #12's `backend-api/main.py` via `google.auth.transport.requests` + `google.oauth2.id_token`) — Terraform must grant each agent's Cloud Run service the `roles/run.invoker` binding for `backend-api`'s service account, and each Cloud Run service must default to `--no-allow-unauthenticated` (the private agents) except `frontend` and `backend-api` which the public needs to reach
- No secrets in code or `.env` committed to git — use Secret Manager
- No manual `gcloud` resource creation for anything beyond one-off verification — production infra goes through Terraform
- CI/CD: single-job GitHub Actions workflow on `main` push, no staging/prod split
- Every PR into `main` still must pass `okf-lint` per existing branch protection
- **Dependency: PR #12 must be merged to `main` before Task 3 (first real deploy) can run** — Task 0, 1, and 2 do not require it and can proceed now
- Terraform state for the shared project is stored remotely in a GCS bucket (not locally) so any teammate can run `terraform apply` and see the same state — bootstrapped once in Task 0
- The bucket + Artifact Registry repo + API-enablement in Task 0 are bootstrapped via plain `gcloud`/`gsutil`, not Terraform — this is the one intentional exception to the "no manual gcloud, infra goes through Terraform" rule, because the Terraform remote-state backend cannot itself be created by the Terraform it will store state for

---

### Task 0: Phase-independent prerequisites

These don't depend on any other task and don't get blocked by anything — do this first so every later task has what it needs already in place.

**Files:**
- Create: `infra/terraform/backend.tf`

**Interfaces:**
- Produces: a GCS bucket for Terraform remote state, an Artifact Registry repo for built images, and the GCP APIs every later task calls — consumed by Task 2 (`backend.tf`) and Task 3/4 (`gcloud builds submit` target repo)

- [ ] **Step 1: Enable required GCP APIs**

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  --project project-3bcd6d36-2338-4b32-848
```
Expected: command completes with no error (each API may already be enabled — that's fine, `enable` is idempotent)

- [ ] **Step 2: Create the GCS bucket for Terraform remote state**

```bash
gcloud storage buckets create gs://project-3bcd6d36-2338-4b32-848-tfstate \
  --project project-3bcd6d36-2338-4b32-848 \
  --location asia-northeast1 \
  --uniform-bucket-level-access
```
Expected: bucket created. If it already exists (`ServiceException: 409`), that's fine — treat as already-satisfied, not an error.

- [ ] **Step 3: Create the Artifact Registry repo for built images**

```bash
gcloud artifacts repositories create cloud-run-source-deploy \
  --project project-3bcd6d36-2338-4b32-848 \
  --location asia-northeast1 \
  --repository-format docker
```
Expected: repo created. If it already exists (`ALREADY_EXISTS`), that's fine.

- [ ] **Step 4: Write `infra/terraform/backend.tf`**

```hcl
# infra/terraform/backend.tf
terraform {
  backend "gcs" {
    bucket = "project-3bcd6d36-2338-4b32-848-tfstate"
    prefix = "walking-skeleton"
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add infra/terraform/backend.tf
git commit -m "infra: bootstrap GCS remote state bucket and Artifact Registry repo"
```

Note: this task creates real cloud resources immediately (the bucket, the Artifact Registry repo, API enablement) — these are idempotent, low-risk, additive operations (nothing is deleted or overwritten). The human has already approved running this task (2026-09-12).

---

### Task 1: Add a Cloud Run Dockerfile for `frontend`

`frontend/` (PR #11) is a Vite-built static SPA with no Dockerfile — `npm run build` produces static files in `frontend/dist/`. Cloud Run needs a container that serves those files; nginx is the standard minimal choice.

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`
- Test: manual verification (Step 3) — a Dockerfile has no unit-test surface, so this task's "test" is building and running the container locally

**Interfaces:**
- Consumes: `frontend/package.json`'s existing `npm run build` script (produces `frontend/dist/`)
- Produces: a container serving the built SPA on `$PORT` (Cloud Run's required convention), consumed by Task 2's Terraform `image` variable

- [ ] **Step 1: Write the multi-stage Dockerfile**

```dockerfile
# frontend/Dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
ENV PORT=8080
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 2: Write the nginx config template (Cloud Run injects `$PORT` at runtime)**

```nginx
# frontend/nginx.conf
server {
    listen ${PORT};
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 3: Build and run the container locally to verify it serves the SPA**

Run:
```bash
cd frontend
docker build -t frontend-local .
docker run --rm -p 8080:8080 -e PORT=8080 frontend-local &
sleep 2
curl -s http://localhost:8080/ | grep -o "<title>.*</title>"
docker stop $(docker ps -q --filter ancestor=frontend-local)
```
Expected: the `curl` output shows the page's `<title>` tag (confirms nginx served `index.html`, not a 404)

- [ ] **Step 4: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf
git commit -m "infra: add Cloud Run Dockerfile for the frontend static build"
```

---

### Task 2: Hand-author Terraform for all 5 Cloud Run services

**Files:**
- Create: `infra/terraform/main.tf`
- Create: `infra/terraform/variables.tf`
- Create: `infra/terraform/outputs.tf`

A single shared Terraform root (not one `deployment/terraform/` per service) is simplest here: none of the 5 services have their own Terraform yet, all 5 belong to the same shared project, and a single root avoids 5 copies of the same provider/project boilerplate.

**Interfaces:**
- Consumes: nothing from earlier tasks except Task 1's `frontend/Dockerfile` existing (referenced only by path, not by content)
- Produces: 5 Cloud Run v2 services and their service accounts + IAM bindings, consumed by Task 3's deploy step

- [ ] **Step 1: Write `variables.tf`**

```hcl
# infra/terraform/variables.tf
variable "project_id" {
  type    = string
  default = "project-3bcd6d36-2338-4b32-848"
}

variable "region" {
  type    = string
  default = "asia-northeast1"
}

variable "frontend_image" {
  type        = string
  description = "Fully-qualified container image URI for frontend, set by CI at deploy time"
}

variable "backend_api_image" {
  type        = string
  description = "Fully-qualified container image URI for backend-api, set by CI at deploy time"
}

variable "search_agent_image" {
  type        = string
  description = "Fully-qualified container image URI for search-agent, set by CI at deploy time"
}

variable "judge_agent_image" {
  type        = string
  description = "Fully-qualified container image URI for judge-agent, set by CI at deploy time"
}

variable "recommend_agent_image" {
  type        = string
  description = "Fully-qualified container image URI for recommend-agent, set by CI at deploy time"
}
```

- [ ] **Step 2: Write `main.tf` — provider, the 3 private agent services, and their service accounts**

```hcl
# infra/terraform/main.tf
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

resource "google_service_account" "frontend_sa" {
  account_id   = "frontend-run-sa"
  display_name = "frontend Cloud Run runtime SA"
}

locals {
  agents = {
    search-agent    = { role = "search", image = var.search_agent_image }
    judge-agent     = { role = "judge", image = var.judge_agent_image }
    recommend-agent = { role = "recommend", image = var.recommend_agent_image }
  }
}

resource "google_service_account" "agent_sa" {
  for_each     = local.agents
  account_id   = "${each.key}-run-sa"
  display_name = "${each.key} Cloud Run runtime SA"
}

resource "google_cloud_run_v2_service" "agent" {
  for_each = local.agents
  name     = each.key
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.agent_sa[each.key].email
    containers {
      image = each.value.image
      env {
        name  = "AGENT_ROLE"
        value = each.value.role
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

# Only backend-api's runtime SA may invoke the private agent services
resource "google_cloud_run_v2_service_iam_member" "agent_invoker" {
  for_each = local.agents
  name     = google_cloud_run_v2_service.agent[each.key].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.backend_api_sa.email}"
}
```

- [ ] **Step 3: Add `backend-api` and `frontend` services to `main.tf`**

```hcl
# infra/terraform/main.tf (append)
resource "google_cloud_run_v2_service" "backend_api" {
  name     = "backend-api"
  location = var.region

  template {
    service_account = google_service_account.backend_api_sa.email
    containers {
      image = var.backend_api_image
      env {
        name  = "SEARCH_AGENT_URL"
        value = google_cloud_run_v2_service.agent["search-agent"].uri
      }
      env {
        name  = "JUDGE_AGENT_URL"
        value = google_cloud_run_v2_service.agent["judge-agent"].uri
      }
      env {
        name  = "RECOMMEND_AGENT_URL"
        value = google_cloud_run_v2_service.agent["recommend-agent"].uri
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

# backend-api is public — the frontend (browser-side) calls it directly
resource "google_cloud_run_v2_service_iam_member" "backend_api_public" {
  name     = google_cloud_run_v2_service.backend_api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "frontend"
  location = var.region

  template {
    service_account = google_service_account.frontend_sa.email
    containers {
      image = var.frontend_image
      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  name     = google_cloud_run_v2_service.frontend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
```

- [ ] **Step 4: Write `outputs.tf`**

```hcl
# infra/terraform/outputs.tf
output "frontend_url" {
  value = google_cloud_run_v2_service.frontend.uri
}

output "backend_api_url" {
  value = google_cloud_run_v2_service.backend_api.uri
}

output "search_agent_url" {
  value = google_cloud_run_v2_service.agent["search-agent"].uri
}

output "judge_agent_url" {
  value = google_cloud_run_v2_service.agent["judge-agent"].uri
}

output "recommend_agent_url" {
  value = google_cloud_run_v2_service.agent["recommend-agent"].uri
}
```

- [ ] **Step 5: Validate the Terraform config syntactically**

Run:
```bash
cd infra/terraform && terraform init -backend=false && terraform validate
```
Expected: `Success! The configuration is valid.`

Note: `terraform plan` cannot run yet without real image URIs and GCP credentials — that happens in Task 3. This step only checks HCL syntax and internal consistency (references, types).

- [ ] **Step 6: Commit**

```bash
git add infra/terraform/
git commit -m "infra: add Terraform for all 5 Cloud Run services (frontend, backend-api, 3 agents)"
```

---

### Task 3: First real deploy to the shared project

**Blocked on:** PR #12 must be merged to `main` first — `backend-api/`, `search-agent/`, `judge-agent/`, `recommend-agent/` do not exist on `main` yet. Check `gh pr view 12 --json state` before starting this task; if still `OPEN`, stop and tell the human this task is blocked on that merge landing, rather than deploying against incomplete code.

**Files:** none (infra operations against already-committed code)

**Interfaces:**
- Consumes: `infra/terraform/` (Task 2), `frontend/Dockerfile` (Task 1), and PR #12's `backend-api/Dockerfile` + 3 agents' `Dockerfile`s once merged
- Produces: 5 live Cloud Run URLs, recorded in a decision page for the team

- [ ] **Step 1: Confirm PR #12 has merged**

Run: `gh pr view 12 --json state --jq .state`
Expected: `MERGED`. If not, stop here and report blocked status to the human — do not proceed with a partial deploy.

- [ ] **Step 2: Pull the merged code**

```bash
git fetch origin main
git merge origin/main
```

- [ ] **Step 3: Build and push the 4 non-frontend images, then apply Terraform for everything except `frontend` — notify the human and wait for approval before running**

Frontend is deployed in two passes because Vite bakes `VITE_API_BASE_URL` in at build time, and the real `backend-api` URL isn't known until backend-api itself is deployed. Pass 1 stands up backend-api + the 3 agents; Pass 2 (Step 5-6) rebuilds frontend with the real URL and deploys it.

Say: "Ready to build and deploy backend-api + the 3 agent services to `project-3bcd6d36-2338-4b32-848` (frontend follows in a second pass once backend-api's URL is known). Proceed?" Wait for explicit yes.

```bash
for svc in backend-api search-agent judge-agent recommend-agent; do
  gcloud builds submit "$svc" \
    --tag "asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/$svc" \
    --project project-3bcd6d36-2338-4b32-848
done
```

- [ ] **Step 4: Apply Terraform, targeting everything except `frontend`**

```bash
cd infra/terraform
terraform init
terraform apply \
  -target=google_cloud_run_v2_service.agent \
  -target=google_cloud_run_v2_service_iam_member.agent_invoker \
  -target=google_cloud_run_v2_service.backend_api \
  -target=google_cloud_run_v2_service_iam_member.backend_api_public \
  -var="frontend_image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/frontend:placeholder" \
  -var="backend_api_image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/backend-api" \
  -var="search_agent_image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/search-agent" \
  -var="judge_agent_image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/judge-agent" \
  -var="recommend_agent_image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/recommend-agent"
```
Expected: `terraform apply` completes and prints `backend_api_url`, `search_agent_url`, `judge_agent_url`, `recommend_agent_url` (the `frontend_image` placeholder value is unused this pass — `frontend`'s own resource isn't targeted, so it stays uncreated for now)

- [ ] **Step 5: Build the real `frontend` image with `backend_api_url` baked in, then apply the rest of the Terraform**

```bash
gcloud builds submit frontend \
  --tag asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/frontend \
  --project project-3bcd6d36-2338-4b32-848 \
  --substitutions=_VITE_API_MODE=http,_VITE_API_BASE_URL="<backend_api_url from Step 4>" \
  --config=- <<'EOF'
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - --build-arg=VITE_API_MODE=$_VITE_API_MODE
      - --build-arg=VITE_API_BASE_URL=$_VITE_API_BASE_URL
      - -t
      - asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/frontend
      - frontend
images:
  - asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/frontend
EOF

cd infra/terraform
terraform apply \
  -var="frontend_image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/frontend" \
  -var="backend_api_image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/backend-api" \
  -var="search_agent_image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/search-agent" \
  -var="judge_agent_image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/judge-agent" \
  -var="recommend_agent_image=asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy/recommend-agent"
```
Expected: `terraform apply` (no `-target` this time) completes and prints all 5 URL outputs, including `frontend_url`

- [ ] **Step 6: End-to-end verification**

Run: `curl -X POST "<backend_api_url>/v1/recommendations" -H "Content-Type: application/json" -d '{"area":"福岡市中央区","wheelchair_width_cm":63}'`
Expected: `200` response with a `recommendations` array (PR #12's smoke content, not real Places/Gemini data yet)

Open `<frontend_url>` in a browser and confirm the SPA loads AND actually calls the real `backend-api` (check browser devtools network tab for a request to `<backend_api_url>/v1/recommendations`, not mock data) — this confirms Step 5's build-arg baking worked, not just that the container starts.

- [ ] **Step 7: Record the live URLs for the team**

Create `docs/wiki/concepts/deployed-endpoints.md` (frontmatter `type: decision`, `owner: infra`, sourced from `service-topology.md`) listing all 5 URLs, following the same structure as other decision pages in `docs/wiki/concepts/`. Update `docs/wiki/index.md` and `docs/wiki/log.md` per the OKF bundle convention.

- [ ] **Step 7: Commit**

```bash
git add docs/wiki/concepts/deployed-endpoints.md docs/wiki/index.md docs/wiki/log.md
git commit -m "docs: record deployed walking-skeleton endpoint URLs"
```

---

### Task 4: GitHub Actions CI/CD (auto-deploy on `main` push)

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: a GCP service account key stored as the GitHub secret `GCP_SA_KEY` (created manually in Step 1 — never committed to the repo)

- [ ] **Step 1: Create a deploy service account and store its key as a GitHub secret**

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
    env:
      PROJECT_ID: project-3bcd6d36-2338-4b32-848
      REGION: asia-northeast1
      REGISTRY: asia-northeast1-docker.pkg.dev/project-3bcd6d36-2338-4b32-848/cloud-run-source-deploy
    steps:
      - uses: actions/checkout@v4

      - uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - uses: google-github-actions/setup-gcloud@v2

      - name: Build backend-api and the 3 agent images
        run: |
          for svc in backend-api search-agent judge-agent recommend-agent; do
            gcloud builds submit "$svc" --tag "$REGISTRY/$svc" --project "$PROJECT_ID"
          done

      - name: Apply Terraform for everything except frontend
        working-directory: infra/terraform
        run: |
          terraform init
          terraform apply -auto-approve \
            -target=google_cloud_run_v2_service.agent \
            -target=google_cloud_run_v2_service_iam_member.agent_invoker \
            -target=google_cloud_run_v2_service.backend_api \
            -target=google_cloud_run_v2_service_iam_member.backend_api_public \
            -var="frontend_image=$REGISTRY/frontend:placeholder" \
            -var="backend_api_image=$REGISTRY/backend-api" \
            -var="search_agent_image=$REGISTRY/search-agent" \
            -var="judge_agent_image=$REGISTRY/judge-agent" \
            -var="recommend_agent_image=$REGISTRY/recommend-agent"

      - name: Read backend-api URL
        id: backend_url
        working-directory: infra/terraform
        run: echo "url=$(terraform output -raw backend_api_url)" >> "$GITHUB_OUTPUT"

      - name: Build frontend with the real backend-api URL baked in
        run: |
          gcloud builds submit frontend \
            --tag "$REGISTRY/frontend" \
            --project "$PROJECT_ID" \
            --substitutions=_VITE_API_MODE=http,_VITE_API_BASE_URL="${{ steps.backend_url.outputs.url }}" \
            --config=- <<'CFGEOF'
          steps:
            - name: gcr.io/cloud-builders/docker
              args:
                - build
                - --build-arg=VITE_API_MODE=$_VITE_API_MODE
                - --build-arg=VITE_API_BASE_URL=$_VITE_API_BASE_URL
                - -t
                - ${REGISTRY}/frontend
                - frontend
          images:
            - ${REGISTRY}/frontend
          CFGEOF

      - name: Apply Terraform for frontend
        working-directory: infra/terraform
        run: |
          terraform apply -auto-approve \
            -var="frontend_image=$REGISTRY/frontend" \
            -var="backend_api_image=$REGISTRY/backend-api" \
            -var="search_agent_image=$REGISTRY/search-agent" \
            -var="judge_agent_image=$REGISTRY/judge-agent" \
            -var="recommend_agent_image=$REGISTRY/recommend-agent"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: auto-deploy all 5 services to the shared project on main push"
```

- [ ] **Step 4: Notify the human and wait for approval before merging this branch**

Say: "CI/CD workflow ready. Merging this PR to `main` will trigger the first automated deploy using the `GCP_SA_KEY` secret. Proceed with merge?" Wait for explicit yes before merging.

---

## Self-Review Notes

- This plan replaces an earlier version whose Task 1 built `search-agent`/`judge-agent`/`recommend-agent` as ADK apps via `agents-cli scaffold`. That work was discarded (never pushed) after discovering a teammate's in-flight PR #12 building the same services as plain FastAPI with a different endpoint contract (`/execute`, not `/invoke`) and its own ID-token auth already wired. This plan is now infra-only and treats PR #12 (and merged PR #11 for frontend) as the source of truth for application code.
- Task 3 is explicitly gated on PR #12's merge status — Step 1 checks it and stops rather than guessing or waiting silently.
- Task 0 was added after realizing two phase-independent prerequisites were missing: a GCS bucket for Terraform remote state (so any teammate, not just this worktree, can run `terraform apply` against consistent state) and the Artifact Registry repo `gcloud builds submit --tag` pushes into (it doesn't auto-create). Both are bootstrapped via plain `gcloud`, the one deliberate exception to "infra goes through Terraform" — the backend that stores Terraform's state can't itself be Terraform-managed state.
- The frontend's `VITE_API_MODE`/`VITE_API_BASE_URL` are Vite build-time env vars, not runtime. Task 3 now deploys in two passes to solve this properly instead of leaving it as an open follow-up: Pass 1 (Steps 3-4) stands up backend-api + the 3 agents and reads `backend_api_url` from Terraform output; Pass 2 (Steps 5-6) rebuilds `frontend`'s image with that real URL baked in via `--build-arg`/Cloud Build substitutions, then applies the rest of the Terraform. Task 4's CI workflow mirrors this same two-pass sequence.
- IAM design: the 3 agent services are `INGRESS_TRAFFIC_INTERNAL_ONLY` and only `backend-api`'s service account may invoke them (`google_cloud_run_v2_service_iam_member.agent_invoker`), matching PR #12's ID-token auth code, which only makes sense if the agents actually reject unauthenticated calls.
