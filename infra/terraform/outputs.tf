# ─────────────────────────────────────────────────────────────
# CareWeb Registry — Terraform Outputs
# ─────────────────────────────────────────────────────────────

output "cloud_run_url" {
  description = "The public HTTPS URL of the Cloud Run service."
  value       = google_cloud_run_v2_service.app.uri
}

output "artifact_registry_repo" {
  description = "Full Artifact Registry repository path. Use this as the base for docker push."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.app_name}"
}

output "docker_image_full" {
  description = "Full Docker image reference deployed to Cloud Run."
  value       = local.image_full
}

output "cloud_sql_instance_connection_name" {
  description = "Cloud SQL connection name used for the Auth Proxy / socket."
  value       = google_sql_database_instance.postgres.connection_name
}

output "cloud_sql_instance_name" {
  description = "Cloud SQL instance name."
  value       = google_sql_database_instance.postgres.name
}

output "cloud_run_service_account" {
  description = "Service account email used by Cloud Run."
  value       = google_service_account.cloud_run_sa.email
}
