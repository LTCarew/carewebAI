# ─────────────────────────────────────────────────────────────
# CareWeb Registry — Terraform Main Configuration
# Provider: Google Cloud Platform
# ─────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }

    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }

  # Optional remote Terraform state:
  #
  # backend "gcs" {
  #   bucket = "your-terraform-state-bucket"
  #   prefix = "careweb/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ─────────────────────────────────────────────────────────────
# Local values
# ─────────────────────────────────────────────────────────────

locals {
  app        = var.app_name
  image_repo = "${var.region}-docker.pkg.dev/${var.project_id}/${local.app}/${local.app}"
  image_full = "${local.image_repo}:${var.image_tag}"

  # Cloud SQL Unix socket path used by the Cloud Run container.
  db_socket = "/cloudsql/${google_sql_database_instance.postgres.connection_name}"
}

# ─────────────────────────────────────────────────────────────
# Enable required Google Cloud APIs
# ─────────────────────────────────────────────────────────────

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# ─────────────────────────────────────────────────────────────
# Artifact Registry
# ─────────────────────────────────────────────────────────────

resource "google_artifact_registry_repository" "docker_repo" {
  depends_on = [google_project_service.apis]

  project       = var.project_id
  location      = var.region
  repository_id = local.app
  format        = "DOCKER"
  description   = "CareWeb Registry Docker images"
}

# ─────────────────────────────────────────────────────────────
# Cloud SQL PostgreSQL
# ─────────────────────────────────────────────────────────────

resource "google_sql_database_instance" "postgres" {
  depends_on = [google_project_service.apis]

  project          = var.project_id
  name             = "${local.app}-postgres"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"

    ip_configuration {
      # Cloud SQL requires at least one connectivity method.
      # Cloud Run still connects using the Cloud SQL Unix socket.
      ipv4_enabled = true
    }

    backup_configuration {
      enabled    = true
      start_time = "03:00"
    }

    deletion_protection_enabled = true
  }

  deletion_protection = true
}

resource "google_sql_database" "db" {
  project  = var.project_id
  name     = var.db_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "db_user" {
  project  = var.project_id
  name     = var.db_user
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}

# ─────────────────────────────────────────────────────────────
# Secret Manager
# ─────────────────────────────────────────────────────────────

resource "google_secret_manager_secret" "django_secret_key" {
  depends_on = [google_project_service.apis]

  project   = var.project_id
  secret_id = "${local.app}-django-secret-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "django_secret_key" {
  secret      = google_secret_manager_secret.django_secret_key.id
  secret_data = var.django_secret_key
}

resource "google_secret_manager_secret" "db_password" {
  depends_on = [google_project_service.apis]

  project   = var.project_id
  secret_id = "${local.app}-db-password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

resource "google_secret_manager_secret" "openai_api_key" {
  depends_on = [google_project_service.apis]

  project   = var.project_id
  secret_id = "${local.app}-openai-api-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "openai_api_key" {
  secret      = google_secret_manager_secret.openai_api_key.id
  secret_data = var.openai_api_key
}

# ─────────────────────────────────────────────────────────────
# Cloud Run service account
# ─────────────────────────────────────────────────────────────

resource "google_service_account" "cloud_run_sa" {
  project      = var.project_id
  account_id   = "${local.app}-run-sa"
  display_name = "CareWeb Cloud Run Service Account"
}

resource "google_project_iam_member" "cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# ─────────────────────────────────────────────────────────────
# Cloud Run Django application
# ─────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "app" {
  depends_on = [
    google_artifact_registry_repository.docker_repo,
    google_sql_database_instance.postgres,
    google_sql_database.db,
    google_sql_user.db_user,
    google_project_iam_member.cloud_sql_client,
    google_project_iam_member.secret_accessor,
  ]

  project  = var.project_id
  name     = local.app
  location = var.region

  template {
    service_account = google_service_account.cloud_run_sa.email

    scaling {
      min_instance_count = var.cloud_run_min_instances
      max_instance_count = var.cloud_run_max_instances
    }

    volumes {
      name = "cloudsql"

      cloud_sql_instance {
        instances = [
          google_sql_database_instance.postgres.connection_name
        ]
      }
    }

    containers {
      image = local.image_full

      resources {
        limits = {
          cpu    = var.cloud_run_cpu
          memory = var.cloud_run_memory
        }

        cpu_idle = true
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "DEBUG"
        value = "False"
      }

      env {
        name = "ALLOWED_HOSTS"

        value = var.site_url != "" ? replace(
          replace(var.site_url, "https://", ""),
          "http://",
          ""
        ) : "*"
      }

      env {
        name  = "SITE_URL"
        value = var.site_url
      }

      env {
        name = "SECRET_KEY"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.django_secret_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "POSTGRES_DB"
        value = var.db_name
      }

      env {
        name  = "POSTGRES_USER"
        value = var.db_user
      }

      env {
        name = "POSTGRES_PASSWORD"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "POSTGRES_HOST"
        value = local.db_socket
      }

      env {
        name  = "POSTGRES_PORT"
        value = ""
      }

      env {
        name = "OPENAI_API_KEY"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openai_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "EMAIL_HOST_USER"
        value = var.email_host_user
      }

      env {
        name  = "EMAIL_HOST_PASSWORD"
        value = var.email_host_password
      }

      ports {
        container_port = 8080
      }

      startup_probe {
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 5
        failure_threshold     = 10

        tcp_socket {
          port = 8080
        }
      }

      liveness_probe {
        initial_delay_seconds = 10
        timeout_seconds       = 5
        period_seconds        = 30
        failure_threshold     = 3

        http_get {
          path = "/"
          port = 8080

          http_headers {
            name  = "Host"
            value = "localhost"
          }
        }
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }
}

# ─────────────────────────────────────────────────────────────
# Public Cloud Run access
# ─────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}