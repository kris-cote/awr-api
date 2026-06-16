# OddLabs AWR Recovery API v1.0

Pilot-ready backend for Autonomous Workforce Recovery.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `/docs`.

## Railway

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Key endpoints

- `GET /health`
- `GET /demo/data`
- `POST /demo/reset`
- `GET /workers`, `/clients`, `/visits`
- `POST /simulate/callout?worker_name=Patricia%20Davis&zone=South`
- `POST /recovery/run`
- `POST /recommendations/approve`
- `POST /recommendations/reject`
- `POST /shift-offers`
- `GET /audit`
- `GET /integrations`
- `POST /integrations/test`
- `POST /import/workers` CSV upload
- `POST /import/visits` CSV upload
- `GET /export/changes`
- `GET /export/changes.csv`

## Notes

This v1.0 release is pilot-ready, not final enterprise architecture. It uses in-memory storage for fast demo/pilot deployment. The next production hardening step is Postgres persistence plus authentication.
