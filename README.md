# OddLabs AWR API - Pilot v2.0

Autonomous Workforce Recovery API for the OddLabs AWR Base44 app.

## What v2.0 adds

- Dynamic worker scoring
- Multi-visit recovery
- Pair-care awareness
- CSV imports for workers, clients, visits, constraints
- Recommendation approval/rejection
- Shift offer lifecycle
- Audit log
- Approved changes export
- Coverage risk endpoint
- Integration readiness endpoints

## Railway start command

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Key endpoints

- `GET /health`
- `GET /pilot/status`
- `POST /simulate/callout`
- `POST /recovery/run`
- `POST /recovery/multi-run`
- `GET /recovery/coverage-risk`
- `GET /recommendations`
- `POST /recommendations/approve`
- `POST /recommendations/reject`
- `POST /shift-offers`
- `POST /shift-offers/{offer_id}/respond`
- `POST /import/workers`
- `POST /import/clients`
- `POST /import/visits`
- `POST /import/constraints`
- `GET /export/changes`
- `GET /export/changes.csv`

## Notes

This is a pilot implementation. It keeps state in process memory for fast demos. For enterprise deployment, connect Postgres, object storage, and vendor connectors.
