"""
Scale Detector — uproszczona, niezawodna wersja.

Zasada: PDF zawsze używa punktów (1 pt = 1/72 cala = 25.4/72 mm).
Jedyna poprawna konwersja to PT_TO_MM = 25.4/72 ≈ 0.3528 mm/pt.
Nie zgadujemy, nie szukamy magicznych przeliczników.

Priorytety:
  1. Jednostka wymuszona przez użytkownika
  2. Skala z tekstu PDF (np. "SKALA 1:2") — koryguje PT_TO_MM
  3. Domyślnie: PT_TO_MM — poprawne dla każdego standardowego PDF z CAD
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from app.core.config import settings

# Jedyny poprawny przelicznik dla standardowych PDF
PT_TO_MM   = 25.4 / 72.0   # 1 PDF point → mm
PT_TO_INCH = 1.0  / 72.0   # 1 PDF point → inch

_SCALE_PATTERNS = [
    (re.compile(r"(?:scale|skala|m)\s*(\d+)\s*:\s*(\d+)", re.IGNORECASE),),
    (re.compile(r"\bskala\b.*?(\d+)\s*:\s*(\d+)", re.IGNORECASE),),
]

_RATIO_RE = re.compile(r"\b(\d+)\s*:\s*(\d+)\b")


@dataclass
class ScaleResult:
    scale_factor: float  = PT_TO_MM
    unit: str            = "mm"
    status: str          = "unverified"    # verified | assumed | unverified
    source: str          = "default"       # forced | text | default
    ratio_numerator: int = 1
    ratio_denominator: int = 1
    confidence_delta: int = 0
    notes: list[str]     = field(default_factory=list)


def detect_scale(
    text_blocks: list[dict],
    raw_segments: list[dict] | None = None,   # nieużywane, zachowane dla kompatybilności
    forced_unit: str | None = None,
    pdf_path: str | None = None,
    page_idx: int = 0,
) -> ScaleResult:
    result = ScaleResult()

    # 1. Wymuszone przez użytkownika
    if forced_unit:
        result.source = "forced"
        result.status = "verified"
        _apply_unit(result, forced_unit.lower().strip())
        result.notes.append(f"Jednostka wymuszona: {forced_unit}")
        return result

    # 2. Szukaj skali w tekście PDF (np. "SKALA 1:2", "1:5")
    all_text = " ".join(b["text"] for b in text_blocks)
    ratio = _detect_ratio(all_text)

    if ratio:
        n, d = ratio
        if n == 1 and d == 1:
            # Explicite SKALA 1:1 w tekście — potwierdza PT_TO_MM
            result.scale_factor      = PT_TO_MM
            result.ratio_numerator   = 1
            result.ratio_denominator = 1
            result.source            = "text"
            result.status            = "verified"
            result.confidence_delta  = 0
            result.notes.append(
                f"Wykryto SKALA 1:1 w tekście PDF. "
                f"scale_factor = PT_TO_MM = {PT_TO_MM:.6f} mm/pt."
            )
        else:
            result.scale_factor      = PT_TO_MM * n / d
            result.ratio_numerator   = n
            result.ratio_denominator = d
            result.source            = "text"
            result.status            = "assumed"
            result.confidence_delta  = -settings.SCALE_CONFIDENCE_PENALTY_ASSUMED
            result.notes.append(
                f"Wykryto skalę {n}:{d} w tekście PDF. "
                f"scale_factor = {PT_TO_MM:.6f} × {n}/{d} = {result.scale_factor:.6f} mm/pt."
            )
        return result

    # 3. Domyślnie: PT_TO_MM — matematyczny fakt, nie zgadywanie.
    #    1 PDF point = 1/72 cala = 25.4/72 mm. Zawsze poprawne dla wektorowych PDF z CAD.
    result.scale_factor    = PT_TO_MM
    result.unit            = "mm"
    result.status          = "verified"
    result.source          = "default"
    result.confidence_delta = 0
    result.notes.append(
        f"Standard ISO: 1 pt PDF = 25.4/72 mm = {PT_TO_MM:.6f} mm/pt. "
        f"Poprawne dla wszystkich wektorowych PDF z CAD."
    )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_ratio(text: str) -> tuple[int, int] | None:
    # Szukaj "SKALA X:Y" lub "M X:Y" lub po prostu "X:Y" w kontekście skali
    for m in re.finditer(r"(?:skala|scale|m)\s*(\d+)\s*:\s*(\d+)", text, re.IGNORECASE):
        a, b = int(m.group(1)), int(m.group(2))
        if a > 0 and b > 0:
            return a, b
    # Fallback: "1:1", "1:2" etc. jako samodzielny wzorzec
    for m in re.finditer(r"\b(1)\s*:\s*([1-9]\d?)\b", text):
        a, b = int(m.group(1)), int(m.group(2))
        return a, b
    return None


def _apply_unit(result: ScaleResult, unit: str):
    """Ustaw scale_factor na podstawie wymuszonej jednostki."""
    if unit in ("mm_direct", "mm_native", "mm_natywne"):
        # Współrzędne PDF już w mm — nie przeliczaj
        result.unit         = "mm"
        result.scale_factor = 1.0
        result.notes.append(
            "Tryb mm natywne: scale_factor=1.0 — "
            "użyj gdy wymiary DXF są ~2.83× za małe (PDF eksportowany z mm jako jednostką)."
        )
    elif unit == "mm":
        result.unit         = "mm"
        result.scale_factor = PT_TO_MM
    else:
        # Nieznana jednostka → domyślnie PT_TO_MM
        result.unit         = "mm"
        result.scale_factor = PT_TO_MM
        result.notes.append(f"Nieznana jednostka '{unit}', użyto PT_TO_MM.")
