# OddLabs AWR Recovery API v2.5

Pilot v2.5 adds Railway Postgres-backed persistence while preserving the v2 recovery engine.

## Deploy

1. Add a Railway Postgres service to the same project.
2. Make sure Railway injects `DATABASE_URL` into the API service.
3. Deploy this repo.
4. Visit `/health` and `/db/status`.

If `DATABASE_URL` is not present, the API falls back to in-memory mode.

## Important endpoints

- `GET /health`
- `GET /db/status`
- `POST /db/persist`
- `POST /db/reset-demo`
- `GET /demo/data`
- `POST /simulate/callout`
- `POST /recovery/run`
- `POST /recommendations/approve`
- `POST /recommendations/reject`
- `POST /import/workers`
- `POST /import/clients`
- `POST /import/visits`
- `POST /import/constraints`
- `GET /recovery/coverage-risk`
- `GET /pilot/status`
