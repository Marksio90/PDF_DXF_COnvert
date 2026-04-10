"""
DXF Writer — converts optimised geometry objects into an ezdxf document.

Key responsibilities:
  • Y-axis flip: Y_dxf = page_height_pt - Y_pdf  (PDF grows down, DXF grows up)
  • Scale: all coordinates multiplied by scale_factor (pt → mm or inch)
  • Native circles and arcs (no polyline approximation)
  • Layer assignment: GEOMETRY, FRAME, TEXT, DIMENSIONS_HINTS
"""
from __future__ import annotations
import math
import ezdxf
from ezdxf.enums import TextEntityAlignment


_LAYERS = {
    "GEOMETRY": {"color": 7},        # white / black
    "FRAME": {"color": 8},           # grey
    "TEXT": {"color": 3},            # green
    "DIMENSIONS_HINTS": {"color": 1},  # red
}

_DXF_VERSION = "R2010"


def _flip_y(y: float, page_height_pt: float) -> float:
    return page_height_pt - y


def _transform(pt: tuple, page_height_pt: float, scale: float) -> tuple:
    x, y = pt
    return x * scale, _flip_y(y, page_height_pt) * scale


def write_dxf(
    optimised_paths: list[dict],
    text_blocks: list[dict],
    page_height_pt: float,
    scale_factor: float,
    output_path: str,
    unit: str = "mm",
) -> dict:
    """
    Write a DXF file from optimised geometry.

    Returns a summary dict with counts per layer.
    """
    doc = ezdxf.new(_DXF_VERSION)
    msp = doc.modelspace()

    # Set drawing units
    if unit == "mm":
        doc.header["$INSUNITS"] = 4   # mm
    elif unit == "inch":
        doc.header["$INSUNITS"] = 1   # inch
    else:
        doc.header["$INSUNITS"] = 4

    # Create layers
    for name, props in _LAYERS.items():
        if name not in doc.layers:
            doc.layers.add(name, dxfattribs={"color": props["color"]})

    counts: dict[str, int] = {k: 0 for k in _LAYERS}

    sf = scale_factor
    ph = page_height_pt

    # ---- geometry objects ---------------------------------------------------
    for obj in optimised_paths:
        layer = "FRAME" if obj.get("is_frame") else "GEOMETRY"
        obj_type = obj.get("type")

        if obj_type == "circle":
            cx, cy = obj["center"]
            r = obj["radius"]
            tx, ty = _transform((cx, cy), ph, sf)
            msp.add_circle(
                (tx, ty),
                radius=r * sf,
                dxfattribs={"layer": layer},
            )
            counts[layer] += 1

        elif obj_type == "arc":
            # Konwertuj łuk z przestrzeni PDF do DXF (Y-flip + scale)
            cx, cy = obj["center"]
            r       = obj["radius"]
            p_start = obj["p_start"]
            p_end   = obj["p_end"]
            p_mid   = obj["p_mid"]

            tcx, tcy = _transform((cx, cy), ph, sf)
            tsx, tsy = _transform(p_start, ph, sf)
            tex, tey = _transform(p_end,   ph, sf)
            tmx, tmy = _transform(p_mid,   ph, sf)
            tr = r * sf

            # Kąty w przestrzeni DXF (po Y-flip)
            sa  = math.degrees(math.atan2(tsy - tcy, tsx - tcx)) % 360
            ea  = math.degrees(math.atan2(tey - tcy, tex - tcx)) % 360
            ma  = math.degrees(math.atan2(tmy - tcy, tmx - tcx)) % 360

            # Sprawdź czy łuk biegnie CCW (standard DXF).
            # Jeśli punkt środkowy łuku nie leży na łuku CCW sa→ea, zamień kierunek.
            def _between_ccw(s: float, m: float, e: float) -> bool:
                if abs(s - e) < 1e-6:
                    return True
                if s < e:
                    return s <= m <= e
                return m >= s or m <= e

            if not _between_ccw(sa, ma, ea):
                sa, ea = ea, sa   # odwróć → CCW

            msp.add_arc(
                (tcx, tcy),
                radius=tr,
                start_angle=sa,
                end_angle=ea,
                dxfattribs={"layer": layer},
            )
            counts[layer] += 1

        elif obj_type == "polyline":
            pts = obj.get("points", [])
            if len(pts) < 2:
                continue
            transformed = [_transform(p, ph, sf) for p in pts]
            closed = obj.get("closed", False)
            msp.add_lwpolyline(
                transformed,
                close=closed,
                dxfattribs={"layer": layer},
            )
            counts[layer] += 1

    # ---- text layer ---------------------------------------------------------
    for block in text_blocks:
        x0, y0 = block["x0"], block["y0"]
        tx, ty = _transform((x0, y0), ph, sf)
        text = block["text"].replace("\n", " ").strip()
        if not text:
            continue
        msp.add_text(
            text,
            dxfattribs={
                "layer": "TEXT",
                "height": 2.5,
                "insert": (tx, ty),
            },
        )
        counts["TEXT"] += 1

    doc.saveas(output_path)
    return counts
