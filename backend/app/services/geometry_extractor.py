"""
Geometry Extractor — pulls raw path data from a PDF page via PyMuPDF
and normalises it into a flat list of primitive path segments.
"""
from __future__ import annotations
import fitz


def extract_paths(pdf_path: str, page_idx: int = 0) -> tuple[list[dict], float, float]:
    """
    Returns (raw_segments, page_width_pt, page_height_pt).

    Uwaga: współrzędne są zawsze w PDF user-space units (domyślnie pt = 1/72 cala).
    Jeśli strona ma UserUnit ≠ 1, PyMuPDF automatycznie skaluje rect i rysunki,
    więc page.rect.width i współrzędne get_drawings() są już uwzględnione.

    Each raw segment is a dict:
      { "type": "line"|"curve", "points": [...], "color": ..., "width": ... }
    """
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    rect = page.rect
    width_pt = rect.width
    height_pt = rect.height

    raw_segments: list[dict] = []
    drawings = page.get_drawings()

    for drawing in drawings:
        color = drawing.get("color") or drawing.get("fill")
        line_width = drawing.get("width", 0.0)

        for item in drawing.get("items", []):
            kind = item[0]

            if kind == "l":  # line
                p0 = item[1]
                p1 = item[2]
                raw_segments.append({
                    "type": "line",
                    "points": [(p0.x, p0.y), (p1.x, p1.y)],
                    "color": color,
                    "width": line_width,
                })

            elif kind == "c":  # cubic Bézier
                p0 = item[1]
                p1 = item[2]
                p2 = item[3]
                p3 = item[4]
                raw_segments.append({
                    "type": "curve",
                    "points": [
                        (p0.x, p0.y),
                        (p1.x, p1.y),
                        (p2.x, p2.y),
                        (p3.x, p3.y),
                    ],
                    "color": color,
                    "width": line_width,
                })

            elif kind == "re":  # rectangle
                r = item[1]
                raw_segments.append({
                    "type": "rect",
                    "points": [
                        (r.x0, r.y0),
                        (r.x1, r.y0),
                        (r.x1, r.y1),
                        (r.x0, r.y1),
                        (r.x0, r.y0),
                    ],
                    "color": color,
                    "width": line_width,
                })

            elif kind == "qu":  # quad
                pts = item[1]
                raw_segments.append({
                    "type": "quad",
                    "points": [
                        (pts.ul.x, pts.ul.y),
                        (pts.ur.x, pts.ur.y),
                        (pts.lr.x, pts.lr.y),
                        (pts.ll.x, pts.ll.y),
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
