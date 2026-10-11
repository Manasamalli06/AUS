from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseModel):
    APP_NAME: str = "Geospatial File Measurement API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = (
        "Production-ready backend API to process geospatial files (Shapefiles and KML), "
        "extract features, reproject coordinates to optimal metric CRSs, and compute geometry measurements."
    )
    
    # Storage settings
    STORAGE_DIR: Path = BASE_DIR / "storage"
    UPLOADS_DIR: Path = BASE_DIR / "storage" / "uploads"
    DB_DIR: Path = BASE_DIR / "storage" / "db"
    
    # Upload constraints
    MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
    ALLOWED_EXTENSIONS: set[str] = {".zip", ".kml"}
    
    # Default CRS when input file lacks spatial reference
    DEFAULT_FALLBACK_CRS: str = "EPSG:4326"

settings = Settings()

# Ensure directories exist
settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
settings.DB_DIR.mkdir(parents=True, exist_ok=True)
