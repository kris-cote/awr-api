# OddLabs AWR API v2.8 — Multi-Tenant Pilot

This release adds tenant-aware SaaS readiness to the AWR Railway API.

## Key additions

- `organization_id` on operational records
- Demo tenant support
- Organization and organization user endpoints
- Tenant-scoped list endpoints for workers, clients, visits, recommendations, approvals, shift offers, audit logs, imports, exports, integrations, and coverage risk
- Tenant-scoped recovery runs and callout simulations
- Tenant-scoped CSV imports
- Tenant-scoped shift offer creation and response handling
- Safety event and safety timer pilot endpoints
- Demo tenant seeding endpoint

## Demo tenants

- `island-community-care`
- `coastal-home-support`
- `north-island-health-ops`

## Important endpoints

- `GET /organizations`
- `GET /tenant/status?organization_id=island-community-care`
- `GET /workers?organization_id=island-community-care`
- `POST /simulate/callout?worker_name=Patricia%20Davis&zone=South&organization_id=island-community-care`
- `POST /recovery/run`
- `GET /recommendations?organization_id=island-community-care`
- `POST /recommendations/approve`
- `POST /shift-offers`
- `GET /shift-offers?organization_id=island-community-care`
- `GET /audit?organization_id=island-community-care`
- `GET /integrations?organization_id=island-community-care`
- `POST /demo/seed-tenants`
- `POST /safety/events`
- `GET /safety/events?organization_id=island-community-care`
- `POST /safety/timers`

## Deployment

Deploy to Railway the same way as earlier releases. Keep Railway Postgres attached and `DATABASE_URL` configured without quotes.

After deploy, check:

- `GET /health`
- `GET /db/status`
- `GET /organizations`
- `GET /tenant/status?organization_id=island-community-care`

If older persisted data exists, v2.8 will migrate missing tenant fields to the default tenant. To load all three clean demo tenants, run:

`POST /demo/seed-tenants`

## Base44 follow-up

Base44 should pass the selected tenant on every API call as either:

- query parameter: `?organization_id=island-community-care`
- JSON body field: `"organization_id": "island-community-care"`

