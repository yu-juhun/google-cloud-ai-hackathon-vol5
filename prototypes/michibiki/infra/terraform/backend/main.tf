terraform {
  required_version = ">= 1.5"
  backend "gcs" {}
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
    random = { source = "hashicorp/random", version = "~> 3.7" }
  }
}
provider "google" {
  project = var.project_id
  region  = var.region
}
variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "asia-northeast1"
}
variable "services_image" { type = string }
variable "frontend_origin" { type = string }

resource "google_project_service" "apis" {
  for_each = toset(["sqladmin.googleapis.com", "secretmanager.googleapis.com", "apikeys.googleapis.com",
    "places.googleapis.com", "aiplatform.googleapis.com", "run.googleapis.com",
  "iamcredentials.googleapis.com", "storage.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "runtime" {
  for_each     = toset(["backend", "orchestrator", "search", "judge", "recommend"])
  account_id   = "michibiki-${each.key}"
  display_name = "michibiki ${each.key} runtime"
}

resource "google_project_iam_member" "vertex" {
  for_each = toset(["orchestrator", "judge", "recommend"])
  project  = var.project_id
  role     = "roles/aiplatform.user"
  member   = "serviceAccount:${google_service_account.runtime[each.key].email}"
}
resource "google_project_iam_member" "sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.runtime["backend"].email}"
}

resource "google_sql_database_instance" "app" {
  name                = "michibiki-db"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = true
  depends_on          = [google_project_service.apis]
  settings {
    tier                  = "db-f1-micro"
    availability_type     = "ZONAL"
    edition               = "ENTERPRISE"
    disk_size             = 10
    disk_autoresize       = true
    disk_autoresize_limit = 20
    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }
    backup_configuration { enabled = true }
  }
}
resource "google_sql_database" "app" {
  name     = "michibiki"
  instance = google_sql_database_instance.app.name
}
resource "random_password" "db" {
  length  = 32
  special = false
}
resource "google_sql_user" "app" {
  name     = "michibiki"
  instance = google_sql_database_instance.app.name
  password = random_password.db.result
}
resource "google_secret_manager_secret" "db" {
  secret_id = "michibiki-db-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}
resource "google_secret_manager_secret_version" "db" {
  secret      = google_secret_manager_secret.db.id
  secret_data = random_password.db.result
}
resource "google_secret_manager_secret_iam_member" "db" {
  secret_id = google_secret_manager_secret.db.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["backend"].email}"
}

resource "google_apikeys_key" "places" {
  name         = "michibiki-places"
  display_name = "michibiki server-side Places only"
  restrictions {
    api_targets { service = "places.googleapis.com" }
  }
  depends_on = [google_project_service.apis]
}
resource "google_secret_manager_secret" "places" {
  secret_id = "michibiki-places-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}
resource "google_secret_manager_secret_version" "places" {
  secret      = google_secret_manager_secret.places.id
  secret_data = google_apikeys_key.places.key_string
}
resource "google_secret_manager_secret_iam_member" "places" {
  secret_id = google_secret_manager_secret.places.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime["search"].email}"
}

resource "google_cloud_run_v2_service" "specialist" {
  for_each            = toset(["search", "judge", "recommend"])
  name                = "michibiki-${each.key}-agent"
  location            = var.region
  deletion_protection = false
  scaling {
    min_instance_count    = 0
    manual_instance_count = 0
  }
  template {
    service_account = google_service_account.runtime[each.key].email
    timeout         = "180s"
    # A single mission can dispatch all ten logical twins concurrently.
    max_instance_request_concurrency = 10
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.services_image
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      env {
        name  = "SERVICE_ROLE"
        value = each.key
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      dynamic "env" {
        for_each = each.key == "search" ? [1] : []
        content {
          name = "PLACES_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.places.secret_id
              version = google_secret_manager_secret_version.places.version
            }
          }
        }
      }
      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds    = 5
        failure_threshold = 20
      }
    }
  }
  depends_on = [google_project_service.apis, google_project_iam_member.vertex,
  google_secret_manager_secret_iam_member.places]
}

resource "google_cloud_run_v2_service" "orchestrator" {
  name                = "michibiki-trip-orchestrator"
  location            = var.region
  deletion_protection = false
  scaling {
    min_instance_count    = 0
    manual_instance_count = 0
  }
  template {
    service_account                  = google_service_account.runtime["orchestrator"].email
    timeout                          = "300s"
    max_instance_request_concurrency = 2
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.services_image
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      env {
        name  = "SERVICE_ROLE"
        value = "orchestrator"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "ORCHESTRATOR_MODEL"
        value = "gemini-3.8-flash"
      }
      dynamic "env" {
        for_each = google_cloud_run_v2_service.specialist
        content {
          name  = "${upper(env.key)}_URL"
          value = env.value.uri
        }
      }
      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds    = 5
        failure_threshold = 20
      }
    }
  }
  depends_on = [google_project_iam_member.vertex]
}
resource "google_cloud_run_v2_service_iam_member" "specialist" {
  for_each = google_cloud_run_v2_service.specialist
  name     = each.value.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime["orchestrator"].email}"
}

resource "google_cloud_run_v2_service" "backend" {
  name                = "michibiki-backend-api"
  location            = var.region
  deletion_protection = false
  scaling {
    min_instance_count    = 0
    manual_instance_count = 0
  }
  template {
    service_account                  = google_service_account.runtime["backend"].email
    timeout                          = "300s"
    max_instance_request_concurrency = 2
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.services_image
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = {
          SERVICE_ROLE             = "backend"
          ORCHESTRATOR_URL         = google_cloud_run_v2_service.orchestrator.uri
          FRONTEND_ORIGIN          = "${var.frontend_origin},http://localhost:5173,http://127.0.0.1:5173"
          INSTANCE_CONNECTION_NAME = google_sql_database_instance.app.connection_name
          DB_USER                  = google_sql_user.app.name
          DB_NAME                  = google_sql_database.app.name
          AVATAR_BUCKET            = google_storage_bucket.avatars.name
          GOOGLE_CLOUD_PROJECT     = var.project_id
          EXPERIENCE_BUCKET        = google_storage_bucket.experiences.name
          EXPERIENCE_REFERENCE_URL = "${var.frontend_origin}/images/cafe-spring-day-trip.png"
          EXPERIENCE_IMAGE_MODEL   = "gemini-3.1-flash-image"
          AVATAR_SIGNER            = google_service_account.runtime["backend"].email
          PERSONA_URL              = var.persona_image == "" ? "" : google_cloud_run_v2_service.persona[0].uri
        }
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db.secret_id
            version = google_secret_manager_secret_version.db.version
          }
        }
      }
      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds    = 5
        failure_threshold = 60
      }
    }
  }
  depends_on = [google_project_iam_member.sql, google_secret_manager_secret_iam_member.db]
}
resource "google_cloud_run_v2_service_iam_member" "orchestrator" {
  name     = google_cloud_run_v2_service.orchestrator.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime["backend"].email}"
}
resource "google_cloud_run_v2_service_iam_member" "backend_demo" {
  name     = google_cloud_run_v2_service.backend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
output "backend_url" { value = google_cloud_run_v2_service.backend.uri }
output "database_connection_name" { value = google_sql_database_instance.app.connection_name }
