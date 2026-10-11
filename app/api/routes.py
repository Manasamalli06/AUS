import logging
import shutil
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import (
    CRSTransformationException,
    FileNotFoundInStorageException,
    FileProcessingException,
    InvalidFileFormatException,
)
from app.models.schemas import (
    FileInfoResponse,
    FileProcessingStatus,
    FileUploadResponse,
    HealthResponse,
    MeasurementsResponse,
)
from app.services.parser import GeospatialParserService
from app.services.storage import storage_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Geospatial Files"])


@router.post(
    "/files/",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a geospatial file",
    description="Accepts either a zipped Shapefile (.zip) or a KML file (.kml), parses its features, reprojects coordinates to appropriate metric CRSs, and calculates measurements.",
)
async def upload_file(
    file: UploadFile = File(..., description="Geospatial file: .zip (Shapefile) or .kml")
):
    # Validate filename and extension
    filename = file.filename or "unknown_file"
    suffix = Path(filename).suffix.lower()

    if suffix not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{suffix}'. Only .zip (containing Shapefile) and .kml are supported.",
        )

    file_id = storage_manager.generate_id()
    saved_filename = f"{file_id}_{filename}"
    saved_path = settings.UPLOADS_DIR / saved_filename

    # Stream file to disk while enforcing size limit
    file_size = 0
    try:
        with open(saved_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                file_size += len(chunk)
                if file_size > settings.MAX_FILE_SIZE_BYTES:
                    saved_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_BYTES // (1024*1024)} MB.",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving file {filename}: {e}")
        saved_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}",
        )

    # Process and measure geospatial features
    try:
        features, crs_str, file_type, summary = GeospatialParserService.process_file(
            saved_path, original_filename=filename
        )

        record = storage_manager.save_record(
            file_id=file_id,
            filename=filename,
            file_path=saved_path,
            file_type=file_type,
            file_size_bytes=file_size,
            feature_count=len(features),
            crs=crs_str,
            status=FileProcessingStatus.COMPLETED,
            summary=summary,
            features=features,
        )

        return FileUploadResponse(
            id=record.file_id,
            filename=record.filename,
            feature_count=record.feature_count,
            crs=record.crs,
            status=record.status,
            message="File uploaded and processed successfully",
        )

    except (InvalidFileFormatException, FileProcessingException, CRSTransformationException) as e:
        logger.warning(f"File processing error for {filename}: {e.message}")
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Unexpected error processing {filename}: {e}", exc_info=True)
        saved_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal processing failure: {str(e)}",
        )


@router.get(
    "/files/{file_id}/",
    response_model=FileInfoResponse,
    summary="Get file information",
    description="Returns metadata, processing status, feature count, and CRS for a previously uploaded file.",
)
async def get_file_info(file_id: str):
    try:
        record = storage_manager.get_record(file_id)
        return record.to_file_info()
    except FileNotFoundInStorageException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found.",
        )


@router.get(
    "/files/{file_id}/measurements/",
    response_model=MeasurementsResponse,
    summary="Get measurements for features",
    description="Returns geometric measurements (Area for Polygons, Length for LineStrings) transformed into metric units, alongside properties.",
)
async def get_file_measurements(file_id: str):
    try:
        record = storage_manager.get_record(file_id)
        return record.to_measurements_response()
    except FileNotFoundInStorageException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found.",
        )


@router.get(
    "/files/{file_id}/features/",
    summary="Get GeoJSON FeatureCollection",
    description="Returns all features with GeoJSON geometries, properties, and measurement attributes.",
)
async def get_file_features(file_id: str):
    try:
        record = storage_manager.get_record(file_id)
        geojson_features = []
        for feat in record.features:
            geojson_features.append({
                "type": "Feature",
                "id": feat["feature_id"],
                "geometry": feat["geometry"],
                "properties": {
                    **feat["properties"],
                    "_measurement": feat["measurement"],
                    "_geometry_type": feat["geometry_type"],
                    "_crs": feat["crs"],
                },
            })
        return {
            "type": "FeatureCollection",
            "file_id": record.file_id,
            "filename": record.filename,
            "crs": record.crs,
            "features": geojson_features,
        }
    except FileNotFoundInStorageException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found.",
        )


@router.get(
    "/files/",
    response_model=List[FileInfoResponse],
    summary="List all uploaded files",
    description="Returns a list of all uploaded files and their processing statuses.",
)
async def list_files():
    return storage_manager.list_records()


@router.delete(
    "/files/{file_id}/",
    status_code=status.HTTP_200_OK,
    summary="Delete a file",
    description="Removes the file and its measurement data from storage.",
)
async def delete_file(file_id: str):
    try:
        storage_manager.delete_record(file_id)
        return {"id": file_id, "deleted": True, "message": "File successfully deleted."}
    except FileNotFoundInStorageException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found.",
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Checks API service operational status and supported formats.",
)
async def health_check():
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        supported_formats=["Shapefile (.zip)", "KML (.kml)"],
    )


@router.get(
    "/samples/{filename}",
    summary="Download a sample geospatial file",
    description="Provides direct download of ready-to-test geospatial sample files: survey.kml, parcels.zip, or routes.zip.",
)
async def download_sample(filename: str):
    from fastapi.responses import FileResponse
    samples_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "sample_data"
    file_path = samples_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Sample file '{filename}' not found.")
    
    media_type = "application/zip" if filename.endswith(".zip") else "application/vnd.google-earth.kml+xml"
    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=filename,
    )


@router.post(
    "/samples/{filename}/test",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="One-click load and test a sample file",
    description="Loads one of the pre-built sample files (survey.kml, parcels.zip, routes.zip) directly into the processing engine without needing manual upload.",
)
async def load_sample_file(filename: str):
    samples_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "sample_data"
    source_path = samples_dir / filename
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Sample file '{filename}' not found.")

    file_id = storage_manager.generate_id()
    saved_filename = f"{file_id}_{filename}"
    saved_path = settings.UPLOADS_DIR / saved_filename
    shutil.copy2(source_path, saved_path)
    file_size = saved_path.stat().st_size

    features, crs_str, file_type, summary = GeospatialParserService.process_file(
        saved_path, original_filename=filename
    )

    record = storage_manager.save_record(
        file_id=file_id,
        filename=filename,
        file_path=saved_path,
        file_type=file_type,
        file_size_bytes=file_size,
        feature_count=len(features),
        crs=crs_str,
        status=FileProcessingStatus.COMPLETED,
        summary=summary,
        features=features,
    )

    return FileUploadResponse(
        id=record.file_id,
        filename=record.filename,
        feature_count=record.feature_count,
        crs=record.crs,
        status=record.status,
        message="Sample loaded and processed successfully",
    )

