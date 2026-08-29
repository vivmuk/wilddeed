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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import wilddeed  # app/wilddeed.py

DB_URL = os.environ.get("DATABASE_URL", "")
JOBS = {}

app = FastAPI(title="WildDeed", version="0.1.0")

# The landing page runs the console against this API from any origin (localhost
# previews, the Railway domain, future custom domains). Everything on it is
# public read-only data, so allow all origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

class Order(BaseModel):
    address: str = Field(..., min_length=4)
    radius: int = Field(8, ge=1, le=25)
    title: str | None = None

class QuickQuery(BaseModel):
    address: str
    radius: int = Field(8, ge=1, le=25)

# Per-job progress hook: generate_report calls it with (stage_key, message) as it
# advances; we mirror it into JOBS so GET /api/dossiers/{id} can report live stage.
STAGE_HOOK = {}

def _make_hook(job_id: str):
    def hook(stage_key: str, message: str = ""):
        job = JOBS.get(job_id)
        if job is not None:
            job.update(stage=stage_key, stage_msg=message, stage_t=time.time())
    return hook

def run_job(job_id: str, order: Order):
    job = JOBS[job_id]
    job.update(status="running", started=time.time())
    STAGE_HOOK[job_id] = _make_hook(job_id)
    try:
        # Geocode HERE (Census -> Nominatim fallback) instead of inside generate_report:
        # the engine's geocoder has no rural fallback and exits hard (SystemExit) on no-match.
        job.update(stage="geocoding", stage_i=1)
        geo = geocode_any(order.address)
        if not geo:
            raise RuntimeError("address not found (Census and Nominatim both returned no match)")
        job.update(geo={"lat": geo["lat"], "lng": geo["lng"], "matched": geo.get("matched_address")})
        job.update(stage="gbif search", stage_i=2)
        result = wilddeed.generate_report(
            address=None,  # skip internal geocoding; pass coords directly
            lat=geo["lat"], lng=geo["lng"],
            radius_km=order.radius,
            title=order.title or order.address,
            out_dir=str(ROOT / "reports"),
            on_progress=STAGE_HOOK[job_id],
        )
        job.update(status="done", finished=time.time(), **result)
    except BaseException as e:  # SystemExit and friends must not silently kill the worker
        job.update(status="error", error=f"{type(e).__name__}: {e}", finished=time.time())
    finally:
        STAGE_HOOK.pop(job_id, None)

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
