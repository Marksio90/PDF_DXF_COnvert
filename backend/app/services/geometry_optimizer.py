"""
Geometry Optimizer — transforms raw segments into optimised geometric objects:
  1. Frames  — rectangles covering > FRAME_BBOX_RATIO of the page
  2. Circles — 4 cubic Bézier arcs with κ ≈ 0.5523 → native CIRCLE
  3. Arcs    — 1 or 2 cubic Bézier arcs that form a partial circle
  4. Polylines — connected line segments joined into LWPOLYLINE
"""
from __future__ import annotations
import math
from app.core.config import settings

# ---- helpers ----------------------------------------------------------------

def _dist(a: tuple, b: tuple) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _bezier_is_arc(p0, p1, p2, p3) -> tuple[bool, float, float, float]:
    """
    Check whether a single cubic Bézier approximates a 90° circle arc using
    the κ = 0.5523 magic number.
    Returns (is_arc, cx, cy, radius) if valid, else (False, 0, 0, 0).
    """
    chord = _dist(p0, p3)
    if chord < 1e-6:
        return False, 0.0, 0.0, 0.0

    kappa = settings.CIRCLE_KAPPA
    tol = settings.CIRCLE_KAPPA_TOLERANCE

    # Control-point distances from the anchor they're attached to
    d01 = _dist(p0, p1)
    d23 = _dist(p2, p3)

    # For a perfect 90° arc: radius = chord / sqrt(2), and d01 = d23 = kappa * r
    r_candidate = chord / math.sqrt(2)
    expected_ctrl = kappa * r_candidate

    if abs(d01 - expected_ctrl) / max(expected_ctrl, 1e-6) > tol:
        return False, 0.0, 0.0, 0.0
    if abs(d23 - expected_ctrl) / max(expected_ctrl, 1e-6) > tol:
        return False, 0.0, 0.0, 0.0

    # Estimate centre: perpendicular bisector of the chord, at distance r
    mx = (p0[0] + p3[0]) / 2
    my = (p0[1] + p3[1]) / 2
    dx = p3[0] - p0[0]
    dy = p3[1] - p0[1]
    perp_len = math.hypot(dx, dy)
    if perp_len < 1e-9:
        return False, 0.0, 0.0, 0.0
    px = -dy / perp_len
    py = dx / perp_len
    h = math.sqrt(max(r_candidate**2 - (chord / 2) ** 2, 0))

    # Two candidate centres – pick the one consistent with control points
    for sign in (1, -1):
        cx = mx + sign * h * px
        cy = my + sign * h * py
        r_check = _dist((cx, cy), p0)
        if abs(r_check - r_candidate) / max(r_candidate, 1e-6) < tol * 2:
            return True, cx, cy, r_candidate

    return False, 0.0, 0.0, 0.0


def _curves_form_circle(curves: list[dict]) -> tuple[bool, float, float, float]:
    """
    Check whether 4 consecutive Bézier segments close into a full circle.
    Returns (True, cx, cy, radius) or (False, 0, 0, 0).
    """
    if len(curves) != 4:
        return False, 0.0, 0.0, 0.0

    centres = []
    radii = []
    for seg in curves:
        pts = seg["points"]
        ok, cx, cy, r = _bezier_is_arc(pts[0], pts[1], pts[2], pts[3])
        if not ok:
            return False, 0.0, 0.0, 0.0
        centres.append((cx, cy))
        radii.append(r)

    # All four arcs should share the same centre and radius
    avg_cx = sum(c[0] for c in centres) / 4
    avg_cy = sum(c[1] for c in centres) / 4
    avg_r = sum(radii) / 4

    for cx, cy in centres:
        if _dist((cx, cy), (avg_cx, avg_cy)) > avg_r * settings.CIRCLE_KAPPA_TOLERANCE * 4:
            return False, 0.0, 0.0, 0.0
    for r in radii:
        if abs(r - avg_r) / max(avg_r, 1e-6) > settings.CIRCLE_KAPPA_TOLERANCE * 4:
            return False, 0.0, 0.0, 0.0

    if avg_r < settings.MIN_CIRCLE_RADIUS_PT:
        return False, 0.0, 0.0, 0.0

    # Verify closure: last point of seg[3] ≈ first point of seg[0]
    first_pt = curves[0]["points"][0]
    last_pt = curves[3]["points"][3]
    if _dist(first_pt, last_pt) > avg_r * 0.05:
        return False, 0.0, 0.0, 0.0

    return True, avg_cx, avg_cy, avg_r


def _is_frame(seg: dict, page_width: float, page_height: float) -> bool:
    """True if the segment is a large rectangle that spans most of the page."""
    pts = seg["points"]
    if len(pts) < 4:
        return False
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    ratio = settings.FRAME_BBOX_RATIO
    return w >= page_width * ratio and h >= page_height * ratio


def _join_lines(lines: list[dict], tol: float) -> list[dict]:
    """
    Connect collinear/adjacent lines into LWPOLYLINE chains.
    Uses a simple greedy end-to-end matching algorithm.
    """
    if not lines:
        return []

    # Each chain is a list of points
    chains: list[list[tuple]] = []
    for seg in lines:
        pts = seg["points"]
        if len(pts) < 2:
            continue
        chains.append(list(pts))

    changed = True
    while changed:
        changed = False
        merged: list[list[tuple]] = []
        used = [False] * len(chains)
        for i, chain_a in enumerate(chains):
            if used[i]:
                continue
            for j in range(i + 1, len(chains)):
                if used[j]:
                    continue
                chain_b = chains[j]
                # end of A → start of B
                if _dist(chain_a[-1], chain_b[0]) < tol:
                    chains[i] = chain_a + chain_b[1:]
                    used[j] = True
                    chain_a = chains[i]
                    changed = True
                # end of B → start of A
                elif _dist(chain_b[-1], chain_a[0]) < tol:
                    chains[i] = chain_b + chain_a[1:]
                    used[j] = True
                    chain_a = chains[i]
                    changed = True
                # end of A → end of B (reverse B)
                elif _dist(chain_a[-1], chain_b[-1]) < tol:
                    chains[i] = chain_a + list(reversed(chain_b))[1:]
                    used[j] = True
                    chain_a = chains[i]
                    changed = True
                # start of A → start of B (reverse A)
                elif _dist(chain_a[0], chain_b[0]) < tol:
                    chains[i] = list(reversed(chain_a)) + chain_b[1:]
                    used[j] = True
                    chain_a = chains[i]
                    changed = True
            if not used[i]:
                merged.append(chains[i])
        # Add remaining unused merged chains
        for i, chain in enumerate(chains):
            if not used[i] and chain not in merged:
                merged.append(chain)
        chains = merged

    result = []
    for chain in chains:
        if len(chain) < 2:
            continue
        closed = _dist(chain[0], chain[-1]) < tol
        result.append({
            "type": "polyline",
            "points": chain,
            "closed": closed,
            "is_frame": False,
        })
    return result


def _approximate_curve_as_polyline(seg: dict, steps: int = 8) -> list[tuple]:
    """Tessellate a Bézier curve into line segments (fallback)."""
    p0, p1, p2, p3 = [seg["points"][i] for i in range(4)]
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
        y = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
        pts.append((x, y))
    return pts


# ---- public API -------------------------------------------------------------

def optimize_geometry(
    raw_segments: list[dict],
    page_width: float,
    page_height: float,
    join_tolerance_pt: float = 0.5,
) -> list[dict]:
    """
    Main optimisation pipeline.  Returns a list of optimised objects:
      { "type": "circle",   "center": (x,y), "radius": r, "is_frame": bool }
      { "type": "polyline", "points": [...],  "closed": bool, "is_frame": bool }
    """
    optimised: list[dict] = []
    pending_lines: list[dict] = []          # lines/rects not yet joined

    # Group curve segments so we can detect 4-arc circles
    # We process drawing-by-drawing; each PyMuPDF drawing already groups items
    # from the same path.  Here we re-group curves that share the same colour/width.
    # Simpler approach: sliding window over all curve segments ordered by appearance.

    curves_buffer: list[dict] = []
    curve_color_buf: tuple | None = None

    def flush_curves():
        nonlocal curves_buffer, curve_color_buf
        buf = curves_buffer[:]
        curves_buffer = []
        curve_color_buf = None
        i = 0
        leftover_lines = []
        while i < len(buf):
            if i + 3 < len(buf):
                candidate = buf[i:i+4]
                ok, cx, cy, r = _curves_form_circle(candidate)
                if ok:
                    optimised.append({
                        "type": "circle",
                        "center": (cx, cy),
                        "radius": r,
                        "is_frame": False,
                    })
                    i += 4
                    continue
            # Fallback: tessellate single curve
            pts = _approximate_curve_as_polyline(buf[i])
            leftover_lines.append({
                "type": "line_chain",
                "points": pts,
                "color": buf[i].get("color"),
                "width": buf[i].get("width", 0.0),
            })
            i += 1
        pending_lines.extend(leftover_lines)

    for seg in raw_segments:
        kind = seg["type"]

        if kind == "line":
            flush_curves()
            pending_lines.append(seg)

        elif kind == "curve":
            col = seg.get("color")
            if curve_color_buf is not None and col != curve_color_buf:
                flush_curves()
            curve_color_buf = col
            curves_buffer.append(seg)

        elif kind in ("rect", "quad"):
            flush_curves()
            if _is_frame(seg, page_width, page_height):
                optimised.append({
                    "type": "polyline",
                    "points": seg["points"],
                    "closed": True,
                    "is_frame": True,
                })
            else:
                pending_lines.append(seg)

        elif kind == "line_chain":
            flush_curves()
            pending_lines.append(seg)

    flush_curves()

    # Normalise all pending line/rect/chain segments to polylines then join
    flat_lines: list[dict] = []
    for seg in pending_lines:
        pts = seg["points"]
        if not pts:
            continue
        closed = _dist(pts[0], pts[-1]) < join_tolerance_pt
        flat_lines.append({
            "type": "line",
            "points": pts,
            "color": seg.get("color"),
            "width": seg.get("width", 0.0),
            "closed": closed,
            "is_frame": _is_frame(seg, page_width, page_height),
        })

    joined = _join_lines(flat_lines, tol=join_tolerance_pt)
    optimised.extend(joined)

    return optimised
