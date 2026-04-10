"""
Geometry Optimizer

Warstwy detekcji geometrii:
  1. 4 krzywe Béziera → CIRCLE (kappa test)
  2. Pojedyncza krzywa Béziera → ARC (circumcircle fit)
  3. Linie → join (dwuprzebiegowy: tight + loose tolerance)
  4. Polilinia → podział na odcinki ARC + LWPOLYLINE (kluczowe dla PDF
     które kodują łuki jako wielokąty z 6-12 odcinków)
  5. Zamknięta polilinia → CIRCLE (fallback)
  6. Frame filter

Wynik:
  { "type": "circle",   "center": (x,y), "radius": r,    "is_frame": False }
  { "type": "arc",      "center": (x,y), "radius": r,
                         "p_start": (x,y), "p_end": (x,y), "p_mid": (x,y),
                         "is_frame": False }
  { "type": "polyline", "points": [...],  "closed": bool, "is_frame": bool  }
"""
from __future__ import annotations
import math
from app.core.config import settings


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _dist(a: tuple, b: tuple) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _circumcircle(p1: tuple, p2: tuple, p3: tuple) -> tuple[bool, float, float, float]:
    """Okrąg przechodzący przez 3 punkty. Zwraca (ok, cx, cy, r)."""
    ax, ay = p1
    bx, by = p2
    cx_, cy_ = p3
    D = 2.0 * (ax * (by - cy_) + bx * (cy_ - ay) + cx_ * (ay - by))
    if abs(D) < 1e-10:
        return False, 0.0, 0.0, 0.0
    ux = ((ax**2 + ay**2)*(by - cy_) + (bx**2 + by**2)*(cy_ - ay) + (cx_**2 + cy_**2)*(ay - by)) / D
    uy = ((ax**2 + ay**2)*(cx_ - bx) + (bx**2 + by**2)*(ax - cx_) + (cx_**2 + cy_**2)*(bx - ax)) / D
    r = math.hypot(ax - ux, ay - uy)
    return True, ux, uy, r


# ---------------------------------------------------------------------------
# Bézier → circle  (Warstwa 1)
# ---------------------------------------------------------------------------

def _bezier_is_quarter_arc(p0, p1, p2, p3) -> tuple[bool, float, float, float]:
    chord = _dist(p0, p3)
    if chord < 1e-6:
        return False, 0.0, 0.0, 0.0
    kappa = settings.CIRCLE_KAPPA
    tol   = settings.CIRCLE_KAPPA_TOLERANCE
    d01   = _dist(p0, p1)
    d23   = _dist(p2, p3)
    r_c   = chord / math.sqrt(2)
    exp   = kappa * r_c
    if abs(d01 - exp) / max(exp, 1e-6) > tol:
        return False, 0.0, 0.0, 0.0
    if abs(d23 - exp) / max(exp, 1e-6) > tol:
        return False, 0.0, 0.0, 0.0
    mx = (p0[0] + p3[0]) / 2
    my = (p0[1] + p3[1]) / 2
    dx = p3[0] - p0[0]
    dy = p3[1] - p0[1]
    pl = math.hypot(dx, dy)
    if pl < 1e-9:
        return False, 0.0, 0.0, 0.0
    px = -dy / pl
    py =  dx / pl
    h  = math.sqrt(max(r_c**2 - (chord / 2)**2, 0))
    for sign in (1, -1):
        cx = mx + sign * h * px
        cy = my + sign * h * py
        if abs(_dist((cx, cy), p0) - r_c) / max(r_c, 1e-6) < tol * 2:
            return True, cx, cy, r_c
    return False, 0.0, 0.0, 0.0


def _curves_form_circle(curves: list[dict]) -> tuple[bool, float, float, float]:
    if len(curves) != 4:
        return False, 0.0, 0.0, 0.0
    centres, radii = [], []
    for seg in curves:
        pts = seg["points"]
        ok, cx, cy, r = _bezier_is_quarter_arc(pts[0], pts[1], pts[2], pts[3])
        if not ok:
            return False, 0.0, 0.0, 0.0
        centres.append((cx, cy))
        radii.append(r)
    avg_cx = sum(c[0] for c in centres) / 4
    avg_cy = sum(c[1] for c in centres) / 4
    avg_r  = sum(radii) / 4
    kt = settings.CIRCLE_KAPPA_TOLERANCE * 4
    for cx, cy in centres:
        if _dist((cx, cy), (avg_cx, avg_cy)) > avg_r * kt:
            return False, 0.0, 0.0, 0.0
    for r in radii:
        if abs(r - avg_r) / max(avg_r, 1e-6) > kt:
            return False, 0.0, 0.0, 0.0
    if avg_r < settings.MIN_CIRCLE_RADIUS_PT:
        return False, 0.0, 0.0, 0.0
    if _dist(curves[0]["points"][0], curves[3]["points"][3]) > avg_r * 0.05:
        return False, 0.0, 0.0, 0.0
    return True, avg_cx, avg_cy, avg_r


# ---------------------------------------------------------------------------
# Bézier → arc  (Warstwa 2)
# ---------------------------------------------------------------------------

def _bezier_to_arc(p0, p1, p2, p3, tol_pt: float = 2.0):
    """Dopasowuje pojedynczy Bézier do łuku kołowego."""
    def _bpt(t):
        mt = 1.0 - t
        return (
            mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0],
            mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1],
        )
    if _dist(p0, p3) < 1e-6:
        return False, 0.0, 0.0, 0.0, None
    p_mid = _bpt(0.5)
    ok, cx, cy, r = _circumcircle(p0, p_mid, p3)
    if not ok or r < settings.MIN_CIRCLE_RADIUS_PT:
        return False, 0.0, 0.0, 0.0, None
    rel_tol = max(tol_pt, r * 0.03)
    for t in (0.15, 0.3, 0.5, 0.7, 0.85):
        if abs(_dist((cx, cy), _bpt(t)) - r) > rel_tol:
            return False, 0.0, 0.0, 0.0, None
    return True, cx, cy, r, p_mid


# ---------------------------------------------------------------------------
# Polyline → arc detection  (Warstwa 3 — kluczowa dla PDF z poligonalnymi łukami)
# ---------------------------------------------------------------------------

def _try_fit_arc_to_points(pts: list[tuple]) -> tuple[bool, float, float, float, tuple]:
    """
    Sprawdza czy punkty leżą na łuku kołowym.
    Wymaga monotonicznego kąta (punkty muszą iść w jednym kierunku).
    Zwraca (ok, cx, cy, r, p_mid).
    """
    n = len(pts)
    if n < 3:
        return False, 0.0, 0.0, 0.0, pts[0]

    ok, cx, cy, r = _circumcircle(pts[0], pts[n // 2], pts[-1])
    if not ok or r < settings.MIN_CIRCLE_RADIUS_PT:
        return False, 0.0, 0.0, 0.0, pts[0]

    # Względna tolerancja dopasowania (uwzględnia poligonalne przybliżenia)
    rel_tol = max(2.0, r * 0.04)

    for p in pts:
        if abs(_dist((cx, cy), p) - r) > rel_tol:
            return False, 0.0, 0.0, 0.0, pts[0]

    # Monotoniczny postęp kątowy (punkty idą w jednym kierunku wokół okręgu)
    angles = [math.atan2(p[1] - cy, p[0] - cx) for p in pts]
    diffs = []
    for i in range(len(angles) - 1):
        d = angles[i + 1] - angles[i]
        if d > math.pi:
            d -= 2 * math.pi
        elif d < -math.pi:
            d += 2 * math.pi
        diffs.append(d)

    if not diffs:
        return False, 0.0, 0.0, 0.0, pts[0]

    pos = sum(1 for d in diffs if d > 1e-6)
    neg = sum(1 for d in diffs if d < -1e-6)
    if pos > 0 and neg > 0:
        return False, 0.0, 0.0, 0.0, pts[0]

    p_mid = pts[n // 2]
    return True, cx, cy, r, p_mid


def _extract_arcs_from_polyline(
    points: list[tuple],
    min_arc_pts: int = 4,
) -> list[dict]:
    """
    Dzieli polilinię na odcinki łukowe (ARC) i prostoliniowe (polyline).
    Kluczowe dla PDF gdzie łuki są zakodowane jako serie krótkich odcinków.

    Algorytm zachłanny: dla każdego punktu startowego próbuje znaleźć
    jak najdłuższy pasujący łuk, potem przetwarza resztę.
    """
    n = len(points)
    if n < 2:
        return []

    result: list[dict] = []
    straight_buf: list[tuple] = []
    i = 0

    def _flush_straight():
        if len(straight_buf) >= 2:
            result.append({
                "type": "polyline",
                "points": list(straight_buf),
                "closed": False,
                "is_frame": False,
            })
        straight_buf.clear()

    while i < n:
        # Próba znalezienia łuku zaczynając od punktu i
        found_arc = False

        if i + min_arc_pts <= n:
            # Zachłannie rozszerzaj okno łuku
            best_j = -1
            best_data = None

            j = i + min_arc_pts
            while j <= n:
                ok, cx, cy, r, p_mid = _try_fit_arc_to_points(points[i:j])
                if ok:
                    best_j = j
                    best_data = (cx, cy, r, p_mid)
                    j += 1
                else:
                    break

            if best_j > 0:
                cx, cy, r, p_mid = best_data
                # Zrzuć zgromadzone odcinki proste
                if straight_buf:
                    # Dodaj punkt startowy łuku do bufora prostego
                    straight_buf.append(points[i])
                    _flush_straight()
                    straight_buf.clear()

                result.append({
                    "type": "arc",
                    "center": (cx, cy),
                    "radius": r,
                    "p_start": points[i],
                    "p_end":   points[best_j - 1],
                    "p_mid":   p_mid,
                    "is_frame": False,
                })
                i = best_j - 1  # -1 → punkt końcowy łuku jako start następnego
                found_arc = True

        if not found_arc:
            if not straight_buf or _dist(straight_buf[-1], points[i]) > 1e-9:
                straight_buf.append(points[i])
            i += 1

    # Zrzuć pozostałe odcinki proste
    _flush_straight()

    return result


# ---------------------------------------------------------------------------
# Polyline → circle fit  (Warstwa 4 — fallback dla pełnych okręgów)
# ---------------------------------------------------------------------------

def _fit_circle_from_polyline(points, radius_cv_tol=0.03, max_angular_gap=4.0):
    pts = list(points)
    if len(pts) > 1 and _dist(pts[0], pts[-1]) < 1.0:
        pts = pts[:-1]
    n = len(pts)
    if n < 6:
        return False, 0.0, 0.0, 0.0
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    dists = [_dist((cx, cy), p) for p in pts]
    mean_r = sum(dists) / n
    if mean_r < settings.MIN_CIRCLE_RADIUS_PT:
        return False, 0.0, 0.0, 0.0
    cv = math.sqrt(sum((d - mean_r)**2 for d in dists) / n) / mean_r
    if cv > radius_cv_tol:
        return False, 0.0, 0.0, 0.0
    angles = sorted(math.atan2(p[1] - cy, p[0] - cx) for p in pts)
    gaps = [angles[i + 1] - angles[i] for i in range(len(angles) - 1)]
    gaps.append(angles[0] + 2 * math.pi - angles[-1])
    if max(gaps) > (2 * math.pi / n) * max_angular_gap:
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
# Path joining  (dwuprzebiegowy: tight + loose)
# ---------------------------------------------------------------------------

def _join_pass(chains: list[list[tuple]], tol: float) -> list[list[tuple]]:
    """Jeden przebieg łączenia łańcuchów z tolerancją tol."""
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
    return chains


def _join_lines(lines: list[dict], tol_tight: float, tol_loose: float) -> list[dict]:
    """
    Łączy segmenty w ciągłe łańcuchy.
    Przebieg 1 (tight): łączy dokładnie pasujące końce (ta sama ścieżka PDF).
    Przebieg 2 (loose): łączy bliskie końce między różnymi ścieżkami PDF.
    """
    if not lines:
        return []
    chains = [list(s["points"]) for s in lines if len(s.get("points", [])) >= 2]
    chains = _join_pass(chains, tol_tight)
    chains = _join_pass(chains, tol_loose)
    result = []
    for chain in chains:
        if len(chain) < 2:
            continue
        closed = _dist(chain[0], chain[-1]) < tol_loose * 2
        result.append({
            "type": "polyline",
            "points": chain,
            "closed": closed,
            "is_frame": False,
        })
    return result


# ---------------------------------------------------------------------------
# Bézier tessellation (fallback)
# ---------------------------------------------------------------------------

def _tessellate_bezier(seg: dict, steps: int = 32) -> list[tuple]:
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
    join_tolerance_pt: float = 1.0,
) -> list[dict]:
    """
    Pipeline:
    1. 4 Béziery → CIRCLE
    2. 1 Bézier → ARC
    3. Linie → join (tight=join_tol, loose=join_tol×8)
    4. Polilinia → podział na ARC + LWPOLYLINE (wykrywa poligonalne łuki)
    5. Zamknięta polilinia → CIRCLE
    6. Frame filter
    """
    bezier_circles: list[dict] = []
    bezier_arcs:    list[dict] = []
    pending:        list[dict] = []
    curves_buf:     list[dict] = []

    # ── Etap 1+2: Bézier pass ─────────────────────────────────────────────

    def flush_bezier():
        nonlocal curves_buf
        buf = curves_buf[:]
        curves_buf = []
        i = 0
        while i < len(buf):
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
            seg = buf[i]
            pts = seg["points"]
            ok, cx, cy, r, p_mid = _bezier_to_arc(pts[0], pts[1], pts[2], pts[3])
            if ok:
                bezier_arcs.append({
                    "type": "arc",
                    "center": (cx, cy),
                    "radius": r,
                    "p_start": pts[0],
                    "p_end":   pts[3],
                    "p_mid":   p_mid,
                    "is_frame": False,
                })
            else:
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
                pending.append({**seg, "_is_frame": True})
            else:
                pending.append(seg)
        elif kind in ("chain", "line_chain"):
            flush_bezier()
            pending.append(seg)
    flush_bezier()

    # ── Etap 3: Łączenie segmentów liniowych ──────────────────────────────

    flat = []
    for seg in pending:
        pts = seg.get("points", [])
        if len(pts) >= 2:
            flat.append({
                "points": list(pts),
                "_is_frame": seg.get("_is_frame", False),
            })

    tol_loose = join_tolerance_pt * 8   # między różnymi ścieżkami PDF
    joined = _join_lines(flat, tol_tight=join_tolerance_pt, tol_loose=tol_loose)

    # ── Etap 4+5+6: Arc extraction + Circle fit + Frame filter ────────────

    result: list[dict] = list(bezier_circles)
    result.extend(bezier_arcs)

    for obj in joined:
        pts    = obj["points"]
        closed = obj["closed"]

        # Frame filter
        if _is_frame(pts, page_width, page_height) or obj.get("_is_frame", False):
            result.append({
                "type": "polyline",
                "points": pts,
                "closed": True,
                "is_frame": True,
            })
            continue

        # Circle fit (dla zamkniętych polilinii)
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

        # Arc extraction — wykrywa poligonalne łuki z krótkich odcinków
        if len(pts) >= 4:
            sub_entities = _extract_arcs_from_polyline(pts)
            if any(e["type"] == "arc" for e in sub_entities):
                # Znaleziono łuki — użyj wynikowych encji
                result.extend(sub_entities)
                continue

        # Zwykła polilinia
        result.append({
            "type": "polyline",
            "points": pts,
            "closed": closed,
            "is_frame": False,
        })

    return result
