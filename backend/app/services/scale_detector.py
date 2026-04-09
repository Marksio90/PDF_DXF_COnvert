"""
Scale Detector — determines the drawing scale and physical unit.

Priority order:
1. User-forced unit (highest)
2. Dimension-text correlation: find numeric labels and match to nearby geometry
3. Text-based: parse "scale 1:2", "mm", etc. from PDF text
4. PDF UserUnit from page metadata
5. Default: PT_TO_MM, status=unverified

Returns ScaleResult with:
  scale_factor : multiply raw PDF coordinates (pt) by this to get the target unit
  unit         : "mm" | "inch"
  status       : "verified" | "assumed" | "unverified"
  source       : "forced" | "dimension" | "text" | "userunit" | "default"
  confidence_delta : negative = penalty applied to confidence score
"""
from __future__ import annotations
import re
import math
import statistics
from dataclasses import dataclass, field
from app.core.config import settings

PT_TO_MM   = 25.4 / 72.0       # 1 PDF point → mm
PT_TO_INCH = 1.0  / 72.0       # 1 PDF point → inch

_SCALE_PATTERNS = [
    (re.compile(r"(?:scale|skala|m)\s*(\d+)\s*:\s*(\d+)", re.IGNORECASE), "ratio"),
    (re.compile(r"(\d+)\s*/\s*(\d+)"), "ratio"),
]

_UNIT_PATTERNS = [
    (re.compile(r"\b(mm|millimetr|millimeter)\b", re.IGNORECASE), "mm"),
    (re.compile(r"\b(inch|in\b|\")",              re.IGNORECASE), "inch"),
    (re.compile(r"\b(cm|centimetr|centimeter)\b", re.IGNORECASE), "cm"),
    (re.compile(r"\b(m\b|meter|metre)\b",         re.IGNORECASE), "m"),
]

# Numeric text that could be a dimension value (not a year, quantity, etc.)
_DIM_VALUE_RE = re.compile(r"^(\d{1,4}(?:[.,]\d{1,3})?)$")


@dataclass
class ScaleResult:
    scale_factor: float        = PT_TO_MM
    unit: str                  = "mm"
    status: str                = "unverified"   # verified|assumed|unverified
    source: str                = "default"      # forced|dimension|text|userunit|default
    ratio_numerator: int       = 1
    ratio_denominator: int     = 1
    confidence_delta: int      = 0
    notes: list[str]           = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_scale(
    text_blocks: list[dict],
    raw_segments: list[dict] | None = None,
    forced_unit: str | None = None,
    pdf_path: str | None = None,
    page_idx: int = 0,
) -> ScaleResult:
    result = ScaleResult()

    # 1. User-forced
    if forced_unit:
        result.source = "forced"
        result.status = "verified"
        _apply_unit(result, forced_unit.lower().strip())
        result.notes.append(f"Jednostka wymuszona przez użytkownika: {forced_unit}")
        return result

    # 2. Dimension-text correlation (most reliable for CAD PDFs)
    if raw_segments:
        dim_sf, dim_note = _detect_from_dimensions(text_blocks, raw_segments)
        if dim_sf is not None:
            result.scale_factor    = dim_sf
            result.unit            = "mm"
            result.status          = "verified"
            result.source          = "dimension"
            result.confidence_delta = 0
            result.notes.append(dim_note)
            return result

    # 3. PDF UserUnit metadata
    if pdf_path:
        uu_sf = _detect_userunit(pdf_path, page_idx)
        if uu_sf is not None:
            result.scale_factor    = uu_sf
            result.unit            = "mm"
            result.status          = "assumed"
            result.source          = "userunit"
            result.confidence_delta = -settings.SCALE_CONFIDENCE_PENALTY_ASSUMED
            result.notes.append(
                f"Wykryto UserUnit w PDF: scale_factor={uu_sf:.6f} (≈ {'mm' if abs(uu_sf-1.0)<0.05 else 'pt→mm'})"
            )
            # fall through to also check text for ratio
            # (don't return yet — might find ratio in text)

    # 4. Text-based detection
    all_text = " ".join(b["text"] for b in text_blocks)
    text_unit  = _detect_unit(all_text)
    text_ratio = _detect_ratio(all_text)

    if text_unit or text_ratio:
        # Start fresh from PT_TO_MM base unless userunit already set
        if result.source != "userunit":
            _apply_unit(result, text_unit or "mm")

        if text_ratio:
            result.ratio_numerator, result.ratio_denominator = text_ratio
            result.scale_factor *= text_ratio[0] / text_ratio[1]

        if text_unit and text_ratio:
            result.status          = "verified"
            result.confidence_delta = 0
            result.source          = "text"
            result.notes.append(
                f"Jednostka '{text_unit}' i skala {text_ratio[0]}:{text_ratio[1]} z tekstu PDF."
            )
        elif text_unit:
            result.status          = "assumed"
            result.confidence_delta = -settings.SCALE_CONFIDENCE_PENALTY_ASSUMED
            result.source          = "text"
            result.notes.append(
                f"Jednostka '{text_unit}' z tekstu PDF; skala nieznana (przyjęto 1:1)."
            )
        elif text_ratio:
            result.status          = "assumed"
            result.confidence_delta = -settings.SCALE_CONFIDENCE_PENALTY_ASSUMED
            result.source          = "text"
            result.notes.append(
                f"Skala {text_ratio[0]}:{text_ratio[1]} z tekstu; brak jednostki (przyjęto mm)."
            )
        return result

    # 5. Default
    if result.source == "userunit":
        return result  # keep userunit result

    result.status          = "unverified"
    result.source          = "default"
    result.confidence_delta = -settings.SCALE_CONFIDENCE_PENALTY_UNKNOWN
    result.notes.append(
        "Brak danych o skali w tekście PDF. Zastosowano domyślne przeliczenie pt→mm."
    )
    return result


# ---------------------------------------------------------------------------
# Dimension-text correlation
# ---------------------------------------------------------------------------

def _detect_from_dimensions(
    text_blocks: list[dict],
    raw_segments: list[dict],
    min_matches: int = 3,
) -> tuple[float | None, str]:
    """
    Correlate numeric text labels with line lengths in the PDF coordinate
    system to recover the actual pt-per-mm ratio.

    Returns (scale_factor, note) or (None, "").
    """
    # Collect candidate dimension values (numeric-only blocks)
    candidates: list[dict] = []
    for blk in text_blocks:
        txt = blk["text"].strip().replace(",", ".")
        m = _DIM_VALUE_RE.match(txt)
        if not m:
            continue
        val = float(m.group(1))
        if val < 1.0 or val > 3000.0:
            continue
        cx = (blk["x0"] + blk["x1"]) / 2
        cy = (blk["y0"] + blk["y1"]) / 2
        candidates.append({"value": val, "cx": cx, "cy": cy})

    if not candidates:
        return None, ""

    # Collect H/V line lengths from raw segments
    hv_lines: list[dict] = []
    for seg in raw_segments:
        pts = seg.get("points", [])
        if len(pts) < 2:
            continue
        p0, p1 = pts[0], pts[-1]
        dx = abs(p1[0] - p0[0])
        dy = abs(p1[1] - p0[1])
        length = math.hypot(dx, dy)
        if length < 1.0:
            continue
        # Accept lines that are at least 80% horizontal or vertical
        if dy < 0.25 * dx or dx < 0.25 * dy:
            hv_lines.append({
                "length": length,
                "cx": (p0[0] + p1[0]) / 2,
                "cy": (p0[1] + p1[1]) / 2,
            })

    if not hv_lines:
        return None, ""

    # For each candidate, find the closest line whose length is proportional
    # to the candidate value within a plausible scale factor range
    SCALE_MIN = 0.20   # compressed DXF (1pt ~ 0.2mm, scale ~5:1 printout)
    SCALE_MAX = 5.0    # expanded DXF
    ratios: list[float] = []

    for cand in candidates:
        val = cand["value"]
        for line in hv_lines:
            # Distance text↔line centre (in PDF pt)
            dist = math.hypot(cand["cx"] - line["cx"], cand["cy"] - line["cy"])
            # Allow proximity up to 3× the line length
            if dist > max(line["length"] * 3, 50):
                continue
            ratio = line["length"] / val   # pt per "mm" (or whatever unit)
            if SCALE_MIN <= ratio <= SCALE_MAX:
                ratios.append(ratio)

    if len(ratios) < min_matches:
        return None, ""

    # Cluster ratios and pick the largest consistent group
    ratios.sort()
    best_group: list[float] = []
    i = 0
    while i < len(ratios):
        group = [ratios[i]]
        j = i + 1
        while j < len(ratios) and abs(ratios[j] - ratios[i]) / ratios[i] < 0.15:
            group.append(ratios[j])
            j += 1
        if len(group) > len(best_group):
            best_group = group
        i = j

    if len(best_group) < min_matches:
        return None, ""

    median_ratio = statistics.median(best_group)
    # median_ratio is PDF-pt per user-unit (assumed mm)
    # scale_factor (to convert pt → mm) = 1 / median_ratio… wait.
    # Actually:  line_length_pt / dim_value_mm = pt_per_mm
    # To get mm from pt:  mm = pt / pt_per_mm = pt * (1/pt_per_mm)
    # But our dxf_writer does:  coordinate_dxf = coordinate_pt * scale_factor
    # So:  scale_factor = 1 / pt_per_mm
    scale_factor = 1.0 / median_ratio
    note = (
        f"Skala wykryta z korelacji {len(best_group)} wymiarów: "
        f"~{median_ratio:.4f} pt/mm → scale_factor={scale_factor:.6f}"
    )
    return scale_factor, note


# ---------------------------------------------------------------------------
# UserUnit detection
# ---------------------------------------------------------------------------

def _detect_userunit(pdf_path: str, page_idx: int) -> float | None:
    """
    Read /UserUnit from the PDF page dictionary.
    Returns the effective pt→mm scale_factor, or None if unavailable.
    """
    try:
        import fitz
        doc = fitz.open(pdf_path)
        page = doc[page_idx]
        xref = page.xref
        raw = doc.xref_get_key(xref, "UserUnit")
        doc.close()
        if raw and raw[0] != "null":
            user_unit = float(raw[1])   # user_unit = physical inches × 72
            if abs(user_unit - 1.0) < 0.01:
                # Default: 1 user unit = 1pt = 1/72 inch → convert to mm
                return PT_TO_MM
            # Each user unit = user_unit/72 inches = user_unit*25.4/72 mm
            mm_per_unit = user_unit * 25.4 / 72.0
            if abs(mm_per_unit - 1.0) < 0.05:
                # coordinates already in mm
                return 1.0
            return mm_per_unit
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_unit(text: str) -> str | None:
    for pattern, unit in _UNIT_PATTERNS:
        if pattern.search(text):
            return unit
    return None


def _detect_ratio(text: str) -> tuple[int, int] | None:
    for pattern, _ in _SCALE_PATTERNS:
        m = pattern.search(text)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > 0 and b > 0:
                return a, b
    return None


def _apply_unit(result: ScaleResult, unit: str):
    """Set scale_factor according to unit string."""
    if unit in ("mm_direct", "mm_native"):
        # PDF coordinates already in mm — no conversion
        result.unit         = "mm"
        result.scale_factor = 1.0
    elif unit == "mm":
        result.unit         = "mm"
        result.scale_factor = PT_TO_MM
    elif unit == "cm":
        result.unit         = "mm"
        result.scale_factor = PT_TO_MM * 10.0
    elif unit == "m":
        result.unit         = "mm"
        result.scale_factor = PT_TO_MM * 1000.0
    elif unit in ("inch", "in"):
        result.unit         = "inch"
        result.scale_factor = PT_TO_INCH
    else:
        result.unit         = "mm"
        result.scale_factor = PT_TO_MM
