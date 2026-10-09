resource "google_storage_bucket" "experiences" {
  name                        = "${var.project_id}-michibiki-experiences"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
}
resource "google_storage_bucket_iam_member" "experience_writer" {
  bucket = google_storage_bucket.experiences.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.runtime["backend"].email}"
}
resource "google_project_iam_member" "experience_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime["backend"].email}"
}
