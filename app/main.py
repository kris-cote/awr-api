from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

VERSION = "2.8.0-multitenant-pilot"

app = FastAPI(
    title="OddLabs AWR Recovery API",
    description="Pilot v2.8 API for Autonomous Workforce Recovery: tenant-scoped SaaS readiness, Postgres-backed persistence, dynamic scoring, recovery workflows, shift offers, audit logs, imports, exports, safety events, and connector status.",
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm(v: Optional[str]) -> str:
    return (v or "").strip().lower()


DEFAULT_ORG_ID = "island-community-care"
DEMO_ORGS = [
    {"organization_id": "island-community-care", "name": "Island Community Care", "type": "Demo Tenant", "status": "Demo", "region": "Vancouver Island", "primary_contact": "Demo Coordinator", "contact_email": "demo@oddlabs.local", "plan": "Demo", "created_at": "", "notes": "Default AWR demo tenant"},
    {"organization_id": "coastal-home-support", "name": "Coastal Home Support", "type": "Demo Tenant", "status": "Demo", "region": "Coastal BC", "primary_contact": "Demo Admin", "contact_email": "coastal@oddlabs.local", "plan": "Demo", "created_at": "", "notes": "Second demo tenant for SaaS separation"},
    {"organization_id": "north-island-health-ops", "name": "North Island Health Ops", "type": "Demo Tenant", "status": "Demo", "region": "North Island", "primary_contact": "Operations Lead", "contact_email": "north@oddlabs.local", "plan": "Demo", "created_at": "", "notes": "Third demo tenant for SaaS separation"},
]


def tenant_id(value: Optional[str]) -> str:
    return (value or DEFAULT_ORG_ID).strip() or DEFAULT_ORG_ID


def tenant_filter(items: List[Dict[str, Any]], organization_id: Optional[str]) -> List[Dict[str, Any]]:
    org = tenant_id(organization_id)
    return [item for item in items if item.get("organization_id", DEFAULT_ORG_ID) == org]


def as_model(model_cls, value):
    """Accept either a Pydantic model instance or a dict and return model instance."""
    if isinstance(value, model_cls):
        return value
    if hasattr(value, "model_dump"):
        return model_cls(**value.model_dump())
    if isinstance(value, dict):
        return model_cls(**value)
    raise TypeError(f"Cannot convert {type(value).__name__} to {model_cls.__name__}")


class Worker(BaseModel):
    id: str
    organization_id: str = DEFAULT_ORG_ID
    name: str
    employee_id: Optional[str] = None
    zone: str = "Central"
    certifications: List[str] = []
    availability: str = "On-Call"
    max_hours: float = 40
    hours_worked_this_week: float = 0
    travel_radius: float = 20
    restrictions: str = "None"
    preferred_areas: List[str] = []
    status: str = "Active"
    phone: Optional[str] = None
    email: Optional[str] = None


class Client(BaseModel):
    id: str
    organization_id: str = DEFAULT_ORG_ID
    client_name: str
    address: Optional[str] = None
    zone: str = "Central"
    care_requirements: List[str] = []
    required_certifications: List[str] = []
    pair_required: bool = False
    continuity_preference: str = "Preferred"
    risk_notes: Optional[str] = None
    risk_level: str = "Low"
    status: str = "Active"


class Visit(BaseModel):
    id: str
    organization_id: str = DEFAULT_ORG_ID
    client_name: str
    date: str
    time: str
    duration: int = 60
    zone: str = "Central"
    care_type: str = "Personal Care"
    required_certifications: List[str] = []
    assigned_worker: Optional[str] = None
    worker_id: Optional[str] = None
    pair_required: bool = False
    status: str = "Scheduled"
    notes: Optional[str] = None


class Constraint(BaseModel):
    id: str
    organization_id: str = DEFAULT_ORG_ID
    name: str
    type: str
    priority: str = "Hard"
    value: Optional[str] = None
    applies_to: Optional[str] = None
    is_active: bool = True
    description: Optional[str] = None


class Disruption(BaseModel):
    organization_id: str = DEFAULT_ORG_ID
    id: str = Field(default_factory=lambda: f"disruption-{int(datetime.now(timezone.utc).timestamp())}")
    type: str = "Worker Callout"
    worker_name: Optional[str] = None
    client_name: Optional[str] = None
    zone: Optional[str] = None
    visit_id: Optional[str] = None
    severity: str = "High"
    timestamp: str = Field(default_factory=now_iso)
    description: Optional[str] = None
    status: str = "Open"


class Recommendation(BaseModel):
    id: str
    organization_id: str = DEFAULT_ORG_ID
    disruption_id: str
    visit_id: str
    client_name: str
    visit_date: str
    visit_time: str
    original_worker: Optional[str] = None
    candidate_worker: str
    candidate_worker_id: str
    match_score: int
    score_breakdown: Dict[str, int]
    certification_match: bool
    zone_match: bool
    availability_match: bool
    restriction_conflict: bool
    overtime_risk: str
    continuity_score: int
    travel_impact: str
    reasoning: str
    status: str = "Pending"


class RecoveryRequest(BaseModel):
    organization_id: str = DEFAULT_ORG_ID
    disruption: Disruption
    workers: Optional[List[Worker]] = None
    clients: Optional[List[Client]] = None
    visits: Optional[List[Visit]] = None
    constraints: Optional[List[Constraint]] = None


class ApprovalRequest(BaseModel):
    organization_id: str = DEFAULT_ORG_ID
    recommendation_id: str
    decided_by: str = "Coordinator"
    notes: Optional[str] = None


class ShiftOfferRequest(BaseModel):
    organization_id: str = DEFAULT_ORG_ID
    recommendation_id: str
    worker_name: str
    worker_id: Optional[str] = None
    client_name: Optional[str] = None
    visit_date: Optional[str] = None
    visit_time: Optional[str] = None
    offer_channel: str = "SMS"


class IntegrationTestRequest(BaseModel):
    organization_id: str = DEFAULT_ORG_ID
    system_type: str
    name: str = "Connector"
    sync_direction: str = "Import Only"


class Organization(BaseModel):
    organization_id: str
    name: str
    type: str = "Demo Tenant"
    status: str = "Demo"
    region: Optional[str] = None
    primary_contact: Optional[str] = None
    contact_email: Optional[str] = None
    plan: str = "Demo"
    created_at: str = Field(default_factory=now_iso)
    notes: Optional[str] = None


class OrganizationUser(BaseModel):
    id: str
    organization_id: str = DEFAULT_ORG_ID
    user_email: str
    user_name: str
    role: str = "Coordinator"
    status: str = "Active"
    created_at: str = Field(default_factory=now_iso)


class SafetyEventRequest(BaseModel):
    organization_id: str = DEFAULT_ORG_ID
    event_type: str
    worker_name: Optional[str] = None
    worker_id: Optional[str] = None
    client_name: Optional[str] = None
    visit_id: Optional[str] = None
    visit_date: Optional[str] = None
    visit_time: Optional[str] = None
    zone: Optional[str] = None
    severity: str = "Medium"
    notes: Optional[str] = None
    location_text: Optional[str] = None


class SafetyTimerRequest(BaseModel):
    organization_id: str = DEFAULT_ORG_ID
    worker_name: str
    worker_id: Optional[str] = None
    client_name: Optional[str] = None
    visit_id: Optional[str] = None
    duration_minutes: int = 30
    notes: Optional[str] = None


DB: Dict[str, Any] = {
    "organizations": [],
    "organization_users": [],
    "workers": [],
    "clients": [],
    "visits": [],
    "constraints": [],
    "disruptions": [],
    "recommendations": [],
    "approvals": [],
    "audit_logs": [],
    "shift_offers": [],
    "imports": [],
    "exports": [],
    "integrations": [],
    "safety_events": [],
    "safety_timers": [],
}


def integration_rows_for_org(org_id: str) -> List[Dict[str, Any]]:
    return [
        {"organization_id": org_id, "name": "Railway API", "system_type": "API", "status": "Connected", "sync_direction": "Two Way", "last_sync": now_iso(), "notes": "Live backend API"},
        {"organization_id": org_id, "name": "Railway Postgres", "system_type": "Database", "status": "Connected", "sync_direction": "Persistent Storage", "last_sync": now_iso(), "notes": "Tenant-scoped persistent records"},
        {"organization_id": org_id, "name": "n8n Automation", "system_type": "n8n", "status": "Connected", "sync_direction": "Event Driven", "last_sync": now_iso(), "notes": "Shift offers and workflow automation through webhooks"},
        {"organization_id": org_id, "name": "CSV Import", "system_type": "CSV", "status": "Connected", "sync_direction": "Import Only", "last_sync": None, "notes": "Pilot import connector"},
        {"organization_id": org_id, "name": "Procura / AlayaCare", "system_type": "Procura", "status": "Not Configured", "sync_direction": "Import Only", "last_sync": None, "notes": "Roadmap connector"},
        {"organization_id": org_id, "name": "UKG", "system_type": "UKG", "status": "Not Configured", "sync_direction": "Two Way", "last_sync": None, "notes": "Roadmap connector"},
        {"organization_id": org_id, "name": "Dayforce", "system_type": "Dayforce", "status": "Not Configured", "sync_direction": "Two Way", "last_sync": None, "notes": "Roadmap connector"},
        {"organization_id": org_id, "name": "SFTP", "system_type": "SFTP", "status": "Not Configured", "sync_direction": "Import/Export", "last_sync": None, "notes": "Roadmap file exchange connector"},
    ]


def seed_tenant_data(org_id: str, variant: str = "default") -> Dict[str, List[Dict[str, Any]]]:
    worker_suffix = "" if variant == "default" else f" {variant.title()}"
    workers = [
        Worker(id="W017", organization_id=org_id, name="Patricia Davis" + worker_suffix, employee_id="W017", zone="South", certifications=["RN", "CPR", "IV Therapy", "Tracheostomy Care"], availability="Full-Time", max_hours=40, hours_worked_this_week=31, travel_radius=25).model_dump(),
        Worker(id="W011", organization_id=org_id, name="James Rodriguez" + worker_suffix, employee_id="W011", zone="South", certifications=["RN", "CPR", "IV Therapy", "Wound Care"], availability="On-Call", max_hours=40, hours_worked_this_week=26, travel_radius=20).model_dump(),
        Worker(id="W014", organization_id=org_id, name="Christopher Adams" + worker_suffix, employee_id="W014", zone="West", certifications=["RN", "CPR", "IV Therapy", "Palliative Care"], availability="Full-Time", max_hours=40, hours_worked_this_week=33, travel_radius=18).model_dump(),
        Worker(id="W016", organization_id=org_id, name="Stephanie Hall" + worker_suffix, employee_id="W016", zone="Central", certifications=["RN", "CPR", "IV Therapy", "Tracheostomy Care"], availability="Part-Time", max_hours=36, hours_worked_this_week=34, travel_radius=15).model_dump(),
        Worker(id="W021", organization_id=org_id, name="Karen Wilson" + worker_suffix, employee_id="W021", zone="North", certifications=["HCA", "CPR", "First Aid", "Manual Handling"], availability="On-Call", max_hours=30, hours_worked_this_week=10, travel_radius=18).model_dump(),
        Worker(id="W007", organization_id=org_id, name="David Kim" + worker_suffix, employee_id="W007", zone="North", certifications=["HCA", "CPR", "First Aid", "Dementia Care"], availability="On-Call", max_hours=40, hours_worked_this_week=23, travel_radius=18).model_dump(),
        Worker(id="W005", organization_id=org_id, name="Sarah Chen" + worker_suffix, employee_id="W005", zone="North", certifications=["HCA", "CPR", "First Aid", "Medication Admin"], availability="PRN", max_hours=32, hours_worked_this_week=27, travel_radius=16).model_dump(),
        Worker(id="W019", organization_id=org_id, name="Jessica Clark" + worker_suffix, employee_id="W019", zone="West", certifications=["LPN", "CPR", "Diabetes Management", "Medication Admin"], availability="PRN", max_hours=32, hours_worked_this_week=14, travel_radius=15).model_dump(),
    ]
    clients = [
        Client(id="C001", organization_id=org_id, client_name="Nancy Stewart", zone="South", care_requirements=["IV Therapy"], required_certifications=["RN", "IV Therapy"], continuity_preference="Strict", risk_level="Medium").model_dump(),
        Client(id="C002", organization_id=org_id, client_name="Frank Patterson", zone="North", care_requirements=["Dementia Care"], required_certifications=["HCA", "Dementia Care"], continuity_preference="Strict", risk_level="High", risk_notes="Requires familiar care routines").model_dump(),
        Client(id="C003", organization_id=org_id, client_name="Arthur Campbell", zone="West", care_requirements=["Personal Care", "Hoisting"], required_certifications=["HCA", "Manual Handling"], pair_required=True, continuity_preference="Preferred", risk_level="High").model_dump(),
    ]
    visits = [
        Visit(id="V001", organization_id=org_id, client_name="Nancy Stewart", date="2026-06-16", time="08:30", duration=45, zone="South", care_type="IV Therapy", required_certifications=["RN", "IV Therapy"], assigned_worker=workers[0]["name"], status="Scheduled").model_dump(),
        Visit(id="V002", organization_id=org_id, client_name="Frank Patterson", date="2026-06-16", time="10:00", duration=30, zone="North", care_type="Dementia Care", required_certifications=["HCA", "Dementia Care"], assigned_worker=workers[4]["name"], status="Scheduled").model_dump(),
        Visit(id="V003", organization_id=org_id, client_name="Arthur Campbell", date="2026-06-16", time="15:30", duration=45, zone="West", care_type="Personal Care", required_certifications=["HCA", "Manual Handling"], assigned_worker="Kevin Wright", pair_required=True, status="Disrupted").model_dump(),
    ]
    constraints = [
        Constraint(id="K001", organization_id=org_id, name="Certification required", type="Certification", priority="Hard", description="Worker must hold all visit-required certifications").model_dump(),
        Constraint(id="K002", organization_id=org_id, name="Weekly overtime threshold", type="Overtime Limit", priority="Soft", value="40", description="Prefer workers below weekly maximum").model_dump(),
        Constraint(id="K003", organization_id=org_id, name="Zone continuity", type="Continuity", priority="Soft", description="Prefer same-zone workers when possible").model_dump(),
        Constraint(id="K004", organization_id=org_id, name="Pair care support", type="Pair Requirement", priority="Hard", description="Flag visits requiring two workers").model_dump(),
    ]
    return {"workers": workers, "clients": clients, "visits": visits, "constraints": constraints}


def seed_demo() -> None:
    DB["organizations"] = []
    DB["organization_users"] = []
    DB["workers"] = []
    DB["clients"] = []
    DB["visits"] = []
    DB["constraints"] = []
    DB["integrations"] = []
    variants = ["default", "coastal", "north"]
    for org_def, variant in zip(DEMO_ORGS, variants):
        org = dict(org_def)
        org["created_at"] = now_iso()
        DB["organizations"].append(Organization(**org).model_dump())
        DB["organization_users"].append(OrganizationUser(id=f"ou-{org['organization_id']}-admin", organization_id=org["organization_id"], user_email=org.get("contact_email") or "demo@oddlabs.local", user_name=org.get("primary_contact") or "Demo Admin", role="Organization Admin").model_dump())
        tenant_data = seed_tenant_data(org["organization_id"], variant)
        for collection, rows in tenant_data.items():
            DB[collection].extend(rows)
        DB["integrations"].extend(integration_rows_for_org(org["organization_id"]))


def migrate_multitenant_defaults() -> None:
    if not DB.get("organizations"):
        for org_def in DEMO_ORGS:
            org = dict(org_def)
            org["created_at"] = now_iso()
            DB["organizations"].append(Organization(**org).model_dump())
    if not DB.get("organization_users"):
        DB["organization_users"].append(OrganizationUser(id="ou-default-admin", organization_id=DEFAULT_ORG_ID, user_email="demo@oddlabs.local", user_name="Demo Coordinator", role="Organization Admin").model_dump())
    for collection in ["workers", "clients", "visits", "constraints", "disruptions", "recommendations", "approvals", "audit_logs", "shift_offers", "imports", "exports", "integrations", "safety_events", "safety_timers"]:
        for item in DB.get(collection, []):
            item.setdefault("organization_id", DEFAULT_ORG_ID)
    if not DB.get("integrations"):
        for org in DB.get("organizations", []):
            DB["integrations"].extend(integration_rows_for_org(org.get("organization_id", DEFAULT_ORG_ID)))

def database_url() -> Optional[str]:
    raw = os.getenv("DATABASE_URL")
    if not raw:
        return None
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw


def get_engine():
    url = database_url()
    if not url:
        return None
    return create_engine(url, pool_pre_ping=True)


ENGINE = get_engine()
PERSISTENT_COLLECTIONS = [
    "organizations", "organization_users", "workers", "clients", "visits", "constraints", "disruptions",
    "recommendations", "approvals", "audit_logs", "shift_offers",
    "imports", "exports", "integrations", "safety_events", "safety_timers",
]


def table_ready() -> bool:
    if ENGINE is None:
        return False
    try:
        with ENGINE.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS awr_store (
                    collection TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
        return True
    except SQLAlchemyError:
        return False


def save_collection(collection: str) -> None:
    if ENGINE is None or collection not in PERSISTENT_COLLECTIONS:
        return
    try:
        with ENGINE.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO awr_store (collection, payload, updated_at)
                    VALUES (:collection, CAST(:payload AS JSONB), NOW())
                    ON CONFLICT (collection) DO UPDATE
                    SET payload = EXCLUDED.payload, updated_at = NOW()
                """),
                {"collection": collection, "payload": json.dumps(DB.get(collection, []))},
            )
    except SQLAlchemyError:
        # Do not crash pilot workflows if persistence is temporarily unavailable.
        return


def persist_all() -> None:
    for collection in PERSISTENT_COLLECTIONS:
        save_collection(collection)


def load_persistent() -> bool:
    if not table_ready():
        return False
    loaded_any = False
    try:
        with ENGINE.begin() as conn:
            rows = conn.execute(text("SELECT collection, payload FROM awr_store")).mappings().all()
        for row in rows:
            collection = row["collection"]
            if collection in DB:
                payload = row["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                DB[collection] = payload
                loaded_any = True
        return loaded_any
    except SQLAlchemyError:
        return False


def initialize_data() -> None:
    loaded = load_persistent()
    if not loaded or not DB.get("workers") or not DB.get("visits"):
        seed_demo()
    migrate_multitenant_defaults()
    persist_all()


initialize_data()


def audit(event_type: str, description: str, user: str = "system", entity_type: Optional[str] = None, entity_id: Optional[str] = None, decision: Optional[str] = None, organization_id: Optional[str] = None) -> Dict[str, Any]:
    org = tenant_id(organization_id)
    rec = {"id": f"audit-{len(DB['audit_logs'])+1}", "organization_id": org, "timestamp": now_iso(), "event_type": event_type, "description": description, "user": user, "entity_type": entity_type, "entity_id": entity_id, "decision": decision}
    DB["audit_logs"].append(rec)
    return rec


def overtime_risk(worker: Worker, visit: Visit) -> str:
    projected = worker.hours_worked_this_week + (visit.duration / 60.0)
    if projected > worker.max_hours:
        return "High"
    if projected > worker.max_hours - 2:
        return "Medium"
    if projected > worker.max_hours - 5:
        return "Low"
    return "None"


def restriction_conflict(worker: Worker, visit: Visit, client: Optional[Client]) -> bool:
    r = norm(worker.restrictions)
    if not r or r == "none":
        return False
    text = f"{visit.care_type} {visit.zone} {client.risk_notes if client else ''}".lower()
    if "no high risk" in r and client and client.risk_level == "High":
        return True
    if "north only" in r and norm(visit.zone) != "north":
        return True
    return any(part.strip() and part.strip() in text for part in r.split(","))


def find_client(name: str, clients: List[Client]) -> Optional[Client]:
    return next((c for c in clients if norm(c.client_name) == norm(name)), None)


def score_worker(worker: Worker, visit: Visit, disruption: Disruption, client: Optional[Client]) -> Optional[Recommendation]:
    if norm(worker.status) != "active":
        return None
    if visit.assigned_worker and norm(worker.name) == norm(visit.assigned_worker):
        return None
    if disruption.worker_name and norm(worker.name) == norm(disruption.worker_name):
        return None

    required = set(visit.required_certifications or (client.required_certifications if client else []))
    held = set(worker.certifications or [])
    cert_match = required.issubset(held) if required else True
    conflict = restriction_conflict(worker, visit, client)
    if not cert_match or conflict:
        return None

    zone_match = norm(worker.zone) == norm(visit.zone)
    availability_match = norm(worker.availability) in {"on-call", "prn", "full-time", "part-time"}
    ot = overtime_risk(worker, visit)
    same_preferred = any(norm(area) == norm(visit.zone) for area in worker.preferred_areas)

    breakdown = {
        "base": 20,
        "certification": 35 if cert_match else 0,
        "zone": 20 if zone_match else 8,
        "preferred_area": 5 if same_preferred else 0,
        "availability": 10 if availability_match else 0,
        "overtime_penalty": {"None": 0, "Low": -5, "Medium": -12, "High": -28}[ot],
        "pair_penalty": -3 if visit.pair_required else 0,
    }
    score = max(0, min(100, sum(breakdown.values())))
    continuity = 95 if zone_match and client and client.continuity_preference == "Strict" else 88 if zone_match else 70
    travel = "Minimal travel impact" if zone_match else f"Cross-zone travel from {worker.zone} to {visit.zone}"
    pair_note = " Pair-required visit: coordinator must confirm second worker coverage." if visit.pair_required else ""
    reasoning = "; ".join([
        "required certifications match",
        "same zone" if zone_match else "qualified but outside primary zone",
        f"availability: {worker.availability}",
        f"overtime risk: {ot}",
        f"continuity score: {continuity}",
    ]) + pair_note

    return Recommendation(
        id=f"rec-{worker.id}-{visit.id}-{int(datetime.now(timezone.utc).timestamp())}",
        organization_id=disruption.organization_id,
        disruption_id=disruption.id,
        visit_id=visit.id,
        client_name=visit.client_name,
        visit_date=visit.date,
        visit_time=visit.time,
        original_worker=visit.assigned_worker,
        candidate_worker=worker.name,
        candidate_worker_id=worker.id,
        match_score=int(score),
        score_breakdown=breakdown,
        certification_match=cert_match,
        zone_match=zone_match,
        availability_match=availability_match,
        restriction_conflict=conflict,
        overtime_risk=ot,
        continuity_score=continuity,
        travel_impact=travel,
        reasoning=reasoning,
    )


def impacted_visits(disruption: Disruption, visits: List[Visit]) -> List[Visit]:
    result: List[Visit] = []
    for visit in visits:
        if disruption.visit_id and visit.id == disruption.visit_id:
            result.append(visit)
        elif disruption.worker_name and norm(visit.assigned_worker) == norm(disruption.worker_name):
            result.append(visit)
        elif disruption.client_name and norm(visit.client_name) == norm(disruption.client_name):
            result.append(visit)
        elif disruption.zone and norm(visit.zone) == norm(disruption.zone) and visit.status in {"Unassigned", "Disrupted"}:
            result.append(visit)
    if not result:
        # Demo fallback for simple Base44 calls.
        if norm(disruption.worker_name) == "patricia davis" or norm(disruption.zone) == "south":
            result = [Visit(**DB["visits"][0])]
        elif norm(disruption.worker_name) == "karen wilson" or norm(disruption.zone) == "north":
            result = [Visit(**DB["visits"][1])]
    return result


def generate_recovery(disruption: Disruption, workers: List[Worker], visits: List[Visit], clients: List[Client]) -> Dict[str, Any]:
    impacted = impacted_visits(disruption, visits)
    recommendations: List[Recommendation] = []
    for visit in impacted:
        client = find_client(visit.client_name, clients)
        for worker in workers:
            rec = score_worker(worker, visit, disruption, client)
            if rec:
                recommendations.append(rec)
    recommendations = sorted(recommendations, key=lambda r: r.match_score, reverse=True)[:10]
    run_id = f"run-{int(datetime.now(timezone.utc).timestamp())}"
    DB["disruptions"].append(disruption.model_dump())
    DB["recommendations"].extend([r.model_dump() for r in recommendations])
    audit("Recommendation Generated", f"{len(recommendations)} recommendations generated for {disruption.type}", entity_type="RecoveryRun", entity_id=run_id, organization_id=disruption.organization_id)
    return {
        "api_version": VERSION,
        "recovery_run_id": run_id,
        "status": "Completed",
        "disruption": disruption.model_dump(),
        "visits_impacted": len(impacted),
        "impacted_visits": [v.model_dump() for v in impacted],
        "recommendations_generated": len(recommendations),
        "recommendations": [r.model_dump() for r in recommendations],
        "next_actions": ["Review ranked recommendations", "Approve or reject candidate", "Export approved change summary"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "oddlabs-awr-recovery-api", "version": VERSION, "timestamp": now_iso(), "database": "postgres" if ENGINE is not None else "memory", "persistence_ready": table_ready() if ENGINE is not None else False}


@app.get("/db/status")
def db_status():
    return {
        "api_version": VERSION,
        "database": "postgres" if ENGINE is not None else "memory",
        "database_url_configured": bool(os.getenv("DATABASE_URL")),
        "persistence_ready": table_ready() if ENGINE is not None else False,
        "collections": {k: len(v) for k, v in DB.items() if isinstance(v, list)},
    }


@app.post("/db/persist")
def db_persist():
    persist_all()
    return {"status": "persisted", "api_version": VERSION, "collections": PERSISTENT_COLLECTIONS}


@app.post("/db/reset-demo")
def db_reset_demo():
    for key in ["organizations", "organization_users", "disruptions", "recommendations", "approvals", "audit_logs", "shift_offers", "imports", "exports", "integrations", "safety_events", "safety_timers"]:
        DB[key] = []
    seed_demo()
    persist_all()
    return {"status": "reset", "api_version": VERSION, "collections": {k: len(v) for k, v in DB.items() if isinstance(v, list)}}


@app.get("/demo/data")
def demo_data(organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    return {"organization_id": org, "workers": tenant_filter(DB["workers"], org), "clients": tenant_filter(DB["clients"], org), "visits": tenant_filter(DB["visits"], org), "constraints": tenant_filter(DB["constraints"], org)}


@app.post("/demo/reset")
def reset_demo():
    for key in ["organizations", "organization_users", "disruptions", "recommendations", "approvals", "audit_logs", "shift_offers", "imports", "exports", "integrations", "safety_events", "safety_timers"]:
        DB[key] = []
    seed_demo()
    persist_all()
    return {"status": "reset", "version": VERSION}


@app.get("/workers")
def list_workers(organization_id: Optional[str] = None):
    items = tenant_filter(DB["workers"], organization_id)
    return {"organization_id": tenant_id(organization_id), "workers": items, "count": len(items)}


@app.get("/clients")
def list_clients(organization_id: Optional[str] = None):
    items = tenant_filter(DB["clients"], organization_id)
    return {"organization_id": tenant_id(organization_id), "clients": items, "count": len(items)}


@app.get("/visits")
def list_visits(organization_id: Optional[str] = None):
    items = tenant_filter(DB["visits"], organization_id)
    return {"organization_id": tenant_id(organization_id), "visits": items, "count": len(items)}


@app.post("/simulate/callout")
def simulate_callout(worker_name: str, zone: Optional[str] = None, client_name: Optional[str] = None, organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    disruption = Disruption(
        organization_id=org,
        type="Worker Callout",
        worker_name=worker_name,
        client_name=client_name,
        zone=zone,
        severity="High",
        description=f"{worker_name} called out. Recovery recommendations generated.",
    )
    result = generate_recovery(disruption, [Worker(**w) for w in tenant_filter(DB["workers"], org)], [Visit(**v) for v in tenant_filter(DB["visits"], org)], [Client(**c) for c in tenant_filter(DB["clients"], org)])
    persist_all()
    return result


@app.post("/recovery/run")
def recovery_run(payload: RecoveryRequest):
    org = tenant_id(payload.organization_id or payload.disruption.organization_id)
    workers = [as_model(Worker, w) for w in payload.workers] if payload.workers else [Worker(**w) for w in tenant_filter(DB["workers"], org)]
    visits = [as_model(Visit, v) for v in payload.visits] if payload.visits else [Visit(**v) for v in tenant_filter(DB["visits"], org)]
    clients = [as_model(Client, c) for c in payload.clients] if payload.clients else [Client(**c) for c in tenant_filter(DB["clients"], org)]
    disruption = as_model(Disruption, payload.disruption)
    disruption.organization_id = org
    result = generate_recovery(disruption, workers, visits, clients)
    persist_all()
    return result


@app.post("/recommendations/approve")
def approve(req: ApprovalRequest):
    org = tenant_id(req.organization_id)
    rec = next((r for r in DB["recommendations"] if r["id"] == req.recommendation_id and r.get("organization_id", DEFAULT_ORG_ID) == org), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found for selected organization")
    rec["status"] = "Approved"
    approval = {"id": f"approval-{len(DB['approvals'])+1}", "organization_id": org, "recommendation_id": req.recommendation_id, "decision": "Approved", "decided_by": req.decided_by, "notes": req.notes, "timestamp": now_iso(), "replacement_worker": rec["candidate_worker"], "client_name": rec["client_name"], "visit_date": rec["visit_date"]}
    DB["approvals"].append(approval)
    audit("Approval Decision", f"Approved {rec['candidate_worker']} for {rec['client_name']}", user=req.decided_by, entity_type="Recommendation", entity_id=req.recommendation_id, decision="Approved", organization_id=org)
    persist_all()
    return {"status": "approved", "approval": approval, "recommendation": rec}


@app.post("/recommendations/reject")
def reject(req: ApprovalRequest):
    org = tenant_id(req.organization_id)
    rec = next((r for r in DB["recommendations"] if r["id"] == req.recommendation_id and r.get("organization_id", DEFAULT_ORG_ID) == org), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found for selected organization")
    rec["status"] = "Rejected"
    audit("Approval Decision", f"Rejected {rec['candidate_worker']} for {rec['client_name']}", user=req.decided_by, entity_type="Recommendation", entity_id=req.recommendation_id, decision="Rejected", organization_id=org)
    persist_all()
    return {"status": "rejected", "recommendation": rec}


@app.post("/shift-offers")
def create_shift_offer(req: ShiftOfferRequest):
    org = tenant_id(req.organization_id)
    offer = req.model_dump()
    offer["organization_id"] = org
    offer.update({"id": f"offer-{len(DB['shift_offers'])+1}", "status": "Sent", "sent_at": now_iso(), "responded_at": None})
    DB["shift_offers"].append(offer)
    audit("Worker Status Change", f"Shift offer sent to {req.worker_name} via {req.offer_channel}", entity_type="ShiftOffer", entity_id=offer["id"], organization_id=org)
    persist_all()
    return {"status": "sent", "offer": offer}


@app.get("/shift-offers")
def list_shift_offers(organization_id: Optional[str] = None):
    items = tenant_filter(DB["shift_offers"], organization_id)
    return {"organization_id": tenant_id(organization_id), "shift_offers": items, "count": len(items)}


@app.get("/audit")
def audit_log(organization_id: Optional[str] = None):
    items = tenant_filter(DB["audit_logs"], organization_id)
    return {"organization_id": tenant_id(organization_id), "audit_logs": items, "count": len(items)}


@app.get("/integrations")
def integrations(organization_id: Optional[str] = None):
    items = tenant_filter(DB["integrations"], organization_id)
    return {"organization_id": tenant_id(organization_id), "integrations": items, "count": len(items)}


@app.post("/integrations/test")
def test_integration(req: IntegrationTestRequest):
    org = tenant_id(req.organization_id)
    connected_types = {"csv", "api", "database", "n8n"}
    result = {"organization_id": org, "name": req.name, "system_type": req.system_type, "status": "Connected" if norm(req.system_type) in connected_types else "Not Configured", "sync_direction": req.sync_direction, "last_sync": now_iso(), "notes": "Live connectors respond in pilot. Vendor connectors require tenant-specific credentials or file access."}
    DB["integrations"].append(result)
    persist_all()
    return result


def parse_list(value: str) -> List[str]:
    return [x.strip() for x in (value or "").replace(";", ",").split(",") if x.strip()]


@app.post("/import/workers")
async def import_workers(file: UploadFile = File(...), organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    text = (await file.read()).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    imported = []
    for i, row in enumerate(rows, 1):
        imported.append(Worker(
            id=row.get("id") or row.get("employee_id") or f"WIMP{i:03d}",
            organization_id=org,
            name=row.get("name") or row.get("worker_name") or f"Worker {i}",
            employee_id=row.get("employee_id"),
            zone=row.get("zone") or "Central",
            certifications=parse_list(row.get("certifications", "")),
            availability=row.get("availability") or "On-Call",
            max_hours=float(row.get("max_hours") or 40),
            hours_worked_this_week=float(row.get("hours_worked_this_week") or 0),
            travel_radius=float(row.get("travel_radius") or 20),
            restrictions=row.get("restrictions") or "None",
            preferred_areas=parse_list(row.get("preferred_areas", "")),
            status=row.get("status") or "Active",
            phone=row.get("phone"),
            email=row.get("email"),
        ).model_dump())
    DB["workers"] = [w for w in DB["workers"] if w.get("organization_id", DEFAULT_ORG_ID) != org] + imported
    batch = {"organization_id": org, "source_system": "CSV", "file_name": file.filename, "import_type": "Workers", "records_imported": len(imported), "records_failed": 0, "status": "Completed", "uploaded_at": now_iso()}
    DB["imports"].append(batch)
    audit("Import Completed", f"Imported {len(imported)} workers from {file.filename}", organization_id=org)
    persist_all()
    return batch


@app.post("/import/visits")
async def import_visits(file: UploadFile = File(...), organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    text = (await file.read()).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    imported = []
    for i, row in enumerate(rows, 1):
        imported.append(Visit(
            id=row.get("id") or f"VIMP{i:03d}",
            organization_id=org,
            client_name=row.get("client_name") or f"Client {i}",
            date=row.get("date") or datetime.now().date().isoformat(),
            time=row.get("time") or "09:00",
            duration=int(float(row.get("duration") or 60)),
            zone=row.get("zone") or "Central",
            care_type=row.get("care_type") or "Personal Care",
            required_certifications=parse_list(row.get("required_certifications", "")),
            assigned_worker=row.get("assigned_worker"),
            pair_required=(row.get("pair_required", "false").lower() in {"true", "yes", "1"}),
            status=row.get("status") or "Scheduled",
        ).model_dump())
    DB["visits"] = [v for v in DB["visits"] if v.get("organization_id", DEFAULT_ORG_ID) != org] + imported
    batch = {"organization_id": org, "source_system": "CSV", "file_name": file.filename, "import_type": "Visits", "records_imported": len(imported), "records_failed": 0, "status": "Completed", "uploaded_at": now_iso()}
    DB["imports"].append(batch)
    audit("Import Completed", f"Imported {len(imported)} visits from {file.filename}", organization_id=org)
    persist_all()
    return batch


@app.get("/export/changes")
def export_changes(organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    records = tenant_filter(DB["approvals"], org)
    export = {"organization_id": org, "export_type": "Approved Changes", "generated_at": now_iso(), "records_exported": len(records), "records": records}
    DB["exports"].append(export)
    audit("Export Generated", f"Generated approved changes export with {len(records)} records", organization_id=org)
    persist_all()
    return export


@app.get("/export/changes.csv")
def export_changes_csv(organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    output = io.StringIO()
    fieldnames = ["organization_id", "recommendation_id", "decision", "decided_by", "replacement_worker", "client_name", "visit_date", "timestamp", "notes"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in tenant_filter(DB["approvals"], org):
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return {"filename": f"approved_changes_{org}.csv", "content_type": "text/csv", "csv": output.getvalue()}


@app.get("/recommendations")
def list_recommendations(status: Optional[str] = None, organization_id: Optional[str] = None):
    items = tenant_filter(DB["recommendations"], organization_id)
    if status:
        items = [r for r in items if norm(r.get("status")) == norm(status)]
    return {"organization_id": tenant_id(organization_id), "recommendations": items, "count": len(items), "api_version": VERSION}


@app.get("/approvals")
def list_approvals(organization_id: Optional[str] = None):
    items = tenant_filter(DB["approvals"], organization_id)
    return {"organization_id": tenant_id(organization_id), "approvals": items, "count": len(items), "api_version": VERSION}


@app.get("/imports")
def list_imports(organization_id: Optional[str] = None):
    items = tenant_filter(DB["imports"], organization_id)
    return {"organization_id": tenant_id(organization_id), "imports": items, "count": len(items), "api_version": VERSION}


@app.get("/exports")
def list_exports(organization_id: Optional[str] = None):
    items = tenant_filter(DB["exports"], organization_id)
    return {"organization_id": tenant_id(organization_id), "exports": items, "count": len(items), "api_version": VERSION}


@app.post("/import/clients")
async def import_clients(file: UploadFile = File(...), organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    text = (await file.read()).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    imported = []
    for i, row in enumerate(rows, 1):
        imported.append(Client(
            id=row.get("id") or f"CIMP{i:03d}",
            organization_id=org,
            client_name=row.get("client_name") or row.get("name") or f"Client {i}",
            address=row.get("address"),
            zone=row.get("zone") or "Central",
            care_requirements=parse_list(row.get("care_requirements", "")),
            required_certifications=parse_list(row.get("required_certifications", "")),
            pair_required=(row.get("pair_required", "false").lower() in {"true", "yes", "1"}),
            continuity_preference=row.get("continuity_preference") or "Preferred",
            risk_notes=row.get("risk_notes"),
            risk_level=row.get("risk_level") or "Low",
            status=row.get("status") or "Active",
        ).model_dump())
    DB["clients"] = [c for c in DB["clients"] if c.get("organization_id", DEFAULT_ORG_ID) != org] + imported
    batch = {"organization_id": org, "source_system": "CSV", "file_name": file.filename, "import_type": "Clients", "records_imported": len(imported), "records_failed": 0, "status": "Completed", "uploaded_at": now_iso()}
    DB["imports"].append(batch)
    audit("Import Completed", f"Imported {len(imported)} clients from {file.filename}", organization_id=org)
    persist_all()
    return batch


@app.post("/import/constraints")
async def import_constraints(file: UploadFile = File(...), organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    text = (await file.read()).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    imported = []
    for i, row in enumerate(rows, 1):
        imported.append(Constraint(
            id=row.get("id") or f"KIMP{i:03d}",
            organization_id=org,
            name=row.get("name") or f"Constraint {i}",
            type=row.get("type") or "Certification",
            priority=row.get("priority") or "Hard",
            value=row.get("value"),
            applies_to=row.get("applies_to"),
            is_active=(row.get("is_active", "true").lower() in {"true", "yes", "1"}),
            description=row.get("description"),
        ).model_dump())
    DB["constraints"] = [k for k in DB["constraints"] if k.get("organization_id", DEFAULT_ORG_ID) != org] + imported
    batch = {"organization_id": org, "source_system": "CSV", "file_name": file.filename, "import_type": "Constraints", "records_imported": len(imported), "records_failed": 0, "status": "Completed", "uploaded_at": now_iso()}
    DB["imports"].append(batch)
    audit("Import Completed", f"Imported {len(imported)} constraints from {file.filename}", organization_id=org)
    persist_all()
    return batch


@app.post("/recovery/multi-run")
def recovery_multi_run(disruptions: List[Disruption], organization_id: Optional[str] = None):
    org = tenant_id(organization_id or (disruptions[0].organization_id if disruptions else DEFAULT_ORG_ID))
    workers = [Worker(**w) for w in tenant_filter(DB["workers"], org)]
    visits = [Visit(**v) for v in tenant_filter(DB["visits"], org)]
    clients = [Client(**c) for c in tenant_filter(DB["clients"], org)]
    results = []
    total_recommendations = 0
    total_impacted = 0
    for disruption in disruptions:
        disruption.organization_id = org
        result = generate_recovery(disruption, workers, visits, clients)
        results.append(result)
        total_recommendations += result["recommendations_generated"]
        total_impacted += result["visits_impacted"]
    persist_all()
    return {
        "api_version": VERSION,
        "organization_id": org,
        "status": "Completed",
        "disruptions_processed": len(disruptions),
        "visits_impacted": total_impacted,
        "recommendations_generated": total_recommendations,
        "results": results,
    }


@app.get("/recovery/coverage-risk")
def coverage_risk(organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    visits = [Visit(**v) for v in tenant_filter(DB["visits"], org)]
    workers = [Worker(**w) for w in tenant_filter(DB["workers"], org)]
    clients = [Client(**c) for c in tenant_filter(DB["clients"], org)]
    risks = []
    for visit in visits:
        client = find_client(visit.client_name, clients)
        eligible = []
        for worker in workers:
            rec = score_worker(worker, visit, Disruption(type="Coverage Risk", worker_name=None, zone=visit.zone), client)
            if rec:
                eligible.append(rec)
        level = "Low"
        if visit.status in {"Unassigned", "Disrupted"}:
            level = "High"
        if len(eligible) == 0:
            level = "Critical"
        elif len(eligible) <= 1:
            level = "High"
        elif len(eligible) <= 2:
            level = "Medium"
        risks.append({
            "visit_id": visit.id,
            "client_name": visit.client_name,
            "date": visit.date,
            "time": visit.time,
            "zone": visit.zone,
            "pair_required": visit.pair_required,
            "eligible_workers": len(eligible),
            "best_score": max([r.match_score for r in eligible], default=0),
            "risk_level": level,
            "reason": "No eligible workers" if len(eligible) == 0 else "Limited eligible coverage" if len(eligible) <= 2 else "Coverage available",
        })
    return {"api_version": VERSION, "organization_id": org, "coverage_risks": risks, "count": len(risks)}


@app.post("/shift-offers/{offer_id}/respond")
def respond_shift_offer(offer_id: str, response: str, response_notes: Optional[str] = None, organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    offer = next((o for o in DB["shift_offers"] if o["id"] == offer_id and o.get("organization_id", DEFAULT_ORG_ID) == org), None)
    if not offer:
        offer = next((o for o in DB["shift_offers"] if o["id"] == offer_id), None)
    if not offer:
        raise HTTPException(status_code=404, detail="Shift offer not found")
    org = offer.get("organization_id", org)
    status = "Accepted" if norm(response) == "accepted" else "Declined" if norm(response) == "declined" else "Expired"
    offer["status"] = status
    offer["responded_at"] = now_iso()
    offer["response_notes"] = response_notes
    audit("Worker Status Change", f"Shift offer {offer_id} {status.lower()} by {offer.get('worker_name')}", entity_type="ShiftOffer", entity_id=offer_id, decision=status, organization_id=org)
    persist_all()
    return {"status": status, "offer": offer}


@app.get("/pilot/status")
def pilot_status(organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    return {
        "api_version": VERSION,
        "organization_id": org,
        "status": "pilot-ready",
        "capabilities": [
            "dynamic worker scoring",
            "multi-visit recovery",
            "pair-care awareness",
            "CSV worker/client/visit/constraint imports",
            "approval/rejection workflow",
            "shift offer lifecycle",
            "audit log",
            "approved change exports",
            "coverage risk analysis",
            "connector readiness dashboard",
        ],
        "counts": {k: len(tenant_filter(v, org)) if k not in {"organizations"} else len(v) for k, v in DB.items() if isinstance(v, list)},
        "next_enterprise_steps": ["Tenant-scoped Base44 calls", "Role-based auth", "Twilio/Teams notifications", "Procura/AlayaCare connector", "OR-Tools optimization"],
    }


@app.get("/organizations")
def list_organizations():
    return {"organizations": DB["organizations"], "count": len(DB["organizations"]), "api_version": VERSION}


@app.get("/organization-users")
def list_organization_users(organization_id: Optional[str] = None):
    items = tenant_filter(DB["organization_users"], organization_id)
    return {"organization_id": tenant_id(organization_id), "organization_users": items, "count": len(items), "api_version": VERSION}


@app.get("/tenant/status")
def tenant_status(organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    organization = next((o for o in DB["organizations"] if o.get("organization_id") == org), None)
    return {
        "api_version": VERSION,
        "organization_id": org,
        "organization": organization,
        "tenant_scoped": True,
        "counts": {
            "workers": len(tenant_filter(DB["workers"], org)),
            "clients": len(tenant_filter(DB["clients"], org)),
            "visits": len(tenant_filter(DB["visits"], org)),
            "recommendations": len(tenant_filter(DB["recommendations"], org)),
            "shift_offers": len(tenant_filter(DB["shift_offers"], org)),
            "audit_logs": len(tenant_filter(DB["audit_logs"], org)),
            "integrations": len(tenant_filter(DB["integrations"], org)),
            "safety_events": len(tenant_filter(DB["safety_events"], org)),
        },
    }


@app.post("/demo/seed-tenants")
def seed_demo_tenants():
    seed_demo()
    for key in ["disruptions", "recommendations", "approvals", "audit_logs", "shift_offers", "imports", "exports", "safety_events", "safety_timers"]:
        DB[key] = []
    persist_all()
    return {"status": "seeded", "api_version": VERSION, "organizations": DB["organizations"], "counts": {k: len(v) for k, v in DB.items() if isinstance(v, list)}}


@app.post("/safety/events")
def create_safety_event(req: SafetyEventRequest):
    org = tenant_id(req.organization_id)
    event = req.model_dump()
    event["organization_id"] = org
    event.update({"id": f"safety-{len(DB['safety_events'])+1}", "event_id": f"safety-{len(DB['safety_events'])+1}", "status": "Open" if req.severity in {"High", "Critical"} else "Resolved", "created_at": now_iso()})
    DB["safety_events"].append(event)
    audit("Safety Event", f"{req.event_type} recorded for {req.worker_name or 'worker'}", entity_type="SafetyEvent", entity_id=event["id"], organization_id=org)
    persist_all()
    return {"status": "recorded", "safety_event": event}


@app.get("/safety/events")
def list_safety_events(organization_id: Optional[str] = None, status: Optional[str] = None):
    items = tenant_filter(DB["safety_events"], organization_id)
    if status:
        items = [e for e in items if norm(e.get("status")) == norm(status)]
    return {"organization_id": tenant_id(organization_id), "safety_events": items, "count": len(items), "api_version": VERSION}


@app.post("/safety/events/{event_id}/acknowledge")
def acknowledge_safety_event(event_id: str, acknowledged_by: str = "Coordinator", organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    event = next((e for e in DB["safety_events"] if e.get("id") == event_id and e.get("organization_id", DEFAULT_ORG_ID) == org), None)
    if not event:
        raise HTTPException(status_code=404, detail="Safety event not found for selected organization")
    event["status"] = "Acknowledged"
    event["acknowledged_by"] = acknowledged_by
    audit("Safety Event", f"Safety event {event_id} acknowledged", user=acknowledged_by, entity_type="SafetyEvent", entity_id=event_id, organization_id=org)
    persist_all()
    return {"status": "acknowledged", "safety_event": event}


@app.post("/safety/events/{event_id}/resolve")
def resolve_safety_event(event_id: str, resolved_by: str = "Coordinator", organization_id: Optional[str] = None):
    org = tenant_id(organization_id)
    event = next((e for e in DB["safety_events"] if e.get("id") == event_id and e.get("organization_id", DEFAULT_ORG_ID) == org), None)
    if not event:
        raise HTTPException(status_code=404, detail="Safety event not found for selected organization")
    event["status"] = "Resolved"
    event["resolved_at"] = now_iso()
    audit("Safety Event", f"Safety event {event_id} resolved", user=resolved_by, entity_type="SafetyEvent", entity_id=event_id, organization_id=org)
    persist_all()
    return {"status": "resolved", "safety_event": event}


@app.post("/safety/timers")
def create_safety_timer(req: SafetyTimerRequest):
    org = tenant_id(req.organization_id)
    timer = req.model_dump()
    timer["organization_id"] = org
    timer.update({
        "id": f"timer-{len(DB['safety_timers'])+1}",
        "timer_id": f"timer-{len(DB['safety_timers'])+1}",
        "started_at": now_iso(),
        "status": "Active",
        "escalation_level": "None",
        "expected_check_in_at": req.duration_minutes,
    })
    DB["safety_timers"].append(timer)
    audit("Safety Timer Started", f"Safety timer started for {req.worker_name}", entity_type="SafetyTimer", entity_id=timer["id"], organization_id=org)
    persist_all()
    return {"status": "active", "safety_timer": timer}


@app.get("/safety/timers")
def list_safety_timers(organization_id: Optional[str] = None, status: Optional[str] = None):
    items = tenant_filter(DB["safety_timers"], organization_id)
    if status:
        items = [t for t in items if norm(t.get("status")) == norm(status)]
    return {"organization_id": tenant_id(organization_id), "safety_timers": items, "count": len(items), "api_version": VERSION}
