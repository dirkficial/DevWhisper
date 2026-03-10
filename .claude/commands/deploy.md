Deploy DevWhisper to Google Cloud Run.

## Prerequisites

- Docker is running
- `gcloud` CLI is authenticated: `gcloud auth login`
- Application Default Credentials are set: `gcloud auth application-default login`
- Project is set: `gcloud config set project project-134fb569-ac25-4bca-929`

## Steps

### 1. Build and push the Docker image

```bash
cd /Users/derekkim/Desktop/DevWhisper
gcloud builds submit --tag gcr.io/project-134fb569-ac25-4bca-929/devwhisper
```

### 2. Deploy to Cloud Run

```bash
gcloud run deploy devwhisper \
  --image gcr.io/project-134fb569-ac25-4bca-929/devwhisper \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=project-134fb569-ac25-4bca-929 \
  --port 8000
```

### 3. Verify

Cloud Run will print the service URL. Open it in Chrome and test a session.

Note: A Dockerfile does not exist yet — this needs to be created on Day 5 before running these steps.
