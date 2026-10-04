terraform {
  required_version = ">= 1.5"
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

variable "project_id" {
  type        = string
  description = "Personal Google Cloud project ID. Set locally; do not commit project-specific tfvars."
}

variable "region" {
  type    = string
  default = "asia-northeast1"
}

variable "frontend_image" {
  type        = string
  description = "Artifact Registry image built from frontend/Dockerfile (prefer a digest)."
}

variable "backend_url" {
  type        = string
  default     = ""
  description = "Public demo API URL. Empty disables requests; it never falls back to mock results."
  validation {
    condition     = var.backend_url == "" || can(regex("^https://[a-z0-9.-]+$", var.backend_url))
    error_message = "backend_url must be an HTTPS origin without path, query, or quotes."
  }
}

resource "google_project_service" "api" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "frontend" {
  location      = var.region
  repository_id = "michibiki"
  format        = "DOCKER"
  depends_on    = [google_project_service.api]
}

resource "google_service_account" "frontend" {
  account_id   = "michibiki-frontend"
  display_name = "michibiki frontend runtime"
}

resource "google_service_account" "builder" {
  account_id   = "michibiki-builder"
  display_name = "michibiki container builder"
}

resource "google_artifact_registry_repository_iam_member" "builder" {
  location   = var.region
  repository = google_artifact_registry_repository.frontend.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_project_iam_member" "builder_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_storage_bucket" "terraform_state" {
  name                        = "${var.project_id}-michibiki-tfstate"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  versioning {
    enabled = true
  }
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30
      with_state                 = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket" "build_source" {
  name                        = "${var.project_id}-michibiki-build-source"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "builder_source" {
  bucket = google_storage_bucket.build_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.builder.email}"
}

resource "google_cloud_run_v2_service" "frontend" {
  name                = "michibiki-frontend"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  depends_on          = [google_project_service.api]

  # Match the service-level defaults returned by the API to avoid perpetual drift.
  scaling {
    min_instance_count    = 0
    manual_instance_count = 0
  }

  template {
    service_account                  = google_service_account.frontend.email
    timeout                          = "30s"
    max_instance_request_concurrency = 80
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image = var.frontend_image
      env {
        name  = "BACKEND_URL"
        value = var.backend_url
      }
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
        cpu_idle = true
      }
      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds    = 3
        timeout_seconds   = 1
        failure_threshold = 10
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

output "frontend_url" {
  value = google_cloud_run_v2_service.frontend.uri
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.frontend.repository_id}"
}
