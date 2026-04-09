from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON
from sqlalchemy.sql import func
from .database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    status = Column(String(20), default="queued", nullable=False)
    # queued | analyzing | converting | done | error

    original_filename = Column(String(255), nullable=False)
    pdf_path = Column(String(512), nullable=True)
    dxf_path = Column(String(512), nullable=True)
    preview_path = Column(String(512), nullable=True)

    pdf_type = Column(String(20), nullable=True)   # vector | mixed | raster
    page_count = Column(Integer, nullable=True)
    page_width_pt = Column(Float, nullable=True)
    page_height_pt = Column(Float, nullable=True)

    scale_status = Column(String(20), nullable=True)  # verified | assumed | unverified
    scale_factor = Column(Float, nullable=True)
    unit = Column(String(10), nullable=True)
    unit_source = Column(String(20), nullable=True)   # forced | text | default

    confidence_score = Column(Integer, nullable=True)
    qa_report = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
