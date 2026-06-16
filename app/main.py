from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

app = FastAPI(
    title="OddLabs AWR Recovery API",
    description="MVP API for Autonomous Workforce Recovery: schedule disruption simulation, replacement scoring, approvals, and export summaries.",
    version="0.1.0",
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

@app.get("/health")
def health():
    return {"status": "ok", "service": "awrid-recovery-api", "version": "0.1.0"}

@app.post("/simulate/callout")
def simulate_callout(worker_name: str, zone: Optional[str] = None):
    return {
        "id": f"disruption-{int(datetime.utcnow().timestamp())}",
        "type": "Worker Callout",
        "worker_name": worker_name,
        "zone": zone,
        "severity": "High",
        "timestamp": datetime.utcnow().isoformat(),
        "description": f"{worker_name} called out. Recovery run required."
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

def score_worker(worker: Worker, visit: Visit) -> Optional[Recommendation]:
    if worker.status != "Active":
        return None
    if visit.assigned_worker and worker.name == visit.assigned_worker:
        return None
    required = set(visit.required_certifications or [])
    held = set(worker.certifications or [])
    cert_match = required.issubset(held) if required else True
    if not cert_match:
        return None
    zone_match = worker.zone == visit.zone
    ot = overtime_risk(worker, visit)
    score = 50
    score += 25 if cert_match else 0
    score += 15 if zone_match else 5
    score += 10 if worker.availability in ["On-Call", "PRN", "Full-Time"] else 5
    score -= {"None": 0, "Low": 5, "Medium": 12, "High": 25}[ot]
    score = max(0, min(100, score))
    continuity = 70 if zone_match else 50
    travel = "Minimal travel impact" if zone_match else f"Cross-zone travel from {worker.zone} to {visit.zone}"
    reasoning = []
    reasoning.append("required certifications match")
    reasoning.append("same zone" if zone_match else "qualified but outside zone")
    reasoning.append(f"overtime risk: {ot.lower()}")
    return Recommendation(
        id=f"rec-{worker.id}-{visit.id}",
        disruption_id="",
        visit_id=visit.id,
        candidate_worker=worker.name,
        candidate_worker_id=worker.id,
        match_score=int(score),
        certification_match=cert_match,
        zone_match=zone_match,
        overtime_risk=ot,
        continuity_score=continuity,
        travel_impact=travel,
        reasoning=", ".join(reasoning),
    )

@app.post("/recovery/run")
def run_recovery(payload: RecoveryRequest):
    disruption = payload.disruption
    impacted = []
    for visit in payload.visits:
        if disruption.worker_name and visit.assigned_worker == disruption.worker_name:
            impacted.append(visit)
        elif disruption.client_name and visit.client_name == disruption.client_name:
            impacted.append(visit)
        elif disruption.zone and visit.zone == disruption.zone and visit.status in ["Unassigned", "Disrupted"]:
            impacted.append(visit)

    recommendations: List[Recommendation] = []
    for visit in impacted:
        for worker in payload.workers:
            rec = score_worker(worker, visit)
            if rec:
                rec.disruption_id = disruption.id
                recommendations.append(rec)

    recommendations = sorted(recommendations, key=lambda r: r.match_score, reverse=True)[:10]
    return {
        "recovery_run_id": f"run-{int(datetime.utcnow().timestamp())}",
        "status": "Completed",
        "disruption": disruption,
        "visits_impacted": len(impacted),
        "recommendations_generated": len(recommendations),
        "recommendations": recommendations,
    }

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
