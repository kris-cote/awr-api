# OddLabs AWR Recovery API

MVP backend for Autonomous Workforce Recovery.

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

1. Create new Railway project.
2. Deploy from GitHub repo.
3. Set start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## MVP endpoints

- `GET /health`
- `POST /simulate/callout`
- `POST /recovery/run`
- `POST /recommendations/approve`
- `GET /export/changes`

## Next upgrades

- Add Postgres persistence
- Add Base44 webhook/API calls
- Add CSV upload parser
- Replace simple scoring with OR-Tools
- Add n8n notification workflows
