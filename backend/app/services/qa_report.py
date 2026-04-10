"""
QA / Report — calculates a confidence score and assembles a JSON report
that is stored in the job record and displayed in the frontend.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict


@dataclass
class QAReport:
    confidence_score: int = 100
    pdf_type: str = ""
    page_count: int = 0
    scale_status: str = "unverified"
    scale_unit: str = "mm"
    scale_notes: list[str] = None
    geometry_counts: dict = None
    warnings: list[str] = None

    def __post_init__(self):
        if self.scale_notes is None:
            self.scale_notes = []
        if self.geometry_counts is None:
            self.geometry_counts = {}
        if self.warnings is None:
            self.warnings = []

    def to_dict(self) -> dict:
        return asdict(self)


def build_report(
    pdf_type: str,
    page_count: int,
    scale_status: str,
    scale_unit: str,
    scale_notes: list[str],
    scale_confidence_delta: int,
    geometry_counts: dict,
) -> QAReport:
    report = QAReport(
        confidence_score=100,
        pdf_type=pdf_type,
        page_count=page_count,
        scale_status=scale_status,
        scale_unit=scale_unit,
        scale_notes=scale_notes,
        geometry_counts=geometry_counts,
        warnings=[],
    )

    # Apply scale penalty
    report.confidence_score += scale_confidence_delta  # delta is already negative

    # Penalty for raster PDFs
    if pdf_type == "raster":
        report.confidence_score -= 50
        report.warnings.append(
            "PDF appears to be raster-based. Geometry extraction quality may be poor."
        )

    if pdf_type == "mixed":
        report.confidence_score -= 10
        report.warnings.append(
            "PDF contains both vector and raster content. Some elements may be missing."
        )

    # Scale warnings — tylko gdy faktycznie niepewna
    if scale_status == "assumed":
        report.warnings.append(
            "Skala wykryta z tekstu PDF. Sprawdź wymiary w programie CAD."
        )

    # Geometry warnings
    circles = geometry_counts.get("circles", 0)
    polylines = geometry_counts.get("polylines", 0)
    if circles + polylines == 0:
        report.confidence_score -= 30
        report.warnings.append("No geometry was extracted from the PDF.")

    report.confidence_score = max(0, min(100, report.confidence_score))
    return report
