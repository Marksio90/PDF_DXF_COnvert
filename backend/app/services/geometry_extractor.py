"""
Geometry Extractor — pulls raw path data from a PDF page via PyMuPDF
and normalises it into a flat list of primitive path segments.

Each segment carries a `drawing_id` (index into page.get_drawings()) so the
optimizer can process items from the same PDF path as one connected unit.
"""
from __future__ import annotations
import fitz


def extract_paths(pdf_path: str, page_idx: int = 0) -> tuple[list[dict], float, float]:
    """
    Returns (raw_segments, page_width_pt, page_height_pt).

    Each raw segment:
      { "type": "line"|"curve"|"rect"|"quad",
        "drawing_id": int,   ← index of the PDF path this item belongs to
        "points": [...],
        "color": ..., "width": ... }
    """
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    rect = page.rect
    width_pt  = rect.width
    height_pt = rect.height

    raw_segments: list[dict] = []
    drawings = page.get_drawings()

    for drawing_id, drawing in enumerate(drawings):
        color      = drawing.get("color") or drawing.get("fill")
        line_width = drawing.get("width", 0.0)

        for item in drawing.get("items", []):
            kind = item[0]

            if kind == "l":  # line
                p0, p1 = item[1], item[2]
                raw_segments.append({
                    "type": "line",
                    "drawing_id": drawing_id,
                    "points": [(p0.x, p0.y), (p1.x, p1.y)],
                    "color": color,
                    "width": line_width,
                })

            elif kind == "c":  # cubic Bézier
                p0, p1, p2, p3 = item[1], item[2], item[3], item[4]
                raw_segments.append({
                    "type": "curve",
                    "drawing_id": drawing_id,
                    "points": [
                        (p0.x, p0.y), (p1.x, p1.y),
                        (p2.x, p2.y), (p3.x, p3.y),
                    ],
                    "color": color,
                    "width": line_width,
                })

            elif kind == "re":  # rectangle
                r = item[1]
                raw_segments.append({
                    "type": "rect",
                    "drawing_id": drawing_id,
                    "points": [
                        (r.x0, r.y0), (r.x1, r.y0),
                        (r.x1, r.y1), (r.x0, r.y1),
                        (r.x0, r.y0),
                    ],
                    "color": color,
                    "width": line_width,
                })

            elif kind == "qu":  # quad
                pts = item[1]
                raw_segments.append({
                    "type": "quad",
                    "drawing_id": drawing_id,
                    "points": [
                        (pts.ul.x, pts.ul.y), (pts.ur.x, pts.ur.y),
                        (pts.lr.x, pts.lr.y), (pts.ll.x, pts.ll.y),
                        (pts.ul.x, pts.ul.y),
                    ],
                    "color": color,
                    "width": line_width,
                })

    doc.close()
    return raw_segments, width_pt, height_pt


def extract_text_blocks(pdf_path: str, page_idx: int = 0) -> list[dict]:
    """Extract all text blocks with position for scale detection and TEXT layer."""
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    blocks = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text, block_no, block_type = block
        if block_type == 0 and text.strip():
            blocks.append({
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "text": text.strip(),
            })
    doc.close()
    return blocks
