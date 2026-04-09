"""
REST API routes for PDF → DXF converter.
"""
from __future__ import annotations
import uuid
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Job
from app.services.job_service import create_job, run_conversion

router = APIRouter(prefix="/api")


# ---- Pydantic response schemas -----------------------------------------------

class JobResponse(BaseModel):
    id: str
    status: str
    original_filename: str
    pdf_type: Optional[str]
    page_count: Optional[int]
    scale_status: Optional[str]
    scale_factor: Optional[float]
    unit: Optional[str]
    unit_source: Optional[str]
    confidence_score: Optional[int]
    qa_report: Optional[dict]
    error_message: Optional[str]
    has_preview: bool
    has_dxf: bool
    created_at: str
    completed_at: Optional[str]

    class Config:
        from_attributes = True

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        return cls(
            id=job.id,
            status=job.status,
            original_filename=job.original_filename,
            pdf_type=job.pdf_type,
            page_count=job.page_count,
            scale_status=job.scale_status,
            scale_factor=job.scale_factor,
            unit=job.unit,
            unit_source=job.unit_source,
            confidence_score=job.confidence_score,
            qa_report=job.qa_report,
            error_message=job.error_message,
            has_preview=bool(job.preview_path and Path(job.preview_path).exists()),
            has_dxf=bool(job.dxf_path and Path(job.dxf_path).exists()),
            created_at=str(job.created_at),
            completed_at=str(job.completed_at) if job.completed_at else None,
        )


# ---- Endpoints ---------------------------------------------------------------

@router.post("/jobs", response_model=JobResponse, status_code=202)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    forced_unit: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Check file size
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    contents = await file.read(max_bytes + 1)
    if len(contents) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large (max {settings.MAX_UPLOAD_SIZE_MB} MB).")

    # Save upload
    upload_id = str(uuid.uuid4())
    pdf_path = settings.UPLOADS_DIR / f"{upload_id}.pdf"
    pdf_path.write_bytes(contents)

    job = create_job(db, original_filename=file.filename, pdf_path=str(pdf_path))
    background_tasks.add_task(run_conversion, job.id, forced_unit)
    return JobResponse.from_job(job)


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(100).all()
    return [JobResponse.from_job(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobResponse.from_job(job)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    for path in (job.pdf_path, job.dxf_path, job.preview_path):
        if path:
            p = Path(path)
            if p.exists():
                p.unlink()
    db.delete(job)
    db.commit()


@router.get("/jobs/{job_id}/preview")
def get_preview(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.preview_path or not Path(job.preview_path).exists():
        raise HTTPException(status_code=404, detail="Preview not available.")
    return FileResponse(job.preview_path, media_type="image/png")


@router.get("/jobs/{job_id}/download")
def download_dxf(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != "done":
        raise HTTPException(status_code=400, detail=f"Job is not done yet (status: {job.status}).")
    if not job.dxf_path or not Path(job.dxf_path).exists():
        raise HTTPException(status_code=404, detail="DXF file not found.")

    stem = Path(job.original_filename).stem
    download_name = f"{stem}_converted.dxf"
    return FileResponse(
        job.dxf_path,
        media_type="application/dxf",
        filename=download_name,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


@router.post("/jobs/{job_id}/reconvert", response_model=JobResponse, status_code=202)
async def reconvert(
    job_id: str,
    background_tasks: BackgroundTasks,
    forced_unit: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Re-run conversion with different settings (e.g. forced unit)."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.pdf_path or not Path(job.pdf_path).exists():
        raise HTTPException(status_code=400, detail="Original PDF no longer available.")

    job.status = "queued"
    job.dxf_path = None
    job.preview_path = None
    job.error_message = None
    job.qa_report = None
    job.confidence_score = None
    db.commit()

    background_tasks.add_task(run_conversion, job.id, forced_unit)
    return JobResponse.from_job(job)
