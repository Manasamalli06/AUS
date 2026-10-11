import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import settings
from app.core.exceptions import FileNotFoundInStorageException
from app.models.schemas import (
    FeatureItem,
    FileInfoResponse,
    FileProcessingStatus,
    MeasurementsResponse,
    MeasurementsSummary,
)

logger = logging.getLogger(__name__)


class FileStorageRecord:
    """Represents a stored file and its processed state."""
    def __init__(
        self,
        file_id: str,
        filename: str,
        file_path: str,
        file_type: str,
        file_size_bytes: int,
        feature_count: int,
        crs: str,
        status: FileProcessingStatus,
        created_at: str,
        summary: Optional[Dict[str, Any]] = None,
        features: Optional[List[Dict[str, Any]]] = None,
        error_message: Optional[str] = None,
    ):
        self.file_id = file_id
        self.filename = filename
        self.file_path = file_path
        self.file_type = file_type
        self.file_size_bytes = file_size_bytes
        self.feature_count = feature_count
        self.crs = crs
        self.status = status
        self.created_at = created_at
        self.summary = summary or {}
        self.features = features or []
        self.error_message = error_message

    def to_file_info(self) -> FileInfoResponse:
        return FileInfoResponse(
            id=self.file_id,
            filename=self.filename,
            feature_count=self.feature_count,
            crs=self.crs,
            status=self.status,
            file_type=self.file_type,
            file_size_bytes=self.file_size_bytes,
            created_at=self.created_at,
            error_message=self.error_message,
        )

    def to_measurements_response(self) -> MeasurementsResponse:
        return MeasurementsResponse(
            id=self.file_id,
            filename=self.filename,
            feature_count=self.feature_count,
            crs=self.crs,
            status=self.status,
            summary=MeasurementsSummary(**self.summary) if self.summary else MeasurementsSummary(),
            measurements=[
                {
                    "feature_id": f["feature_id"],
                    "geometry_type": f["geometry_type"],
                    "properties": f["properties"],
                    "measurement": f["measurement"],
                }
                for f in self.features
            ],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "file_size_bytes": self.file_size_bytes,
            "feature_count": self.feature_count,
            "crs": self.crs,
            "status": self.status.value if isinstance(self.status, FileProcessingStatus) else self.status,
            "created_at": self.created_at,
            "summary": self.summary,
            "features": self.features,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileStorageRecord":
        return cls(
            file_id=data["file_id"],
            filename=data["filename"],
            file_path=data["file_path"],
            file_type=data.get("file_type", "unknown"),
            file_size_bytes=data.get("file_size_bytes", 0),
            feature_count=data.get("feature_count", 0),
            crs=data.get("crs", "Unknown"),
            status=FileProcessingStatus(data.get("status", "COMPLETED")),
            created_at=data.get("created_at", ""),
            summary=data.get("summary", {}),
            features=data.get("features", []),
            error_message=data.get("error_message"),
        )


class StorageManager:
    """Thread-safe disk-backed persistence manager for file records."""

    def __init__(self, db_path: Path = settings.DB_DIR / "records.json"):
        self.db_path = db_path
        self._lock = Lock()
        self._records: Dict[str, FileStorageRecord] = {}
        self._load_from_disk()

    def _load_from_disk(self):
        with self._lock:
            if self.db_path.exists():
                try:
                    with open(self.db_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for file_id, rec_dict in data.items():
                            self._records[file_id] = FileStorageRecord.from_dict(rec_dict)
                    logger.info(f"Loaded {len(self._records)} records from disk.")
                except Exception as e:
                    logger.error(f"Failed to load records from {self.db_path}: {e}")

    def _save_to_disk(self):
        try:
            temp_path = self.db_path.with_suffix(".tmp")
            data = {fid: rec.to_dict() for fid, rec in self._records.items()}
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self.db_path)
        except Exception as e:
            logger.error(f"Failed to save records to disk: {e}")

    def generate_id(self) -> str:
        """Generates a clean short unique identifier."""
        return uuid.uuid4().hex[:12]

    def save_record(
        self,
        file_id: str,
        filename: str,
        file_path: Path,
        file_type: str,
        file_size_bytes: int,
        feature_count: int,
        crs: str,
        status: FileProcessingStatus,
        summary: MeasurementsSummary,
        features: List[FeatureItem],
        error_message: Optional[str] = None,
    ) -> FileStorageRecord:
        with self._lock:
            record = FileStorageRecord(
                file_id=file_id,
                filename=filename,
                file_path=str(file_path),
                file_type=file_type,
                file_size_bytes=file_size_bytes,
                feature_count=feature_count,
                crs=crs,
                status=status,
                created_at=datetime.now(timezone.utc).isoformat(),
                summary=summary.model_dump(),
                features=[f.model_dump() for f in features],
                error_message=error_message,
            )
            self._records[file_id] = record
            self._save_to_disk()
            return record

    def get_record(self, file_id: str) -> FileStorageRecord:
        with self._lock:
            if file_id not in self._records:
                raise FileNotFoundInStorageException(file_id)
            return self._records[file_id]

    def list_records(self) -> List[FileInfoResponse]:
        with self._lock:
            # Sort newest first
            return [
                rec.to_file_info()
                for rec in sorted(
                    self._records.values(), key=lambda r: r.created_at, reverse=True
                )
            ]

    def delete_record(self, file_id: str) -> bool:
        with self._lock:
            if file_id not in self._records:
                raise FileNotFoundInStorageException(file_id)
            record = self._records.pop(file_id)
            # Remove uploaded file from disk if it exists
            try:
                p = Path(record.file_path)
                if p.exists():
                    p.unlink()
            except Exception as e:
                logger.warning(f"Could not delete physical file {record.file_path}: {e}")
            self._save_to_disk()
            return True


storage_manager = StorageManager()
