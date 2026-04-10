from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATA_DIR: Path = Path("/data")
    UPLOADS_DIR: Path = Path("/data/uploads")
    OUTPUTS_DIR: Path = Path("/data/outputs")
    PREVIEWS_DIR: Path = Path("/data/previews")
    DB_PATH: Path = Path("/data/jobs.db")

    # Geometry tolerances
    NODE_JOIN_TOLERANCE_MM: float = 0.1       # legacy, kept for compat
    NODE_JOIN_LOOSE_PT: float = 15.0          # loose join between PDF paths (≈5 mm)
    CIRCLE_KAPPA: float = 0.5522847498        # Bézier circle approximation constant
    CIRCLE_KAPPA_TOLERANCE: float = 0.02      # tolerance around kappa
    FRAME_BBOX_RATIO: float = 0.92            # BBox > 92% of page = frame
    MIN_CIRCLE_RADIUS_PT: float = 1.0         # minimum circle radius in PDF pts

    # Scale detection
    SCALE_CONFIDENCE_PENALTY_UNKNOWN: int = 40
    SCALE_CONFIDENCE_PENALTY_ASSUMED: int = 15

    # Garbage collector
    GC_MAX_AGE_HOURS: int = 48
    GC_INTERVAL_SECONDS: int = 3600           # run every hour

    # API
    MAX_UPLOAD_SIZE_MB: int = 50
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://frontend:3000"]

    class Config:
        env_file = ".env"


settings = Settings()
