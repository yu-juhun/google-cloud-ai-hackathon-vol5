variable "video_image" {
  type    = string
  default = ""
}

resource "google_service_account" "video" {
  account_id   = "michibiki-video"
  display_name = "michibiki video generation runtime"
}
resource "google_project_iam_member" "video_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.video.email}"
}
resource "google_storage_bucket_iam_member" "journey_video_media" {
  for_each = toset(["roles/storage.objectViewer", "roles/storage.objectCreator"])
  bucket   = google_storage_bucket.avatars.name
  role     = each.value
  member   = "serviceAccount:${google_service_account.video.email}"
  condition {
    title      = "journey-video-objects-only"
    expression = "resource.name.startsWith('projects/_/buckets/${google_storage_bucket.avatars.name}/objects/videos/journeys/')"
  }
}
resource "google_cloud_run_v2_service" "video" {
  count               = var.video_image == "" ? 0 : 1
  name                = "michibiki-video-agent"
  location            = var.region
  deletion_protection = false
  scaling {
    min_instance_count    = 0
    manual_instance_count = 0
  }
  template {
    service_account                  = google_service_account.video.email
    timeout                          = "300s"
    max_instance_request_concurrency = 1
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.video_image
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "2", memory = "2Gi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = {
          VERTEX_PROJECT_ID = var.project_id
          VERTEX_LOCATION   = "us-central1"
          MEDIA_BUCKET      = google_storage_bucket.avatars.name
        }
        content {
          name  = env.key
          value = env.value
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
  depends_on = [google_project_service.apis, google_project_iam_member.video_vertex, google_storage_bucket_iam_member.journey_video_media]
}
resource "google_cloud_run_v2_service_iam_member" "video" {
  count    = var.video_image == "" ? 0 : 1
  name     = google_cloud_run_v2_service.video[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime["backend"].email}"
}
output "video_url" {
  value = var.video_image == "" ? "" : google_cloud_run_v2_service.video[0].uri
}
