"""
PDF Analyzer — classifies the PDF as vector/mixed/raster and extracts
page-level metadata needed by the rest of the pipeline.
"""
from __future__ import annotations
import fitz  # PyMuPDF


class PDFAnalysis:
    def __init__(self):
        self.page_count: int = 0
        self.pdf_type: str = "unknown"          # vector | mixed | raster
        self.pages: list[dict] = []             # per-page metadata
        self.width_pt: float = 0.0
        self.height_pt: float = 0.0

    def to_dict(self) -> dict:
        return {
            "page_count": self.page_count,
            "pdf_type": self.pdf_type,
            "width_pt": self.width_pt,
            "height_pt": self.height_pt,
            "pages": self.pages,
        }


def analyze_pdf(pdf_path: str) -> PDFAnalysis:
    result = PDFAnalysis()
    doc = fitz.open(pdf_path)
    result.page_count = len(doc)

    vector_pages = 0
    raster_pages = 0

    for page_idx, page in enumerate(doc):
        rect = page.rect
        drawings = page.get_drawings()
        text_blocks = page.get_text("blocks")
        images = page.get_images(full=False)

        path_count = len(drawings)
        text_count = len(text_blocks)
        image_count = len(images)

        has_vector = path_count > 5
        has_raster = image_count > 0

        if has_vector and not has_raster:
            page_type = "vector"
            vector_pages += 1
        elif has_vector and has_raster:
            page_type = "mixed"
            vector_pages += 1
        elif has_raster and not has_vector:
            page_type = "raster"
            raster_pages += 1
        else:
            page_type = "empty"

        result.pages.append({
            "page_idx": page_idx,
            "width_pt": rect.width,
            "height_pt": rect.height,
            "page_type": page_type,
            "path_count": path_count,
            "text_count": text_count,
            "image_count": image_count,
        })

        if page_idx == 0:
            result.width_pt = rect.width
            result.height_pt = rect.height

    doc.close()

    if vector_pages == 0 and raster_pages > 0:
        result.pdf_type = "raster"
    elif vector_pages > 0 and raster_pages == 0:
        result.pdf_type = "vector"
    else:
        result.pdf_type = "mixed"

    return result
