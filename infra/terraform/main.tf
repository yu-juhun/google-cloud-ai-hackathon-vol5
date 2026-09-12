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
    search-agent    = { role = "search", image = var.search_agent_image, needs_places_secret = true, needs_vertex = false }
    judge-agent     = { role = "judge", image = var.judge_agent_image, needs_places_secret = false, needs_vertex = true }
    recommend-agent = { role = "recommend", image = var.recommend_agent_image, needs_places_secret = false, needs_vertex = true }
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
  # INGRESS_TRAFFIC_INTERNAL_ONLY requires callers to reach this service via
  # VPC networking (Direct VPC egress / Serverless VPC Access), which
  # backend-api does not use — with plain Cloud-Run-to-Cloud-Run calls that
  # setting made Google Front End reject the request before it ever reached
  # this container (fast failure, no request logged here at all). Privacy is
  # enforced by the IAM invoker binding below instead (default ingress + no
  # public invoker = effectively private to authorized callers). Must be set
  # explicitly to ALL — omitting the attribute does NOT reset a previously
  # applied "internal" value on the live resource (confirmed: Terraform
  # apply succeeded while the live annotation stayed run.googleapis.com/
  # ingress=internal, causing GFE to 404 every request before it reached
  # the container).
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.agent_sa[each.key].email
    containers {
      image = each.value.image
      env {
        name  = "AGENT_ROLE"
        value = each.value.role
      }
      dynamic "env" {
        for_each = each.value.needs_places_secret ? [1] : []
        content {
          name = "PLACES_API_KEY"
          value_source {
            secret_key_ref {
              secret  = "places-api-key"
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = each.value.needs_vertex ? [1] : []
        content {
          name  = "VERTEX_PROJECT_ID"
          value = var.project_id
        }
      }
      dynamic "env" {
        for_each = each.value.needs_vertex ? [1] : []
        content {
          name  = "VERTEX_LOCATION"
          value = "global"
        }
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

# search-agent's runtime SA needs read access to the manually-created places-api-key secret
resource "google_secret_manager_secret_iam_member" "search_agent_places_api_key" {
  for_each  = { for k, v in local.agents : k => v if v.needs_places_secret }
  secret_id = "places-api-key"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_sa[each.key].email}"
}

# judge-agent and recommend-agent call Vertex AI Gemini as their own runtime SA
resource "google_project_iam_member" "agent_vertex_user" {
  for_each = { for k, v in local.agents : k => v if v.needs_vertex }
  project  = var.project_id
  role     = "roles/aiplatform.user"
  member   = "serviceAccount:${google_service_account.agent_sa[each.key].email}"
}

# Only backend-api's runtime SA may invoke the private agent services
resource "google_cloud_run_v2_service_iam_member" "agent_invoker" {
  for_each = local.agents
  name     = google_cloud_run_v2_service.agent[each.key].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.backend_api_sa.email}"
}

resource "google_cloud_run_v2_service" "backend_api" {
  name                = "backend-api"
  location            = var.region
  deletion_protection = false

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
  name                = "frontend"
  location            = var.region
  deletion_protection = false

  template {
    service_account = google_service_account.frontend_sa.email
    containers {
      image = var.frontend_image
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
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
