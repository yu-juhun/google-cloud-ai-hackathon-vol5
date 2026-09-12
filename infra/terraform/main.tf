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
