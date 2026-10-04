variable "persona_image" {
  type    = string
  default = ""
}
variable "youcam_key_secret" {
  type    = string
  default = ""
}
variable "youcam_api_secret" {
  type    = string
  default = ""
}

resource "google_storage_bucket" "avatars" {
  name                        = "${var.project_id}-michibiki-avatars"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
}
resource "google_service_account" "persona" {
  account_id   = "michibiki-persona"
  display_name = "michibiki avatar and voice runtime"
}
resource "google_project_iam_member" "persona_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.persona.email}"
}
resource "google_storage_bucket_iam_member" "avatar_writer" {
  bucket = google_storage_bucket.avatars.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.persona.email}"
}
resource "google_storage_bucket_iam_member" "avatar_reader" {
  bucket = google_storage_bucket.avatars.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.runtime["backend"].email}"
}
resource "google_service_account_iam_member" "avatar_signer" {
  service_account_id = google_service_account.runtime["backend"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.runtime["backend"].email}"
}
locals {
  youcam_secrets = { for key, value in {
    PERFECTCORP_API_KEY    = var.youcam_key_secret
    PERFECTCORP_API_SECRET = var.youcam_api_secret
  } : key => value if value != "" }
}
resource "google_secret_manager_secret_iam_member" "youcam" {
  for_each  = local.youcam_secrets
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.persona.email}"
}
resource "google_cloud_run_v2_service" "persona" {
  count               = var.persona_image == "" ? 0 : 1
  name                = "michibiki-persona-agent"
  location            = var.region
  deletion_protection = false
  scaling {
    min_instance_count    = 0
    manual_instance_count = 0
  }
  template {
    service_account                  = google_service_account.persona.email
    timeout                          = "300s"
    max_instance_request_concurrency = 4
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.persona_image
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = {
          VERTEX_PROJECT_ID = var.project_id
          VERTEX_LOCATION   = "us-central1"
          IMAGE_LOCATION    = "global"
          AVATAR_BUCKET     = google_storage_bucket.avatars.name
        }
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.youcam_secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
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
  depends_on = [google_project_service.apis, google_project_iam_member.persona_vertex,
  google_storage_bucket_iam_member.avatar_writer, google_secret_manager_secret_iam_member.youcam]
}
resource "google_cloud_run_v2_service_iam_member" "persona" {
  count    = var.persona_image == "" ? 0 : 1
  name     = google_cloud_run_v2_service.persona[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime["backend"].email}"
}
output "persona_url" {
  value = var.persona_image == "" ? "" : google_cloud_run_v2_service.persona[0].uri
}
