import json
import logging
import math
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, List, Optional, Tuple

import geopandas as gpd
import pandas as pd
import pyproj
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from app.core.exceptions import FileProcessingException, InvalidFileFormatException
from app.models.schemas import FeatureItem, MeasurementsSummary
from app.services.crs_service import CRSService
from app.services.measurement import MeasurementService

logger = logging.getLogger(__name__)


class GeospatialParserService:
    """
    Parses zipped Shapefiles (.zip) and KML files (.kml).
    Extracts features, geometry GeoJSON, attributes, CRS, and runs measurement calculations.
    """

    @classmethod
    def process_file(
        cls, file_path: Path, original_filename: str
    ) -> Tuple[List[FeatureItem], str, str, MeasurementsSummary]:
        """
        Processes uploaded file and returns:
        (features, detected_crs_str, file_type, summary)
        """
        suffix = original_filename.lower()
        if suffix.endswith(".zip"):
            gdf, detected_crs, file_type = cls._read_shapefile_zip(file_path)
        elif suffix.endswith(".kml"):
            gdf, detected_crs, file_type = cls._read_kml(file_path)
        else:
            raise InvalidFileFormatException(
                f"Unsupported file format for '{original_filename}'. Allowed formats: .zip (Shapefile) or .kml."
            )

        # Normalize CRS
        crs_obj, crs_str, _ = CRSService.normalize_crs(detected_crs)

        # Extract features and calculate measurements
        features: List[FeatureItem] = []
        summary = MeasurementsSummary(total_features=len(gdf))

        for idx, row in gdf.iterrows():
            geom: Optional[BaseGeometry] = row.get("geometry")

            geom_type = geom.geom_type if (geom is not None and not geom.is_empty) else "None"
            geom_dict = mapping(geom) if (geom is not None and not geom.is_empty) else None

            # Extract and sanitize attributes (excluding geometry)
            properties = {}
            for col, val in row.items():
                if col != "geometry":
                    properties[col] = sanitize_value(val)

            # Feature ID / index
            feature_id = properties.get("id") or properties.get("ID") or properties.get("fid") or idx

            # Compute measurement
            meas = MeasurementService.calculate_measurement(geom, crs_obj)

            # Update aggregate summary
            if geom_type in ("Polygon", "MultiPolygon"):
                summary.polygon_count += 1
                if meas.value is not None:
                    summary.total_area_sq_meters += meas.value
            elif geom_type in ("LineString", "MultiLineString", "LinearRing"):
                summary.linestring_count += 1
                if meas.value is not None:
                    summary.total_length_meters += meas.value
            elif geom_type in ("Point", "MultiPoint"):
                summary.point_count += 1
            else:
                summary.other_count += 1

            features.append(
                FeatureItem(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    geometry=geom_dict,
                    crs=crs_str,
                    properties=properties,
                    measurement=meas,
                )
            )

        # Finalize summary derived values
        summary.total_area_sq_meters = round(summary.total_area_sq_meters, 4)
        summary.total_area_hectares = round(summary.total_area_sq_meters / 10_000.0, 4)
        summary.total_length_meters = round(summary.total_length_meters, 4)
        summary.total_length_km = round(summary.total_length_meters / 1000.0, 4)

        return features, crs_str, file_type, summary

    @classmethod
    def _read_shapefile_zip(cls, zip_path: Path) -> Tuple[gpd.GeoDataFrame, Any, str]:
        """
        Unzips archive and reads Shapefile (.shp).
        Supports nested folders inside zip archives.
        """
        temp_dir = Path(tempfile.mkdtemp(prefix="aus_shp_"))
        try:
            try:
                with zipfile.ZipFile(zip_path, "r") as archive:
                    # Check for path traversal vulnerabilities (Zip Slip)
                    for member in archive.namelist():
                        resolved_path = (temp_dir / member).resolve()
                        if not str(resolved_path).startswith(str(temp_dir.resolve())):
                            raise InvalidFileFormatException("Archive contains illegal path references.")
                    archive.extractall(temp_dir)
            except zipfile.BadZipFile:
                raise InvalidFileFormatException("The uploaded zip file is corrupt or not a valid archive.")

            # Search for .shp files in the extracted tree
            shp_files = list(temp_dir.rglob("*.shp"))
            if not shp_files:
                raise FileProcessingException(
                    "No Shapefile (.shp) found in the uploaded zip archive. "
                    "Ensure the zip contains at least .shp, .shx, and .dbf files."
                )

            shp_file = shp_files[0]
            logger.info(f"Loading Shapefile from extracted path: {shp_file}")

            # Read via GeoPandas (using pyogrio or fiona)
            try:
                gdf = gpd.read_file(shp_file, engine="pyogrio")
            except Exception:
                gdf = gpd.read_file(shp_file)

            if gdf is None or len(gdf) == 0:
                # Return empty GDF gracefully
                gdf = gpd.GeoDataFrame(columns=["geometry"])

            return gdf, gdf.crs, "shapefile_zip"

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @classmethod
    def _read_kml(cls, kml_path: Path) -> Tuple[gpd.GeoDataFrame, Any, str]:
        """
        Reads KML file using pyogrio or fiona or fastkml fallback.
        """
        # Strategy 1: GeoPandas with pyogrio (native GDAL KML driver)
        try:
            gdf = gpd.read_file(kml_path, engine="pyogrio")
            logger.info(f"Successfully read KML via pyogrio: {len(gdf)} features")
            return gdf, gdf.crs or "EPSG:4326", "kml"
        except Exception as e_pyogrio:
            logger.warning(f"pyogrio failed to read KML ({e_pyogrio}), attempting fiona...")

        # Strategy 2: Fiona with enabled KML driver
        try:
            import fiona
            if "KML" not in fiona.drvsupport.supported_drivers:
                fiona.drvsupport.supported_drivers["KML"] = "r"
                fiona.drvsupport.supported_drivers["LIBKML"] = "r"

            gdf = gpd.read_file(kml_path, driver="KML")
            logger.info(f"Successfully read KML via fiona: {len(gdf)} features")
            return gdf, gdf.crs or "EPSG:4326", "kml"
        except Exception as e_fiona:
            logger.warning(f"fiona failed to read KML ({e_fiona}), attempting fastkml fallback...")

        # Strategy 3: FastKML fallback parser
        try:
            gdf = cls._read_kml_with_fastkml(kml_path)
            logger.info(f"Successfully read KML via fastkml: {len(gdf)} features")
            return gdf, "EPSG:4326", "kml"
        except Exception as e_fastkml:
            logger.error(f"All KML parsers failed: {e_fastkml}")
            raise FileProcessingException(
                f"Failed to parse KML file. Details: {str(e_fastkml)}"
            )

    @classmethod
    def _read_kml_with_fastkml(cls, kml_path: Path) -> gpd.GeoDataFrame:
        """
        Fallback parser using fastkml.
        """
        from fastkml import kml
        from shapely.geometry import shape

        with open(kml_path, "rb") as f:
            raw_content = f.read()

        k = kml.KML()
        k.from_string(raw_content)

        features_data = []

        def extract_features(element):
            if hasattr(element, "features"):
                for child in element.features():
                    extract_features(child)
            else:
                geom = None
                if hasattr(element, "geometry") and element.geometry is not None:
                    try:
                        geom = shape(element.geometry)
                    except Exception:
                        geom = None
                
                props = {
                    "name": getattr(element, "name", None),
                    "description": getattr(element, "description", None),
                }
                features_data.append({"geometry": geom, **props})

        for doc in k.features():
            extract_features(doc)

        if not features_data:
            return gpd.GeoDataFrame(columns=["geometry", "name", "description"], crs="EPSG:4326")

        return gpd.GeoDataFrame(features_data, crs="EPSG:4326")


def sanitize_value(val: Any) -> Any:
    """
    Sanitizes values to standard JSON-serializable Python data types.
    Handles NaN, inf, NaT, datetime, numpy numbers.
    """
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (float, int)):
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if isinstance(val, (bytes, bytearray)):
        return val.decode("utf-8", errors="replace")
    if hasattr(val, "item"):  # numpy scalar types
        native = val.item()
        if isinstance(native, float) and (math.isnan(native) or math.isinf(native)):
            return None
        return native
    return str(val) if not isinstance(val, (str, bool, list, dict)) else val
