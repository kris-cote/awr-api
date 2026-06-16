# OddLabs AWR Recovery API

MVP backend for Autonomous Workforce Recovery.

## Version

`0.2.0`

This update makes `/simulate/callout` return a full recovery payload with ranked recommendations, impacted visits, score breakdown fields, and reasoning.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://localhost:8000/docs
```

## Railway deployment

1. Push this repo to GitHub.
2. Railway redeploys automatically.
3. Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## MVP endpoints

- `GET /health`
- `POST /simulate/callout?worker_name=Patricia%20Davis&zone=South`
- `POST /recovery/run`
- `POST /recommendations/approve`
- `GET /export/changes`

## Base44 integration

Base44's `Run Recovery` button can call:

```text
POST https://web-production-1e39e.up.railway.app/simulate/callout?worker_name=Patricia%20Davis&zone=South
```

Expected response:

```json
{
  "recovery_run_id": "run-...",
  "status": "Completed",
  "disruption": {},
  "visits_impacted": 1,
  "impacted_visits": [],
  "recommendations_generated": 3,
  "recommendations": []
}
```

## Next upgrades

- Store approvals and recovery runs in Postgres
- Add Base44 data-sync endpoint
- Add CSV upload parser
- Replace simple scoring with OR-Tools
- Add n8n notification workflows
