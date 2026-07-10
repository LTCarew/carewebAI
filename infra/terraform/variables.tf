# ─────────────────────────────────────────────────────────────
# CareWeb Registry — Terraform Variables
# ─────────────────────────────────────────────────────────────

variable "project_id" {
  description = "GCP project ID to deploy resources into."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run, Cloud SQL, and Artifact Registry."
  type        = string
  default     = "us-central1"
}

variable "app_name" {
  description = "Short name used to prefix/label all resources."
  type        = string
  default     = "careweb"
}

# ── Docker image ──────────────────────────────────────────────
variable "image_tag" {
  description = "Docker image tag to deploy to Cloud Run (e.g. 'latest' or a SHA)."
  type        = string
  default     = "latest"
}

# ── Cloud SQL ─────────────────────────────────────────────────
variable "db_tier" {
  description = "Cloud SQL machine tier (e.g. db-f1-micro for dev, db-g1-small for prod)."
  type        = string
  default     = "db-f1-micro"
}

variable "db_name" {
  description = "Name of the PostgreSQL database to create."
  type        = string
  default     = "careweb"
}

variable "db_user" {
  description = "PostgreSQL user that the Django app connects with."
  type        = string
  default     = "careweb_user"
}

variable "db_password" {
  description = "PostgreSQL user password. Store this in Secret Manager or a *.tfvars file — never commit it."
  type        = string
  sensitive   = true
}

# ── Django secrets ────────────────────────────────────────────
variable "django_secret_key" {
  description = "Django SECRET_KEY. Store this in Secret Manager or a *.tfvars file — never commit it."
  type        = string
  sensitive   = true
}

# ── OpenAI ───────────────────────────────────────────────────
variable "openai_api_key" {
  description = "OpenAI API key for AI-assisted matching. Keep secret."
  type        = string
  sensitive   = true
  default     = ""
}

# ── Cloud Run ────────────────────────────────────────────────
variable "cloud_run_min_instances" {
  description = "Minimum number of Cloud Run instances (0 = scale to zero)."
  type        = number
  default     = 0
}

variable "cloud_run_max_instances" {
  description = "Maximum number of Cloud Run instances."
  type        = number
  default     = 5
}

variable "cloud_run_cpu" {
  description = "CPU allocated per Cloud Run instance."
  type        = string
  default     = "1"
}

variable "cloud_run_memory" {
  description = "Memory allocated per Cloud Run instance."
  type        = string
  default     = "512Mi"
}

# ── Email (optional) ─────────────────────────────────────────
variable "email_host_user" {
  description = "SMTP username for Django email sending."
  type        = string
  default     = ""
}

variable "email_host_password" {
  description = "SMTP password for Django email sending."
  type        = string
  sensitive   = true
  default     = ""
}

variable "site_url" {
  description = "Public URL of the deployed app (e.g. https://careweb-xyz-uc.a.run.app)."
  type        = string
  default     = ""
}
