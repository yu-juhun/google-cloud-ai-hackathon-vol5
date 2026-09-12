# infra/terraform/backend.tf
terraform {
  backend "gcs" {
    bucket = "project-3bcd6d36-2338-4b32-848-tfstate"
    prefix = "walking-skeleton"
  }
}
