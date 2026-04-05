# FlowAgent (FastAPI + GCP)

FlowAgent is a multi-agent scheduling assistant backend with:
- Google Calendar read/write via OAuth2
- Firestore task management (CRUD + priorities/tags)
- Daily optimization engine with scheduling rules
- Confirmation-based event creation workflow
- Cloud Run ready deployment

## 1) Project Structure

- `app/main.py` - FastAPI app entrypoint
- `app/routes/auth.py` - Google OAuth connect/callback
- `app/routes/flow.py` - Message + confirmation APIs
- `app/routes/tasks.py` - Task CRUD APIs
- `app/services/*` - Calendar/Task/Optimizer/Scheduling logic
- `app/clients/*` - Firestore and Calendar client wrappers

## 2) GCP Prerequisites

```powershell
gcloud config set project woven-answer-492218-v6
gcloud services enable run.googleapis.com cloudbuild.googleapis.com firestore.googleapis.com secretmanager.googleapis.com calendar-json.googleapis.com
```

Create Firestore (if not created yet):

```powershell
gcloud firestore databases create --location=asia-south1 --type=firestore-native
```

## 3) Google OAuth Setup

1. In Google Cloud Console, configure OAuth consent screen.
2. Create OAuth 2.0 Client ID (`Web application`).
3. Add redirect URI:
   - `http://localhost:8080/auth/callback` (local)
   - `https://<cloud-run-url>/auth/callback` (prod)
4. Put values in `.env` from `.env.example`.

## 4) Local Run

```powershell
cd C:\Users\tanis\source\flowagent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Open Swagger:
- `http://localhost:8080/docs`

## 5) Connect Calendar

1. Call `GET /auth/url?user_id=<your-user-id>`.
2. Open `auth_url` in browser and approve access.
3. Callback stores OAuth tokens in Firestore: `users/{userId}/oauth/google`.

## 6) API Endpoints

- `POST /flow/message`
  - Body: `{ "user_id": "u1", "message": "When am I free today?" }`
- `POST /flow/confirm`
  - Body contains the proposed action from `/flow/message`
- `GET /users/{user_id}/tasks?status=pending`
- `POST /users/{user_id}/tasks`
- `PATCH /users/{user_id}/tasks/{task_id}`
- `DELETE /users/{user_id}/tasks/{task_id}`

## 7) Cloud Run Deploy

Build image:

```powershell
gcloud builds submit --config cloudbuild.yaml .
```

Deploy:

```powershell
gcloud run deploy flowagent `
  --image gcr.io/woven-answer-492218-v6/flowagent `
  --region asia-south1 `
  --allow-unauthenticated `
  --set-env-vars GCP_PROJECT_ID=woven-answer-492218-v6,GOOGLE_CLIENT_ID=<id>,GOOGLE_CLIENT_SECRET=<secret>,GOOGLE_REDIRECT_URI=https://<cloud-run-url>/auth/callback,STATE_SECRET=<strong-random>
```

## 8) Scheduling Rules Implemented

- Default timezone: `Asia/Kolkata`
- Default work hours: `09:00` to `19:00`
- 15-minute buffer around busy events
- No scheduling outside working hours unless code is customized
- Deep work preference: morning slots
- Admin preference: post-lunch
- Health tasks preference: lunch/end-day style windows
- Confirmation prompt before writing calendar events

## 9) Notes for Production

- Store OAuth client secret and state secret in Secret Manager.
- Encrypt refresh tokens at rest.
- Add retry/backoff and refresh-token revocation handling.
- Add authentication in front of APIs (IAP/Firebase Auth/Auth0).
