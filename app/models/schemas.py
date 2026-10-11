from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel, Field


class FileProcessingStatus(str, Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MeasurementType(str, Enum):
    AREA = "area"
    LENGTH = "length"
    NOT_APPLICABLE = "not_applicable"


class MeasurementDetail(BaseModel):
    type: Optional[MeasurementType] = Field(
        None, description="Type of measurement computed ('area', 'length', or 'not_applicable')"
    )
    value: Optional[float] = Field(
        None, description="Numerical measurement value in base metric units (m² for area, m for length)"
    )
    unit: Optional[str] = Field(
        None, description="Base metric unit of measurement ('square_meters' or 'meters')"
    )
    formatted: Optional[str] = Field(
        None, description="Human-readable formatted string (e.g., '12,450.25 m²')"
    )
    additional_units: Optional[dict[str, float]] = Field(
        default_factory=dict,
        description="Measurement converted to helpful secondary units (hectares, sq_km, km, etc.)",
    )
    projected_crs: Optional[str] = Field(
        None, description="Projected metric coordinate reference system used for calculation (e.g. EPSG:32643)"
    )
    status: str = Field(
        "calculated", description="Status of measurement: 'calculated', 'not_applicable', 'unsupported', 'error'"
    )
    note: Optional[str] = Field(
        None, description="Informational message or rationale for unsupported/non-applicable types"
    )


class FeatureItem(BaseModel):
    feature_id: Union[int, str] = Field(..., description="Unique index or identifier of the feature")
    geometry_type: str = Field(..., description="Geometry type (e.g. Polygon, LineString, Point)")
    geometry: Optional[dict[str, Any]] = Field(
        None, description="GeoJSON geometry object with type and coordinates"
    )
    crs: str = Field(..., description="Original Coordinate Reference System of the feature")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Attributes and properties of the feature"
    )
    measurement: Optional[MeasurementDetail] = Field(
        None, description="Calculated measurement details"
    )


class FileInfoResponse(BaseModel):
    id: str = Field(..., description="Unique identifier of the uploaded file")
    filename: str = Field(..., description="Original name of the uploaded file")
    feature_count: int = Field(..., description="Total number of geospatial features extracted")
    crs: str = Field(..., description="Identified Coordinate Reference System (e.g. EPSG:4326)")
    status: FileProcessingStatus = Field(..., description="Processing status (PROCESSING, COMPLETED, FAILED)")
    file_type: Optional[str] = Field(None, description="Detected file format ('shapefile_zip' or 'kml')")
    file_size_bytes: Optional[int] = Field(None, description="File size in bytes")
    created_at: Optional[str] = Field(None, description="ISO timestamp of upload")
    error_message: Optional[str] = Field(None, description="Error details if processing failed")


class FileUploadResponse(BaseModel):
    id: str = Field(..., description="Unique identifier assigned to the file")
    filename: str = Field(..., description="Original file name")
    feature_count: int = Field(..., description="Number of features extracted")
    crs: str = Field(..., description="Identified CRS")
    status: FileProcessingStatus = Field(..., description="Processing status")
    message: str = Field("File uploaded and processed successfully", description="Status message")


class MeasurementsSummary(BaseModel):
    total_features: int = 0
    polygon_count: int = 0
    linestring_count: int = 0
    point_count: int = 0
    other_count: int = 0
    total_area_sq_meters: float = 0.0
    total_area_hectares: float = 0.0
    total_length_meters: float = 0.0
    total_length_km: float = 0.0


class FeatureMeasurementItem(BaseModel):
    feature_id: Union[int, str]
    geometry_type: str
    properties: dict[str, Any]
    measurement: MeasurementDetail


class MeasurementsResponse(BaseModel):
    id: str = Field(..., description="File ID")
    filename: str = Field(..., description="Original file name")
    feature_count: int = Field(..., description="Number of features")
    crs: str = Field(..., description="Source Coordinate Reference System")
    status: FileProcessingStatus = Field(..., description="Processing status")
    summary: MeasurementsSummary = Field(..., description="Aggregate summary of measurements")
    measurements: list[FeatureMeasurementItem] = Field(
        ..., description="Per-feature measurement results"
    )


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    supported_formats: list[str] = ["Shapefile (.zip)", "KML (.kml)"]
