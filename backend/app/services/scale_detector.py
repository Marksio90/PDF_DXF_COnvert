"""
Scale Detector

Cel: zawsze zwrócić DXF w skali 1:1 (prawdziwe wymiary wyrobu).

Priorytety:
  1. Jednostka wymuszona przez użytkownika
  2. Skala z tekstu PDF (np. "SKALA 1:2")
     → scale_factor = PT_TO_MM × (d / n)
     → dla 1:2: PT_TO_MM × 2  (linie 2× krótsze na papierze → 2× wydłuż w DXF)
  3. Korelacja wymiarów: porównaj liczby-wymiary z tekstu z długościami linii
  4. Domyślnie: PT_TO_MM (matematyczny fakt, zawsze poprawne dla std. PDF)

Konwersja:
  1 PDF point = 1/72 cala = 25.4/72 mm ≈ 0.352778 mm
  PT_TO_MM × (d/n) = mnożnik przywracający skalę 1:1
"""
from __future__ import annotations
import re
import math
from dataclasses import dataclass, field
from app.core.config import settings

PT_TO_MM = 25.4 / 72.0   # jedyna poprawna konwersja pt → mm


@dataclass
class ScaleResult:
    scale_factor: float  = PT_TO_MM
    unit: str            = "mm"
    status: str          = "verified"   # verified | assumed
    source: str          = "default"    # forced | text | dimension | default
    ratio_numerator: int = 1
    ratio_denominator: int = 1
    confidence_delta: int = 0
    notes: list[str]     = field(default_factory=list)


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

    # ── 1. Wymuszone przez użytkownika ────────────────────────────────────
    if forced_unit:
        result.source = "forced"
        result.status = "verified"
        _apply_unit(result, forced_unit.lower().strip())
        result.notes.append(f"Jednostka wymuszona: {forced_unit}")
        return result

    # ── 2. Skala z tekstu PDF (np. "SKALA 1:2", "1:5") ───────────────────
    all_text = " ".join(b["text"] for b in text_blocks)
    ratio = _detect_ratio_from_text(all_text)

    if ratio:
        n, d = ratio
        # scale_factor = PT_TO_MM × d/n
        # Przykład SKALA 1:2: n=1, d=2 → mnożnik=2 → linie 2× dłuższe → 1:1 ✓
        # Przykład SKALA 1:1: n=1, d=1 → mnożnik=1 → bez zmiany ✓
        multiplier = d / n
        result.scale_factor      = PT_TO_MM * multiplier
        result.ratio_numerator   = n
        result.ratio_denominator = d
        result.source            = "text"
        result.status            = "verified"
        result.confidence_delta  = 0
        result.notes.append(
            f"Wykryto SKALA {n}:{d} w tekście PDF. "
            f"Mnożnik skali: {multiplier:.4f}× "
            f"(PT_TO_MM × {d}/{n} = {result.scale_factor:.6f} mm/pt). "
            f"DXF będzie w skali 1:1."
        )
        return result

    # ── 3. Korelacja wymiarów (gdy brak tekstu ze skalą) ─────────────────
    if raw_segments:
        dim_result = _detect_from_dimensions(text_blocks, raw_segments)
        if dim_result is not None:
            multiplier, matches = dim_result
            result.scale_factor    = PT_TO_MM * multiplier
            result.source          = "dimension"
            result.status          = "assumed"
            result.confidence_delta = -settings.SCALE_CONFIDENCE_PENALTY_ASSUMED
            result.notes.append(
                f"Brak skali w tekście. Korelacja wymiarów ({matches} par): "
                f"mnożnik ≈ {multiplier:.4f}× "
                f"(scale_factor = {result.scale_factor:.6f} mm/pt)."
            )
            return result

    # ── 4. Domyślnie: PT_TO_MM ────────────────────────────────────────────
    # 1 PDF point = 25.4/72 mm to fakt matematyczny, nie zgadywanie.
    # Dla wektorowych PDF z CAD eksportowanych bez specjalnej skali → zawsze poprawne.
    result.scale_factor    = PT_TO_MM
    result.unit            = "mm"
    result.status          = "verified"
    result.source          = "default"
    result.confidence_delta = 0
    result.notes.append(
        f"Standard ISO: 1 pt PDF = 25.4/72 mm = {PT_TO_MM:.6f} mm/pt. "
        f"Poprawne dla wszystkich wektorowych PDF z CAD bez specjalnej skali."
    )
    return result


# ---------------------------------------------------------------------------
# Pomocnicy
# ---------------------------------------------------------------------------

def _detect_ratio_from_text(text: str) -> tuple[int, int] | None:
    """
    Szuka wzorców: "SKALA 1:2", "SCALE 1:5", "M 1:10", samodzielne "1:2" itp.
    Zwraca (n, d) lub None.
    """
    # Priorytet: słowo kluczowe + ratio
    for m in re.finditer(
        r"(?:skala|scale|m)\s*(\d+)\s*:\s*(\d+)", text, re.IGNORECASE
    ):
        n, d = int(m.group(1)), int(m.group(2))
        if n > 0 and d > 0:
            return n, d

    # Fallback: samodzielny wzorzec "1:X" (X > 1 → pomniejszenie)
    for m in re.finditer(r"\b1\s*:\s*([2-9]\d*)\b", text):
        d = int(m.group(1))
        return 1, d

    return None


def _detect_from_dimensions(
    text_blocks: list[dict],
    raw_segments: list[dict],
    min_line_pt: float = 15.0,     # minimalna długość linii (pt)
    proximity_pt: float = 60.0,    # max odległość tekstu od linii (pt)
    min_matches: int = 2,          # minimalna liczba zgodnych par
    consistency_tol: float = 0.06, # max odchylenie od mediany (6%)
) -> tuple[float, int] | None:
    """
    Wykrywa mnożnik skali przez porównanie wartości numerycznych z tekstu
    (wymiary opisane na rysunku) z długościami poziomych/pionowych linii.

    Zwraca (multiplier, liczba_par) lub None gdy za mało danych.
    """
    # Zbierz wartości numeryczne z tekstu (prawdopodobne wymiary w mm)
    dim_values: list[tuple[float, float, float]] = []  # (value, mid_x, mid_y)
    for block in text_blocks:
        raw = block["text"]
        cx = (block["x0"] + block["x1"]) / 2
        cy = (block["y0"] + block["y1"]) / 2
        # Tylko "czyste" liczby, bez jednostek ani ułamków dziesiętnych < 1
        for m in re.finditer(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", raw):
            val = float(m.group(1))
            if 3.0 <= val <= 9999.0:   # rozsądny zakres wymiaru w mm
                dim_values.append((val, cx, cy))

    if not dim_values:
        return None

    # Zbierz poziome i pionowe odcinki linii
    ratios: list[float] = []
    for seg in raw_segments:
        if seg["type"] != "line":
            continue
        pts = seg.get("points", [])
        if len(pts) < 2:
            continue
        x0, y0 = pts[0]
        x1, y1 = pts[1]
        dx, dy = abs(x1 - x0), abs(y1 - y0)

        # Tylko czysto poziome lub pionowe
        if dx > 4 * dy:          # pozioma
            length_pt = dx
        elif dy > 4 * dx:        # pionowa
            length_pt = dy
        else:
            continue

        if length_pt < min_line_pt:
            continue

        line_mm = length_pt * PT_TO_MM
        mid_x = (x0 + x1) / 2
        mid_y = (y0 + y1) / 2

        # Porównaj z każdą wartością tekstową w pobliżu
        for val, tx, ty in dim_values:
            dist = math.hypot(tx - mid_x, ty - mid_y)
            if dist > proximity_pt:
                continue
            ratio = val / line_mm   # rzeczywisty / papierowy = mnożnik skali
            # Odfiltruj nierealne wartości
            if 0.8 <= ratio <= 500.0:
                ratios.append(ratio)

    if len(ratios) < min_matches:
        return None

    # Mediana jako estymata mnożnika
    ratios.sort()
    median = ratios[len(ratios) // 2]

    # Wybierz pary zgodne z medianą (± consistency_tol)
    consistent = [r for r in ratios if abs(r - median) / median <= consistency_tol]
    if len(consistent) < min_matches:
        return None

    avg = sum(consistent) / len(consistent)

    # Przybliż do standardowego mnożnika (1, 2, 5, 10, 20, 50, 100 …)
    standard = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500]
    for s in standard:
        if abs(avg - s) / s < 0.08:   # 8% tolerancja
            return float(s), len(consistent)

    return avg, len(consistent)


def _apply_unit(result: ScaleResult, unit: str):
    """Ustaw scale_factor na podstawie wymuszonej jednostki."""
    if unit in ("mm_direct", "mm_native", "mm_natywne"):
        # PDF eksportowany z mm jako jednostką — nie przeliczaj
        result.unit         = "mm"
        result.scale_factor = 1.0
        result.notes.append(
            "Tryb mm natywne: scale_factor=1.0 "
            "(PDF z mm jako jednostką, bez konwersji pt→mm)."
        )
    else:
        # "mm" lub cokolwiek innego → standardowy PT_TO_MM
        result.unit         = "mm"
        result.scale_factor = PT_TO_MM
        if unit not in ("mm", ""):
            result.notes.append(f"Nieznana jednostka '{unit}', użyto PT_TO_MM.")
