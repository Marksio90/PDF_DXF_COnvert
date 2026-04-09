"""
Geometry Optimizer — dwie warstwy detekcji okręgów + łączenie ścieżek.

Warstwa 1 (Bézier):
  Sprawdza czy 4 kolejne krzywe Béziera (κ ≈ 0.5523) tworzą pełny okrąg.
  Działa gdy PDF koduje okręgi przez kubiczne aproksymacje.

Warstwa 2 (polyline → circle fit):
  Po złączeniu wszystkich segmentów, każda *zamknięta* polilinia o ≥6 pkt
  jest testowana pod kątem okrągłości metodą wariancji promieni od centroidu.
  Wykrywa okręgi zakodowane jako wieloboki (linie proste) lub gdy warstwa 1
  zawiodła z powodu tolerancji / kolejności segmentów.

Wynik:
  { "type": "circle",   "center": (x,y), "radius": r,       "is_frame": False }
  { "type": "polyline", "points": [...],  "closed": bool,    "is_frame": bool  }
"""
from __future__ import annotations
import math
from app.core.config import settings


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _dist(a: tuple, b: tuple) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------------------
# Bézier circle detection (Warstwa 1)
# ---------------------------------------------------------------------------

def _bezier_is_arc(p0, p1, p2, p3) -> tuple[bool, float, float, float]:
    """
    Sprawdza czy pojedyncza kubiczna krzywa Béziera aproksymuje łuk 90°.
    Używa właściwości kappa = 0.5523 dla optymalnej aproksymacji okręgu.
    Zwraca (True, cx, cy, r) lub (False, 0, 0, 0).
    """
    chord = _dist(p0, p3)
    if chord < 1e-6:
        return False, 0.0, 0.0, 0.0

    kappa = settings.CIRCLE_KAPPA
    tol   = settings.CIRCLE_KAPPA_TOLERANCE

    d01 = _dist(p0, p1)
    d23 = _dist(p2, p3)

    r_candidate   = chord / math.sqrt(2)
    expected_ctrl = kappa * r_candidate

    if abs(d01 - expected_ctrl) / max(expected_ctrl, 1e-6) > tol:
        return False, 0.0, 0.0, 0.0
    if abs(d23 - expected_ctrl) / max(expected_ctrl, 1e-6) > tol:
        return False, 0.0, 0.0, 0.0

    mx  = (p0[0] + p3[0]) / 2
    my  = (p0[1] + p3[1]) / 2
    dx  = p3[0] - p0[0]
    dy  = p3[1] - p0[1]
    pl  = math.hypot(dx, dy)
    if pl < 1e-9:
        return False, 0.0, 0.0, 0.0
    px = -dy / pl
    py =  dx / pl
    h  = math.sqrt(max(r_candidate**2 - (chord / 2) ** 2, 0))

    for sign in (1, -1):
        cx = mx + sign * h * px
        cy = my + sign * h * py
        if abs(_dist((cx, cy), p0) - r_candidate) / max(r_candidate, 1e-6) < tol * 2:
            return True, cx, cy, r_candidate

    return False, 0.0, 0.0, 0.0


def _curves_form_circle(curves: list[dict]) -> tuple[bool, float, float, float]:
    """
    Sprawdza czy 4 kolejne segmenty Béziera tworzą zamknięty okrąg.
    """
    if len(curves) != 4:
        return False, 0.0, 0.0, 0.0

    centres, radii = [], []
    for seg in curves:
        pts = seg["points"]
        ok, cx, cy, r = _bezier_is_arc(pts[0], pts[1], pts[2], pts[3])
        if not ok:
            return False, 0.0, 0.0, 0.0
        centres.append((cx, cy))
        radii.append(r)

    avg_cx = sum(c[0] for c in centres) / 4
    avg_cy = sum(c[1] for c in centres) / 4
    avg_r  = sum(radii) / 4

    kappa_tol = settings.CIRCLE_KAPPA_TOLERANCE * 4
    for cx, cy in centres:
        if _dist((cx, cy), (avg_cx, avg_cy)) > avg_r * kappa_tol:
            return False, 0.0, 0.0, 0.0
    for r in radii:
        if abs(r - avg_r) / max(avg_r, 1e-6) > kappa_tol:
            return False, 0.0, 0.0, 0.0

    if avg_r < settings.MIN_CIRCLE_RADIUS_PT:
        return False, 0.0, 0.0, 0.0

    # Weryfikuj zamknięcie pętli
    if _dist(curves[0]["points"][0], curves[3]["points"][3]) > avg_r * 0.05:
        return False, 0.0, 0.0, 0.0

    return True, avg_cx, avg_cy, avg_r


# ---------------------------------------------------------------------------
# Polyline → circle fit (Warstwa 2)
# ---------------------------------------------------------------------------

def _fit_circle_from_polyline(
    points: list[tuple],
    radius_cv_tol: float = 0.03,   # max coefficient of variation promienia
    max_angular_gap: float = 4.0,   # max stosunek przerwy kątowej do oczekiwanej
) -> tuple[bool, float, float, float]:
    """
    Testuje czy zamknięta polilinia aproksymuje okrąg.

    Metoda:
      1. Oblicz centroid punktów.
      2. Oblicz odległości (promienie) do centroidu.
      3. Sprawdź czy wariancja promieni / średni promień < radius_cv_tol.
      4. Sprawdź czy kąty są rozłożone równomiernie (pełny okrąg, nie łuk).

    Zwraca (True, cx, cy, radius) lub (False, 0, 0, 0).
    """
    pts = list(points)
    # Usuń zdublowany punkt zamknięcia (ostatni ≈ pierwszy)
    if len(pts) > 1 and _dist(pts[0], pts[-1]) < 1.0:
        pts = pts[:-1]

    n = len(pts)
    if n < 6:
        return False, 0.0, 0.0, 0.0

    # Centroid
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n

    # Odległości od centroidu
    dists = [_dist((cx, cy), p) for p in pts]
    mean_r = sum(dists) / n

    if mean_r < settings.MIN_CIRCLE_RADIUS_PT:
        return False, 0.0, 0.0, 0.0

    # Współczynnik zmienności promienia (relative std dev)
    variance = sum((d - mean_r) ** 2 for d in dists) / n
    cv = math.sqrt(variance) / mean_r
    if cv > radius_cv_tol:
        return False, 0.0, 0.0, 0.0

    # Sprawdź rozłożenie kątowe → pełny okrąg (nie łuk)
    angles = sorted(math.atan2(p[1] - cy, p[0] - cx) for p in pts)
    # Przerwy między kolejnymi kątami + zawijanie
    gaps = [angles[i + 1] - angles[i] for i in range(len(angles) - 1)]
    gaps.append(angles[0] + 2 * math.pi - angles[-1])
    expected_gap = 2 * math.pi / n
    if max(gaps) > expected_gap * max_angular_gap:
        # Duża przerwa kątowa → to łuk, nie pełny okrąg
        return False, 0.0, 0.0, 0.0

    return True, cx, cy, mean_r


# ---------------------------------------------------------------------------
# Frame detection
# ---------------------------------------------------------------------------

def _is_frame(pts: list[tuple], page_width: float, page_height: float) -> bool:
    if len(pts) < 4:
        return False
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ratio = settings.FRAME_BBOX_RATIO
    return (
        max(xs) - min(xs) >= page_width  * ratio and
        max(ys) - min(ys) >= page_height * ratio
    )


# ---------------------------------------------------------------------------
# Path joining
# ---------------------------------------------------------------------------

def _join_lines(lines: list[dict], tol: float) -> list[dict]:
    """
    Łączy sąsiadujące segmenty w ciągłe łańcuchy (LWPOLYLINE).
    Algorytm zachłanny end-to-end z wielokrotnym przebiegiem aż do stabilizacji.
    """
    if not lines:
        return []

    chains: list[list[tuple]] = [list(s["points"]) for s in lines if len(s["points"]) >= 2]

    stable = False
    while not stable:
        stable = True
        new_chains: list[list[tuple]] = []
        used = [False] * len(chains)
        for i in range(len(chains)):
            if used[i]:
                continue
            chain = list(chains[i])
            for j in range(len(chains)):
                if i == j or used[j]:
                    continue
                other = chains[j]
                if _dist(chain[-1], other[0]) < tol:
                    chain = chain + other[1:]
                    used[j] = True
                    stable = False
                elif _dist(other[-1], chain[0]) < tol:
                    chain = other + chain[1:]
                    used[j] = True
                    stable = False
                elif _dist(chain[-1], other[-1]) < tol:
                    chain = chain + list(reversed(other))[1:]
                    used[j] = True
                    stable = False
                elif _dist(chain[0], other[0]) < tol:
                    chain = list(reversed(other)) + chain[1:]
                    used[j] = True
                    stable = False
            new_chains.append(chain)
        chains = new_chains

    result = []
    for chain in chains:
        if len(chain) < 2:
            continue
        closed = _dist(chain[0], chain[-1]) < tol * 2
        result.append({
            "type": "polyline",
            "points": chain,
            "closed": closed,
            "is_frame": False,
        })
    return result


# ---------------------------------------------------------------------------
# Bézier tessellation fallback
# ---------------------------------------------------------------------------

def _tessellate_bezier(seg: dict, steps: int = 12) -> list[tuple]:
    """Przelicza krzywą Béziera na listę punktów (fallback gdy nie wykryto okręgu)."""
    p0, p1, p2, p3 = [seg["points"][i] for i in range(4)]
    pts = []
    for i in range(steps + 1):
        t  = i / steps
        mt = 1 - t
        x = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
        y = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
        pts.append((x, y))
    return pts


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def optimize_geometry(
    raw_segments: list[dict],
    page_width: float,
    page_height: float,
    join_tolerance_pt: float = 0.5,
) -> list[dict]:
    """
    Główny pipeline optymalizacji geometrii.

    Etap 1 – Bézier pass:
        Próbuje wykryć okręgi z grup 4 kolejnych krzywych Béziera.
        Niezakwalifikowane krzywe tesselluje do odcinków.

    Etap 2 – Line joining:
        Łączy wszystkie sąsiadujące segmenty w LWPOLYLINE.

    Etap 3 – Circle fit (kluczowy):
        Każda zamknięta polilinia ≥6 punktów przechodzi test okrągłości.
        Okręgi zastępowane natywnymi obiektami CIRCLE.

    Etap 4 – Frame filter:
        Prostokąty o BBox > FRAME_BBOX_RATIO strony → warstwa FRAME.
    """
    bezier_circles: list[dict] = []   # wykryte przez Bézier pass
    pending: list[dict]         = []  # segmenty do złączenia

    curves_buf: list[dict] = []

    # ---- Etap 1: Bézier pass ------------------------------------------------

    def flush_bezier():
        nonlocal curves_buf
        buf = curves_buf[:]
        curves_buf = []
        i = 0
        while i < len(buf):
            # Spróbuj wykryć okrąg z kolejnych 4 krzywych
            if i + 4 <= len(buf):
                ok, cx, cy, r = _curves_form_circle(buf[i:i + 4])
                if ok:
                    bezier_circles.append({
                        "type": "circle",
                        "center": (cx, cy),
                        "radius": r,
                        "is_frame": False,
                    })
                    i += 4
                    continue
            # Fallback: tessellacja
            pending.append({
                "type": "chain",
                "points": _tessellate_bezier(buf[i]),
            })
            i += 1

    for seg in raw_segments:
        kind = seg["type"]

        if kind == "curve":
            curves_buf.append(seg)

        elif kind == "line":
            flush_bezier()
            pending.append(seg)

        elif kind in ("rect", "quad"):
            flush_bezier()
            pts = seg["points"]
            if _is_frame(pts, page_width, page_height):
                # Ramka rysunkowa — traktuj od razu, nie łącz
                pending.append({**seg, "_is_frame": True})
            else:
                pending.append(seg)

        elif kind in ("chain", "line_chain"):
            flush_bezier()
            pending.append(seg)

    flush_bezier()

    # ---- Etap 2: Łączenie segmentów -----------------------------------------

    flat: list[dict] = []
    for seg in pending:
        pts = seg.get("points", [])
        if len(pts) < 2:
            continue
        flat.append({
            "points": list(pts),
            "_is_frame": seg.get("_is_frame", False),
        })

    joined = _join_lines(flat, tol=join_tolerance_pt)

    # ---- Etap 3 + 4: Circle fit + Frame filter --------------------------------

    result: list[dict] = list(bezier_circles)  # zacznij od Bézier circles

    for obj in joined:
        pts = obj["points"]
        closed = obj["closed"]
        is_frame_seg = obj.get("_is_frame", False)

        # Frame filter
        if _is_frame(pts, page_width, page_height) or is_frame_seg:
            result.append({
                "type": "polyline",
                "points": pts,
                "closed": True,
                "is_frame": True,
            })
            continue

        # Circle fit (Warstwa 2) — tylko dla zamkniętych polilinii
        if closed and len(pts) >= 6:
            ok, cx, cy, r = _fit_circle_from_polyline(pts)
            if ok:
                result.append({
                    "type": "circle",
                    "center": (cx, cy),
                    "radius": r,
                    "is_frame": False,
                })
                continue

        # Zwykła polilinia
        result.append({
            "type": "polyline",
            "points": pts,
            "closed": closed,
            "is_frame": False,
        })

    return result
