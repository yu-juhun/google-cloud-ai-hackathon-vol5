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
