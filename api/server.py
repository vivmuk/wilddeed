"""WildDeed API — thin wrapper around the dossier pipeline.

Endpoints:
  GET  /               -> the landing page (static site)
  GET  /healthz        -> {"ok": true, "db": bool}
  GET  /api/species    -> quick lookup: species summary for an address (fast, no LLM)
  POST /api/dossiers   -> {"address": "...", "radius": 8, "title": "..."} starts a full dossier job
  GET  /api/dossiers/{id} -> job status (+ summary when done)
  GET  /api/dossiers/{id}/pdf -> the PDF when done
"""
import os, sys, uuid, threading, time, pathlib, datetime
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import wilddeed  # app/wilddeed.py

DB_URL = os.environ.get("DATABASE_URL", "")
JOBS = {}

app = FastAPI(title="WildDeed", version="0.1.0")

class Order(BaseModel):
    address: str = Field(..., min_length=4)
    radius: int = Field(8, ge=1, le=25)
    title: str | None = None

class QuickQuery(BaseModel):
    address: str
    radius: int = Field(8, ge=1, le=25)

def run_job(job_id: str, order: Order):
    job = JOBS[job_id]
    job.update(status="running", started=time.time())
    try:
        result = wilddeed.generate_report(
            address=order.address,
            radius_km=order.radius,
            title=order.title or order.address,
            out_dir=str(ROOT / "reports"),
        )
        job.update(status="done", finished=time.time(), **result)
    except Exception as e:
        job.update(status="error", error=f"{type(e).__name__}: {e}", finished=time.time())

@app.post("/api/dossiers")
def create_dossier(order: Order):
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"id": job_id, "status": "queued", "address": order.address, "radius": order.radius}
    threading.Thread(target=run_job, args=(job_id, order), daemon=True).start()
    return {"id": job_id, "status": "queued"}

@app.get("/api/dossiers/{job_id}")
def get_dossier(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return job

@app.get("/api/dossiers/{job_id}/pdf")
def get_pdf(job_id: str):
    job = JOBS.get(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "not ready")
    return FileResponse(job["pdf"], media_type="application/pdf", filename=f"wilddeed-{job_id}.pdf")


def geocode_any(address: str) -> dict:
    """Census first (best US parcel match), Nominatim fallback (rural coverage)."""
    geo = wilddeed.geocode_census(address)
    if geo:
        return geo
    try:
        import requests as _rq
        r = _rq.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": "WildDeed/0.1 (parcel wildlife dossier)"},
            timeout=30,
        )
        hits = r.json()
        if hits:
            return {"lat": float(hits[0]["lat"]), "lng": float(hits[0]["lon"]),
                    "matched_address": hits[0].get("display_name", address), "all_matches": []}
    except Exception:
        pass
    return {}

@app.post("/api/species")
def quick_species(q: QuickQuery):
    """Fast preview: geocode + GBIF counts + top species. No LLM, no PDF."""
    try:
        geo = geocode_any(q.address)
        if not geo:
            raise HTTPException(422, "address not found by the Census geocoder")
        recs = wilddeed.gbif_search(geo["lat"], geo["lng"], q.radius, min_year=(datetime.date.today().year - wilddeed.DEFAULT_YEARS))
        species = wilddeed.normalize_records(recs.get("records", []))
        flagships = wilddeed.rank_flagships(species)
        top = [
            {"common": s.get("commonName") or s.get("scientificName"),
             "scientific": s.get("scientificName"),
             "records": s.get("count"),
             "last_seen": s.get("lastSeen"),
             "first_seen": s.get("firstSeen"),
             "iucn": s.get("iucn"),
             "game": s.get("isGame"),
             "invasive": s.get("isInvasive")}
            for s in flagships[:12]
        ]
        return {"lat": geo["lat"], "lon": geo["lng"], "matched": geo.get("matched_address"),
                "total_records": recs.get("count", len(recs.get("records", []))),
                "species_count": len(species), "top": top}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")

@app.get("/healthz")
def healthz():
    return {"ok": True, "db": bool(DB_URL)}

SITE = ROOT / "site"
if SITE.exists():
    app.mount("/", StaticFiles(directory=str(SITE), html=True), name="site")
