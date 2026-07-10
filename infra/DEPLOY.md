# CareWeb Registry — GCP Deployment Guide

This guide walks through deploying the CareWeb Registry Django app to
**Google Cloud Run** backed by **Cloud SQL PostgreSQL**, using
**Terraform** for all infrastructure and **Docker** for packaging.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| gcloud CLI | latest | https://cloud.google.com/sdk/docs/install |
| Docker Desktop | latest | https://docs.docker.com/get-docker/ |
| Terraform | >= 1.6 | https://developer.hashicorp.com/terraform/install |

---

## 1 · One-time GCP setup

```bash
# Authenticate with your Google account
gcloud auth login
gcloud auth application-default login

# Set your project
gcloud config set project YOUR_PROJECT_ID
```

---

## 2 · Configure Terraform variables

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` and fill in every `CHANGE_ME` value:

| Variable | Where to get it |
|----------|----------------|
| `project_id` | GCP Console → project selector |
| `django_secret_key` | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `db_password` | Choose a strong password |
| `openai_api_key` | https://platform.openai.com/api-keys |
| `site_url` | Leave blank for the first apply; fill in after step 4 |

> ⚠️ **Never commit `terraform.tfvars`** — it is in `.gitignore`.

---

## 3 · Provision infrastructure

```bash
cd infra/terraform

terraform init
terraform plan   # review what will be created
terraform apply  # type "yes" when prompted
```

First apply takes ~10 minutes (Cloud SQL instance creation is slow).

**Note the outputs:**

```
cloud_run_url              = "https://careweb-XXXXX-uc.a.run.app"
artifact_registry_repo     = "us-central1-docker.pkg.dev/YOUR_PROJECT/careweb"
cloud_sql_instance_name    = "careweb-postgres"
```

---

## 4 · Register the Cloud Run URL

1. Copy the `cloud_run_url` value from the Terraform output.
2. Edit `infra/terraform/terraform.tfvars`:
   ```hcl
   site_url = "https://careweb-XXXXX-uc.a.run.app"
   ```
3. Re-apply:
   ```bash
   terraform apply
   ```

---

## 5 · Build and push the Docker image

Run from the **`caregiver_registry/`** directory (where the Dockerfile lives):

```bash
# Authenticate Docker with Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build the image (set PROJECT_ID and REGION to your values)
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/careweb/careweb:latest"

cd caregiver_registry
docker build -t $IMAGE .

# Push to Artifact Registry
docker push $IMAGE
```

---

## 6 · Run Django database migrations

After pushing the image, run migrations via Cloud Run Jobs or a one-off container.
The easiest approach is a temporary Cloud Run job:

```bash
gcloud run jobs create careweb-migrate \
  --image "$IMAGE" \
  --region "$REGION" \
  --set-cloudsql-instances "$(terraform -chdir=infra/terraform output -raw cloud_sql_instance_connection_name)" \
  --set-env-vars "DEBUG=False,POSTGRES_DB=careweb,POSTGRES_USER=careweb_user" \
  --set-secrets "SECRET_KEY=careweb-django-secret-key:latest,POSTGRES_PASSWORD=careweb-db-password:latest" \
  --command python \
  --args "manage.py,migrate"

gcloud run jobs execute careweb-migrate --region "$REGION" --wait
```

---

## 7 · Deploy the new image to Cloud Run

After pushing a new image, update Cloud Run:

```bash
gcloud run services update careweb \
  --image "$IMAGE" \
  --region "$REGION"
```

Or bump the `image_tag` in `terraform.tfvars` and re-run `terraform apply`.

---

## 8 · Local development (unchanged)

Local dev still uses SQLite and the Django dev server — no Docker required:

```bash
cd caregiver_registry
python manage.py runserver     # DEBUG=True in .env → SQLite
```

---

## Environment variable reference

| Variable | Dev (`.env`) | Prod (Cloud Run) |
|----------|-------------|-----------------|
| `DEBUG` | `True` | `False` |
| `SECRET_KEY` | any string | Secret Manager |
| `ALLOWED_HOSTS` | _(auto: localhost)_ | Cloud Run domain |
| `POSTGRES_*` | _(not used — SQLite)_ | Cloud SQL socket |
| `OPENAI_API_KEY` | your key | Secret Manager |

---

## Cost estimates (us-central1)

| Resource | Approximate monthly cost |
|----------|--------------------------|
| Cloud Run (scale-to-zero, low traffic) | ~$0 – $5 |
| Cloud SQL db-f1-micro | ~$7 |
| Artifact Registry (first 0.5 GB free) | ~$0 |
| Secret Manager | ~$0 |
| **Total** | **~$7 – $12 / month** |
