"""
Scale Detector — tries to determine the drawing scale and unit from:
1. User-forced unit (highest priority)
2. Text found in the PDF
3. Default assumption (mm, 1:1, low confidence)

Returns a ScaleResult with:
  - scale_factor: multiply PDF points by this to get mm
  - unit: "mm" | "inch" | "unknown"
  - status: "verified" | "assumed" | "unverified"
  - source: "forced" | "text" | "default"
  - confidence_delta: penalty to subtract from the base confidence score
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from app.core.config import settings

# 1 PDF point = 1/72 inch = 25.4/72 mm
PT_TO_MM = 25.4 / 72.0
PT_TO_INCH = 1.0 / 72.0

# Patterns that indicate scale in text (order matters – most specific first)
_SCALE_PATTERNS = [
    # "1:1", "SCALE 1:2", "M1:5" etc.
    (re.compile(r"(?:scale|skala|m)\s*(\d+)\s*:\s*(\d+)", re.IGNORECASE), "ratio"),
    # "1/1", "1/2"
    (re.compile(r"(\d+)\s*/\s*(\d+)"), "ratio"),
]

_UNIT_PATTERNS = [
    (re.compile(r"\b(mm|millimetr|millimeter)\b", re.IGNORECASE), "mm"),
    (re.compile(r"\b(inch|in\b|\")", re.IGNORECASE), "inch"),
    (re.compile(r"\b(cm|centimetr|centimeter)\b", re.IGNORECASE), "cm"),
    (re.compile(r"\b(m\b|meter|metre)\b", re.IGNORECASE), "m"),
]


@dataclass
class ScaleResult:
    scale_factor: float = PT_TO_MM       # pt → unit
    unit: str = "mm"
    status: str = "unverified"           # verified | assumed | unverified
    source: str = "default"              # forced | text | default
    ratio_numerator: int = 1
    ratio_denominator: int = 1
    confidence_delta: int = 0            # negative = penalty
    notes: list[str] = field(default_factory=list)


def detect_scale(
    text_blocks: list[dict],
    forced_unit: str | None = None,
) -> ScaleResult:
    result = ScaleResult()

    # 1. User-forced unit
    if forced_unit:
        result.source = "forced"
        result.status = "verified"
        _apply_unit(result, forced_unit.lower().strip())
        result.notes.append(f"Unit forced by user: {forced_unit}")
        return result

    # 2. Search text blocks
    all_text = " ".join(b["text"] for b in text_blocks)

    unit = _detect_unit(all_text)
    ratio = _detect_ratio(all_text)

    if unit:
        _apply_unit(result, unit)
        result.source = "text"

    if ratio:
        result.ratio_numerator, result.ratio_denominator = ratio
        # scale_factor already set to pt→unit; apply the drawing ratio
        result.scale_factor = result.scale_factor * ratio[0] / ratio[1]

    if unit and ratio:
        result.status = "verified"
        result.confidence_delta = 0
        result.notes.append(f"Unit '{unit}' and scale {ratio[0]}:{ratio[1]} found in text.")
    elif unit:
        result.status = "assumed"
        result.confidence_delta = -settings.SCALE_CONFIDENCE_PENALTY_ASSUMED
        result.notes.append(f"Unit '{unit}' found in text; scale ratio not detected (assumed 1:1).")
    elif ratio:
        result.status = "assumed"
        result.confidence_delta = -settings.SCALE_CONFIDENCE_PENALTY_ASSUMED
        _apply_unit(result, "mm")  # default to mm
        result.scale_factor = result.scale_factor * ratio[0] / ratio[1]
        result.notes.append(f"Scale {ratio[0]}:{ratio[1]} found; unit not detected (assumed mm).")
    else:
        # Nothing found
        result.status = "unverified"
        result.source = "default"
        result.confidence_delta = -settings.SCALE_CONFIDENCE_PENALTY_UNKNOWN
        result.notes.append("No scale or unit information found in PDF text.")

    return result


# ---- private helpers --------------------------------------------------------

def _detect_unit(text: str) -> str | None:
    for pattern, unit in _UNIT_PATTERNS:
        if pattern.search(text):
            return unit
    return None


def _detect_ratio(text: str) -> tuple[int, int] | None:
    for pattern, kind in _SCALE_PATTERNS:
        m = pattern.search(text)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > 0 and b > 0:
                return a, b
    return None


def _apply_unit(result: ScaleResult, unit: str):
    if unit == "mm":
        result.unit = "mm"
        result.scale_factor = PT_TO_MM
    elif unit == "cm":
        result.unit = "mm"           # normalise to mm
        result.scale_factor = PT_TO_MM * 10.0
    elif unit == "m":
        result.unit = "mm"
        result.scale_factor = PT_TO_MM * 1000.0
    elif unit in ("inch", "in"):
        result.unit = "inch"
        result.scale_factor = PT_TO_INCH
    else:
        result.unit = "mm"
        result.scale_factor = PT_TO_MM
