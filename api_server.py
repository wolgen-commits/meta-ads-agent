"""
API Server — Next.js dashboard bisa trigger agent via HTTP POST
Run: uvicorn api_server:app --reload --port 8000
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncio
import concurrent.futures
from agent import run_agent
from supabase import create_client
import os

app = FastAPI(title="Meta Ad Library Agent API")

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Track job status sederhana (bisa diganti Redis untuk production)
job_status = {}


class ScrapeRequest(BaseModel):
    competitor_name: str
    country: str = "ID"
    max_ads: int = 20


def _run_agent_in_thread(competitor_name: str, country: str, max_ads: int) -> dict:
    """
    Jalankan agent di thread terpisah dengan event loop baru.
    Diperlukan di Windows karena Playwright tidak bisa launch browser
    subprocess dari dalam event loop FastAPI yang sudah berjalan
    (akan throw NotImplementedError).
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_agent(competitor_name, country, max_ads))
    finally:
        loop.close()


async def run_agent_job(job_id: str, req: ScrapeRequest):
    job_status[job_id] = {"status": "running", "competitor": req.competitor_name}
    try:
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            summary = await loop.run_in_executor(
                pool,
                _run_agent_in_thread,
                req.competitor_name,
                req.country,
                req.max_ads,
            )
        job_status[job_id] = {"status": "done", "summary": summary}
    except Exception as e:
        err_msg = repr(e) if not str(e).strip() else str(e)
        print(f"[Agent ERROR] {err_msg}")
        job_status[job_id] = {"status": "error", "error": err_msg}


@app.post("/api/agent/scrape")
async def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Trigger scraping agent. Berjalan di background.
    Next.js: POST /api/agent/scrape { competitor_name, country, max_ads }
    """
    import uuid
    job_id = str(uuid.uuid4())
    background_tasks.add_task(run_agent_job, job_id, req)
    return {"job_id": job_id, "message": f"Agent mulai scraping {req.competitor_name}"}


@app.get("/api/agent/status/{job_id}")
async def get_job_status(job_id: str):
    """Cek status job scraping."""
    if job_id not in job_status:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return job_status[job_id]


@app.get("/api/ads")
async def get_ads(
    competitor: Optional[str] = None,
    objective: Optional[str] = None,
    limit: int = 50,
):
    """
    Ambil data iklan dari Supabase untuk ditampilkan di dashboard.
    Query params: competitor, objective, limit
    """
    query = supabase.table("competitor_ads").select("*").limit(limit)
    if competitor:
        query = query.eq("competitor_name", competitor)
    if objective:
        query = query.eq("inferred_objective", objective)

    result = query.order("scraped_at", desc=True).execute()
    return {"data": result.data, "count": len(result.data)}


@app.get("/api/ads/summary")
async def get_summary():
    """Ringkasan data untuk widget dashboard."""
    result = supabase.table("competitor_ads").select(
        "competitor_name, inferred_objective, ad_strength_score, creative_strategy"
    ).execute()

    data = result.data
    from collections import Counter

    objectives = Counter(d["inferred_objective"] for d in data if d.get("inferred_objective"))
    strategies = Counter(d["creative_strategy"] for d in data if d.get("creative_strategy"))
    competitors = Counter(d["competitor_name"] for d in data if d.get("competitor_name"))

    avg_score = (
        sum(d["ad_strength_score"] for d in data if d.get("ad_strength_score"))
        / len(data)
        if data else 0
    )

    return {
        "total_ads": len(data),
        "objectives_distribution": dict(objectives),
        "creative_strategies": dict(strategies),
        "ads_per_competitor": dict(competitors),
        "average_strength_score": round(avg_score, 1),
    }
