from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(
    title="OddLabs AWR Recovery API",
    description=(
        "MVP API for Autonomous Workforce Recovery: disruption simulation, "
        "replacement scoring, approvals, and export summaries."
    ),
    version="0.2.0",
)


class Worker(BaseModel):
    id: str
    name: str
    zone: str
    certifications: List[str] = []
    availability: str = "On-Call"
    max_hours: float = 40
    hours_worked_this_week: float = 0
    travel_radius: float = 20
    restrictions: str = "None"
    status: str = "Active"


class Visit(BaseModel):
    id: str
    client_name: str
    date: str
    time: str
    duration: int
    zone: str
    care_type: str
    required_certifications: List[str] = []
    assigned_worker: Optional[str] = None
    pair_required: bool = False
    status: str = "Scheduled"


class Disruption(BaseModel):
    id: str
    type: str
    worker_name: Optional[str] = None
    client_name: Optional[str] = None
    zone: Optional[str] = None
    severity: str = "Medium"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    description: Optional[str] = None


class Recommendation(BaseModel):
    id: str
    disruption_id: str
    visit_id: str
    candidate_worker: str
    candidate_worker_id: str
    match_score: int
    certification_match: bool
    zone_match: bool
    overtime_risk: str
    continuity_score: int
    travel_impact: str
    reasoning: str
    status: str = "Pending"


class RecoveryRequest(BaseModel):
    disruption: Disruption
    workers: List[Worker]
    visits: List[Visit]


class ApprovalRequest(BaseModel):
    recommendation_id: str
    decided_by: str = "Coordinator"
    notes: Optional[str] = None


DEMO_APPROVALS: List[Dict] = []

DEMO_WORKERS: List[Worker] = [
    Worker(
        id="W017",
        name="Patricia Davis",
        zone="South",
        certifications=["RN", "CPR", "IV Therapy", "Tracheostomy Care"],
        availability="Full-Time",
        max_hours=40,
        hours_worked_this_week=31,
        travel_radius=25,
    ),
    Worker(
        id="W011",
        name="James Rodriguez",
        zone="South",
        certifications=["RN", "CPR", "IV Therapy", "Wound Care"],
        availability="On-Call",
        max_hours=40,
        hours_worked_this_week=26,
        travel_radius=20,
    ),
    Worker(
        id="W014",
        name="Christopher Adams",
        zone="West",
        certifications=["RN", "CPR", "IV Therapy", "Palliative Care"],
        availability="Full-Time",
        max_hours=40,
        hours_worked_this_week=33,
        travel_radius=18,
    ),
    Worker(
        id="W016",
        name="Stephanie Hall",
        zone="Central",
        certifications=["RN", "CPR", "IV Therapy", "Tracheostomy Care"],
        availability="Part-Time",
        max_hours=36,
        hours_worked_this_week=34,
        travel_radius=15,
    ),
    Worker(
        id="W021",
        name="Karen Wilson",
        zone="North",
        certifications=["HCA", "CPR", "First Aid", "Manual Handling"],
        availability="On-Call",
        max_hours=30,
        hours_worked_this_week=10,
        travel_radius=18,
    ),
    Worker(
        id="W007",
        name="David Kim",
        zone="North",
        certifications=["HCA", "CPR", "First Aid", "Dementia Care"],
        availability="On-Call",
        max_hours=40,
        hours_worked_this_week=23,
        travel_radius=18,
    ),
    Worker(
        id="W005",
        name="Sarah Chen",
        zone="North",
        certifications=["HCA", "CPR", "First Aid", "Medication Admin"],
        availability="PRN",
        max_hours=32,
        hours_worked_this_week=27,
        travel_radius=16,
    ),
]

DEMO_VISITS: List[Visit] = [
    Visit(
        id="V001",
        client_name="Nancy Stewart",
        date="2026-06-16",
        time="08:30",
        duration=45,
        zone="South",
        care_type="IV Therapy",
        required_certifications=["RN", "IV Therapy"],
        assigned_worker="Patricia Davis",
        status="Scheduled",
    ),
    Visit(
        id="V002",
        client_name="Frank Patterson",
        date="2026-06-16",
        time="10:00",
        duration=30,
        zone="North",
        care_type="Dementia Care",
        required_certifications=["HCA", "Dementia Care"],
        assigned_worker="Karen Wilson",
        status="Scheduled",
    ),
]


def normalize(value: Optional[str]) -> str:
    return (value or "").strip().lower()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "awrid-recovery-api",
        "version": "0.2.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


def overtime_risk(worker: Worker, visit: Visit) -> str:
    projected = worker.hours_worked_this_week + (visit.duration / 60)
    if projected > worker.max_hours:
        return "High"
    if projected > worker.max_hours - 2:
        return "Medium"
    if projected > worker.max_hours - 5:
        return "Low"
    return "None"


def score_worker(worker: Worker, visit: Visit, disruption_id: str) -> Optional[Recommendation]:
    if worker.status != "Active":
        return None
    if visit.assigned_worker and normalize(worker.name) == normalize(visit.assigned_worker):
        return None

    required = set(visit.required_certifications or [])
    held = set(worker.certifications or [])
    cert_match = required.issubset(held) if required else True
    if not cert_match:
        return None

    zone_match = normalize(worker.zone) == normalize(visit.zone)
    ot = overtime_risk(worker, visit)

    score = 50
    score += 25 if cert_match else 0
    score += 15 if zone_match else 5
    score += 10 if worker.availability in ["On-Call", "PRN", "Full-Time"] else 5
    score -= {"None": 0, "Low": 5, "Medium": 12, "High": 25}[ot]

    # Demo continuity proxy: same-zone care generally improves continuity.
    continuity = 92 if zone_match and ot in ["None", "Low"] else 82 if zone_match else 68
    travel = "Minimal travel impact" if zone_match else f"Cross-zone travel from {worker.zone} to {visit.zone}"

    reasoning_parts = [
        "Required certifications match",
        "same zone" if zone_match else "qualified but outside primary zone",
        f"overtime risk: {ot.lower()}",
        f"availability: {worker.availability}",
    ]

    return Recommendation(
        id=f"rec-{worker.id}-{visit.id}",
        disruption_id=disruption_id,
        visit_id=visit.id,
        candidate_worker=worker.name,
        candidate_worker_id=worker.id,
        match_score=max(0, min(100, int(score))),
        certification_match=cert_match,
        zone_match=zone_match,
        overtime_risk=ot,
        continuity_score=continuity,
        travel_impact=travel,
        reasoning="; ".join(reasoning_parts),
    )


def find_impacted_visits(disruption: Disruption, visits: List[Visit]) -> List[Visit]:
    impacted: List[Visit] = []
    for visit in visits:
        if disruption.worker_name and normalize(visit.assigned_worker) == normalize(disruption.worker_name):
            impacted.append(visit)
        elif disruption.client_name and normalize(visit.client_name) == normalize(disruption.client_name):
            impacted.append(visit)
        elif disruption.zone and normalize(visit.zone) == normalize(disruption.zone) and visit.status in ["Unassigned", "Disrupted"]:
            impacted.append(visit)
    return impacted


def generate_recommendations(disruption: Disruption, workers: List[Worker], visits: List[Visit]) -> Dict:
    impacted = find_impacted_visits(disruption, visits)

    # If Base44 only sends a worker + zone through /simulate/callout, create a useful demo visit.
    if not impacted:
        if normalize(disruption.worker_name) == "patricia davis" or normalize(disruption.zone) == "south":
            impacted = [DEMO_VISITS[0]]
        elif normalize(disruption.worker_name) == "karen wilson" or normalize(disruption.zone) == "north":
            impacted = [DEMO_VISITS[1]]

    recommendations: List[Recommendation] = []
    for visit in impacted:
        for worker in workers:
            rec = score_worker(worker, visit, disruption.id)
            if rec:
                recommendations.append(rec)

    recommendations = sorted(recommendations, key=lambda r: r.match_score, reverse=True)[:10]
    return {
        "recovery_run_id": f"run-{int(datetime.utcnow().timestamp())}",
        "status": "Completed",
        "disruption": disruption,
        "visits_impacted": len(impacted),
        "impacted_visits": impacted,
        "recommendations_generated": len(recommendations),
        "recommendations": recommendations,
    }


@app.post("/simulate/callout")
def simulate_callout(worker_name: str, zone: Optional[str] = None, client_name: Optional[str] = None):
    disruption = Disruption(
        id=f"disruption-{int(datetime.utcnow().timestamp())}",
        type="Worker Callout",
        worker_name=worker_name,
        client_name=client_name,
        zone=zone,
        severity="High",
        timestamp=datetime.utcnow().isoformat(),
        description=f"{worker_name} called out. Recovery recommendations generated.",
    )
    return generate_recommendations(disruption, DEMO_WORKERS, DEMO_VISITS)


@app.post("/recovery/run")
def run_recovery(payload: RecoveryRequest):
    return generate_recommendations(payload.disruption, payload.workers, payload.visits)


@app.post("/recommendations/approve")
def approve_recommendation(request: ApprovalRequest):
    approval = {
        "recommendation_id": request.recommendation_id,
        "decision": "Approved",
        "decided_by": request.decided_by,
        "notes": request.notes,
        "timestamp": datetime.utcnow().isoformat(),
    }
    DEMO_APPROVALS.append(approval)
    return {"status": "approved", "approval": approval}


@app.get("/export/changes")
def export_changes():
    return {
        "export_type": "Approved Changes",
        "generated_at": datetime.utcnow().isoformat(),
        "records_exported": len(DEMO_APPROVALS),
        "records": DEMO_APPROVALS,
    }
