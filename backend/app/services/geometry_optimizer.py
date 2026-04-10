"""
Geometry Optimizer

Warstwy detekcji:
  1. 4 krzywe Béziera → CIRCLE (kappa test)
  2. Pojedyncza krzywa Béziera → ARC (circumcircle fit)
  3. Linie → dwuprzebiegowy join (tight + loose tolerance)
  4. Zamknięta polilinia ≥6 pkt → CIRCLE (fallback)
  5. Frame filter

Wynik:
  { "type": "circle",   "center": (x,y), "radius": r,    "is_frame": False }
  { "type": "arc",      "center": (x,y), "radius": r,
                         "p_start": (x,y), "p_end": (x,y), "p_mid": (x,y) }
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
    ax, ay = p1
    bx, by = p2
    cx_, cy_ = p3
    D = 2.0 * (ax * (by - cy_) + bx * (cy_ - ay) + cx_ * (ay - by))
    if abs(D) < 1e-10:
        return False, 0.0, 0.0, 0.0
    ux = ((ax**2+ay**2)*(by-cy_) + (bx**2+by**2)*(cy_-ay) + (cx_**2+cy_**2)*(ay-by)) / D
    uy = ((ax**2+ay**2)*(cx_-bx) + (bx**2+by**2)*(ax-cx_) + (cx_**2+cy_**2)*(bx-ax)) / D
    return True, ux, uy, math.hypot(ax-ux, ay-uy)


# ---------------------------------------------------------------------------
# Bézier → CIRCLE  (Warstwa 1)
# ---------------------------------------------------------------------------

def _bezier_is_quarter_arc(p0, p1, p2, p3) -> tuple[bool, float, float, float]:
    chord = _dist(p0, p3)
    if chord < 1e-6:
        return False, 0.0, 0.0, 0.0
    kappa = settings.CIRCLE_KAPPA
    tol   = settings.CIRCLE_KAPPA_TOLERANCE
    r_c   = chord / math.sqrt(2)
    exp   = kappa * r_c
    if abs(_dist(p0,p1) - exp) / max(exp,1e-6) > tol:
        return False, 0.0, 0.0, 0.0
    if abs(_dist(p2,p3) - exp) / max(exp,1e-6) > tol:
        return False, 0.0, 0.0, 0.0
    mx = (p0[0]+p3[0])/2; my = (p0[1]+p3[1])/2
    dx = p3[0]-p0[0];     dy = p3[1]-p0[1]
    pl = math.hypot(dx, dy)
    if pl < 1e-9:
        return False, 0.0, 0.0, 0.0
    px = -dy/pl; py = dx/pl
    h  = math.sqrt(max(r_c**2 - (chord/2)**2, 0))
    for sign in (1, -1):
        cx = mx + sign*h*px
        cy = my + sign*h*py
        if abs(_dist((cx,cy), p0) - r_c) / max(r_c,1e-6) < tol*2:
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
        centres.append((cx, cy)); radii.append(r)
    avg_cx = sum(c[0] for c in centres)/4
    avg_cy = sum(c[1] for c in centres)/4
    avg_r  = sum(radii)/4
    kt = settings.CIRCLE_KAPPA_TOLERANCE * 4
    for cx, cy in centres:
        if _dist((cx,cy),(avg_cx,avg_cy)) > avg_r*kt:
            return False, 0.0, 0.0, 0.0
    for r in radii:
        if abs(r-avg_r)/max(avg_r,1e-6) > kt:
            return False, 0.0, 0.0, 0.0
    if avg_r < settings.MIN_CIRCLE_RADIUS_PT:
        return False, 0.0, 0.0, 0.0
    if _dist(curves[0]["points"][0], curves[3]["points"][3]) > avg_r*0.05:
        return False, 0.0, 0.0, 0.0
    return True, avg_cx, avg_cy, avg_r


# ---------------------------------------------------------------------------
# Bézier → ARC  (Warstwa 2)
# ---------------------------------------------------------------------------

def _bezier_to_arc(p0, p1, p2, p3, tol_pt: float = 2.0):
    def _bpt(t):
        mt = 1.0-t
        return (mt**3*p0[0]+3*mt**2*t*p1[0]+3*mt*t**2*p2[0]+t**3*p3[0],
                mt**3*p0[1]+3*mt**2*t*p1[1]+3*mt*t**2*p2[1]+t**3*p3[1])
    if _dist(p0, p3) < 1e-6:
        return False, 0.0, 0.0, 0.0, None
    p_mid = _bpt(0.5)
    ok, cx, cy, r = _circumcircle(p0, p_mid, p3)
    if not ok or r < settings.MIN_CIRCLE_RADIUS_PT:
        return False, 0.0, 0.0, 0.0, None
    rel_tol = max(tol_pt, r*0.03)
    for t in (0.15, 0.3, 0.5, 0.7, 0.85):
        if abs(_dist((cx,cy), _bpt(t)) - r) > rel_tol:
            return False, 0.0, 0.0, 0.0, None
    return True, cx, cy, r, p_mid


# ---------------------------------------------------------------------------
# Polyline → CIRCLE  (Warstwa 3 — fallback dla pełnych okręgów)
# ---------------------------------------------------------------------------

def _fit_circle_from_polyline(points, radius_cv_tol=0.03, max_angular_gap=4.0):
    pts = list(points)
    if len(pts) > 1 and _dist(pts[0], pts[-1]) < 1.0:
        pts = pts[:-1]
    n = len(pts)
    if n < 6:
        return False, 0.0, 0.0, 0.0
    cx = sum(p[0] for p in pts)/n
    cy = sum(p[1] for p in pts)/n
    dists = [_dist((cx,cy),p) for p in pts]
    mean_r = sum(dists)/n
    if mean_r < settings.MIN_CIRCLE_RADIUS_PT:
        return False, 0.0, 0.0, 0.0
    cv = math.sqrt(sum((d-mean_r)**2 for d in dists)/n) / mean_r
    if cv > radius_cv_tol:
        return False, 0.0, 0.0, 0.0
    angles = sorted(math.atan2(p[1]-cy, p[0]-cx) for p in pts)
    gaps = [angles[i+1]-angles[i] for i in range(len(angles)-1)]
    gaps.append(angles[0]+2*math.pi-angles[-1])
    if max(gaps) > (2*math.pi/n)*max_angular_gap:
        return False, 0.0, 0.0, 0.0
    return True, cx, cy, mean_r


# ---------------------------------------------------------------------------
# Frame detection
# ---------------------------------------------------------------------------

def _is_frame(pts: list[tuple], page_width: float, page_height: float) -> bool:
    if len(pts) < 4:
        return False
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    ratio = settings.FRAME_BBOX_RATIO
    return (max(xs)-min(xs) >= page_width*ratio and
            max(ys)-min(ys) >= page_height*ratio)


# ---------------------------------------------------------------------------
# Path joining — dwuprzebiegowy (tight + loose)
# ---------------------------------------------------------------------------

def _join_pass(chains: list[list[tuple]], tol: float) -> list[list[tuple]]:
    stable = False
    while not stable:
        stable = True
        new_chains: list[list[tuple]] = []
        used = [False]*len(chains)
        for i in range(len(chains)):
            if used[i]:
                continue
            chain = list(chains[i])
            for j in range(len(chains)):
                if i == j or used[j]:
                    continue
                other = chains[j]
                if _dist(chain[-1], other[0]) < tol:
                    chain = chain + other[1:]; used[j]=True; stable=False
                elif _dist(other[-1], chain[0]) < tol:
                    chain = other + chain[1:]; used[j]=True; stable=False
                elif _dist(chain[-1], other[-1]) < tol:
                    chain = chain + list(reversed(other))[1:]; used[j]=True; stable=False
                elif _dist(chain[0], other[0]) < tol:
                    chain = list(reversed(other)) + chain[1:]; used[j]=True; stable=False
            new_chains.append(chain)
        chains = new_chains
    return chains


def _join_lines(lines: list[dict], tol_tight: float, tol_loose: float) -> list[dict]:
    """
    Łączy segmenty w ciągłe łańcuchy.
    Przebieg 1 (tight ≈0.5pt): łączy dokładnie — ta sama ścieżka PDF.
    Przebieg 2 (loose ≈5pt): łączy bliskie końce między różnymi ścieżkami.
    """
    if not lines:
        return []
    chains = [list(s["points"]) for s in lines if len(s.get("points",[])) >= 2]
    chains = _join_pass(chains, tol_tight)
    chains = _join_pass(chains, tol_loose)
    result = []
    for chain in chains:
        if len(chain) < 2:
            continue
        closed = _dist(chain[0], chain[-1]) < tol_loose*2
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
    p0,p1,p2,p3 = [seg["points"][i] for i in range(4)]
    pts = []
    for i in range(steps+1):
        t=i/steps; mt=1-t
        pts.append((mt**3*p0[0]+3*mt**2*t*p1[0]+3*mt*t**2*p2[0]+t**3*p3[0],
                    mt**3*p0[1]+3*mt**2*t*p1[1]+3*mt*t**2*p2[1]+t**3*p3[1]))
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
    bezier_circles: list[dict] = []
    bezier_arcs:    list[dict] = []
    pending:        list[dict] = []
    curves_buf:     list[dict] = []

    def flush_bezier():
        nonlocal curves_buf
        buf = curves_buf[:]
        curves_buf = []
        i = 0
        while i < len(buf):
            if i+4 <= len(buf):
                ok, cx, cy, r = _curves_form_circle(buf[i:i+4])
                if ok:
                    bezier_circles.append({"type":"circle","center":(cx,cy),"radius":r,"is_frame":False})
                    i += 4; continue
            seg = buf[i]; pts = seg["points"]
            ok, cx, cy, r, p_mid = _bezier_to_arc(pts[0],pts[1],pts[2],pts[3])
            if ok:
                bezier_arcs.append({"type":"arc","center":(cx,cy),"radius":r,
                                    "p_start":pts[0],"p_end":pts[3],"p_mid":p_mid,"is_frame":False})
            else:
                pending.append({"type":"chain","points":_tessellate_bezier(buf[i])})
            i += 1

    for seg in raw_segments:
        kind = seg["type"]
        if kind == "curve":
            curves_buf.append(seg)
        elif kind == "line":
            flush_bezier(); pending.append(seg)
        elif kind in ("rect","quad"):
            flush_bezier()
            pts = seg["points"]
            pending.append({**seg, "_is_frame": _is_frame(pts,page_width,page_height)})
        elif kind in ("chain","line_chain"):
            flush_bezier(); pending.append(seg)
    flush_bezier()

    flat = [{"points":list(s.get("points",[])),"_is_frame":s.get("_is_frame",False)}
            for s in pending if len(s.get("points",[]))>=2]

    # Dwuprzebiegowe łączenie: tight (w obrębie ścieżki) + loose (między ścieżkami)
    joined = _join_lines(flat, tol_tight=join_tolerance_pt, tol_loose=join_tolerance_pt*5)

    result: list[dict] = list(bezier_circles)
    result.extend(bezier_arcs)

    for obj in joined:
        pts    = obj["points"]
        closed = obj["closed"]

        if _is_frame(pts,page_width,page_height) or obj.get("_is_frame",False):
            result.append({"type":"polyline","points":pts,"closed":True,"is_frame":True})
            continue

        if closed and len(pts) >= 6:
            ok, cx, cy, r = _fit_circle_from_polyline(pts)
            if ok:
                result.append({"type":"circle","center":(cx,cy),"radius":r,"is_frame":False})
                continue

        result.append({"type":"polyline","points":pts,"closed":closed,"is_frame":False})

    return result
