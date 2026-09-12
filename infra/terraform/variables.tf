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
