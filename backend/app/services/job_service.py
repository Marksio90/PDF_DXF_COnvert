"""
Job Service — orchestrates the full PDF → DXF conversion pipeline
for a single job.  Runs synchronously inside a background thread.
"""
from __future__ import annotations
import uuid
import traceback
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Job
from app.services.pdf_analyzer import analyze_pdf
from app.services.geometry_extractor import extract_paths, extract_text_blocks
from app.services.geometry_optimizer import optimize_geometry
from app.services.scale_detector import detect_scale
from app.services.dxf_writer import write_dxf
from app.services.preview_service import generate_preview
from app.services.qa_report import build_report


def create_job(db: Session, original_filename: str, pdf_path: str) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        status="queued",
        original_filename=original_filename,
        pdf_path=pdf_path,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_conversion(job_id: str, forced_unit: str | None = None):
    """
    Entry-point called from a background thread / task.
    Opens its own DB session to avoid cross-thread sharing.
    """
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        _run(db, job, forced_unit)
    except Exception as exc:
        db.query(Job).filter(Job.id == job_id).update({
            "status": "error",
            "error_message": f"Unexpected error: {exc}\n{traceback.format_exc()}",
        })
        db.commit()
    finally:
        db.close()


def _run(db: Session, job: Job, forced_unit: str | None):
    def _update(**kwargs):
        for k, v in kwargs.items():
            setattr(job, k, v)
        db.commit()

    # --- Step 1: Analyze PDF ---
    _update(status="analyzing")
    try:
        analysis = analyze_pdf(job.pdf_path)
    except Exception as exc:
        _update(status="error", error_message=f"PDF analysis failed: {exc}")
        return

    _update(
        pdf_type=analysis.pdf_type,
        page_count=analysis.page_count,
        page_width_pt=analysis.width_pt,
        page_height_pt=analysis.height_pt,
    )

    # --- Step 2: Extract geometry ---
    _update(status="converting")
    page_width_pt = analysis.width_pt
    page_height_pt = analysis.height_pt

    try:
        raw_segments, _, _ = extract_paths(job.pdf_path, page_idx=0)
        text_blocks = extract_text_blocks(job.pdf_path, page_idx=0)
    except Exception as exc:
        _update(status="error", error_message=f"Geometry extraction failed: {exc}")
        return

    # --- Step 3: Detect scale ---
    scale_result = detect_scale(text_blocks, forced_unit=forced_unit)

    # --- Step 4: Optimise geometry ---
    # Join tolerance in PDF points (0.5 pt ≈ 0.18 mm at 1:1 scale)
    join_tol_pt = settings.NODE_JOIN_TOLERANCE_MM / scale_result.scale_factor
    try:
        optimised = optimize_geometry(
            raw_segments,
            page_width=page_width_pt,
            page_height=page_height_pt,
            join_tolerance_pt=join_tol_pt,
        )
    except Exception as exc:
        _update(status="error", error_message=f"Geometry optimisation failed: {exc}")
        return

    # --- Step 5: Write DXF ---
    dxf_filename = f"{job.id}.dxf"
    dxf_path = settings.OUTPUTS_DIR / dxf_filename
    try:
        layer_counts = write_dxf(
            optimised_paths=optimised,
            text_blocks=text_blocks,
            page_height_pt=page_height_pt,
            scale_factor=scale_result.scale_factor,
            output_path=str(dxf_path),
            unit=scale_result.unit,
        )
    except Exception as exc:
        _update(status="error", error_message=f"DXF generation failed: {exc}")
        return

    # --- Step 6: Generate preview ---
    preview_filename = f"{job.id}.png"
    preview_path = settings.PREVIEWS_DIR / preview_filename
    generate_preview(job.pdf_path, str(preview_path))

    # --- Step 7: QA report ---
    circles = sum(1 for o in optimised if o["type"] == "circle")
    polylines = sum(1 for o in optimised if o["type"] == "polyline")
    geom_counts = {"circles": circles, "polylines": polylines, **layer_counts}

    report = build_report(
        pdf_type=analysis.pdf_type,
        page_count=analysis.page_count,
        scale_status=scale_result.status,
        scale_unit=scale_result.unit,
        scale_notes=scale_result.notes,
        scale_confidence_delta=scale_result.confidence_delta,
        geometry_counts=geom_counts,
    )

    _update(
        status="done",
        dxf_path=str(dxf_path),
        preview_path=str(preview_path),
        scale_status=scale_result.status,
        scale_factor=scale_result.scale_factor,
        unit=scale_result.unit,
        unit_source=scale_result.source,
        confidence_score=report.confidence_score,
        qa_report=report.to_dict(),
        completed_at=datetime.now(timezone.utc),
    )
