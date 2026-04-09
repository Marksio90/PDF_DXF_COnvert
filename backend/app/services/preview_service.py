"""
Preview Service — renders the first page of a PDF to a PNG thumbnail
using PyMuPDF, suitable for displaying in the frontend.
"""
from __future__ import annotations
from pathlib import Path
import fitz


def generate_preview(pdf_path: str, output_path: str, dpi: int = 96) -> bool:
    """
    Render the first page of pdf_path to a PNG at output_path.
    Returns True on success.
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
        pix.save(output_path)
        doc.close()
        return True
    except Exception:
        return False
