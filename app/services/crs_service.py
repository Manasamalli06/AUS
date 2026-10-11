import math
import logging
from typing import Optional, Tuple
import pyproj
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
import shapely

from app.core.exceptions import CRSTransformationException

logger = logging.getLogger(__name__)


class CRSService:
    """
    Handles Coordinate Reference System (CRS) inspection, UTM zone determination,
    and reprojection from geographic (degrees) to planar projected (metric) systems.
    """

    DEFAULT_GEOGRAPHIC_CRS = pyproj.CRS.from_epsg(4326)
    EQUAL_AREA_FALLBACK_CRS = pyproj.CRS.from_epsg(6933)  # World Cylindrical Equal Area (metric)

    @classmethod
    def normalize_crs(cls, raw_crs: Optional[object]) -> Tuple[pyproj.CRS, str, bool]:
        """
        Normalizes any CRS object (string, int, pyproj.CRS, dict, None) into a pyproj.CRS.
        Returns: (pyproj.CRS, human_readable_string, is_fallback)
        """
        if raw_crs is None or raw_crs == "" or str(raw_crs).strip().lower() in ("none", "null", "undefined"):
            logger.warning("No CRS detected in source file. Defaulting to EPSG:4326.")
            return cls.DEFAULT_GEOGRAPHIC_CRS, "EPSG:4326 (Default Assumed)", True

        try:
            crs_obj = pyproj.CRS.from_user_input(raw_crs)
            auth = crs_obj.to_authority()
            if auth:
                crs_str = f"{auth[0]}:{auth[1]}"
            else:
                crs_str = crs_obj.name or str(raw_crs)
            return crs_obj, crs_str, False
        except Exception as e:
            logger.warning(f"Could not parse CRS '{raw_crs}': {e}. Defaulting to EPSG:4326.")
            return cls.DEFAULT_GEOGRAPHIC_CRS, "EPSG:4326 (Fallback Assumed)", True

    @classmethod
    def is_geographic(cls, crs: pyproj.CRS) -> bool:
        """Returns True if the CRS uses angular units (e.g. degrees like EPSG:4326)."""
        return crs.is_geographic

    @classmethod
    def get_optimal_projected_crs(
        cls, geometry: BaseGeometry, source_crs: pyproj.CRS
    ) -> Tuple[pyproj.CRS, str]:
        """
        Determines the optimal metric projected CRS for measurement.
        
        Strategy:
        1. If source CRS is already projected and has linear units in meters, use it.
        2. If source CRS is geographic (e.g., EPSG:4326), compute the geometry's centroid
           in WGS84 and select the exact local UTM zone (EPSG:32601-32660 / 32701-32760).
        3. If coordinates are in polar regions (|lat| > 80), use UPS or World Cylindrical Equal Area (EPSG:6933).
        """
        # If already projected in meters, source CRS is appropriate
        if crs_is_metric_projected(source_crs):
            auth = source_crs.to_authority()
            auth_str = f"{auth[0]}:{auth[1]}" if auth else source_crs.name
            return source_crs, f"{auth_str} ({source_crs.name})"

        if geometry is None or geometry.is_empty:
            # Fallback to World Cylindrical Equal Area for empty geometry
            return cls.EQUAL_AREA_FALLBACK_CRS, "EPSG:6933 (World Cylindrical Equal Area)"

        # Reproject centroid to WGS84 if source CRS is not already WGS84
        try:
            centroid = geometry.centroid
            lon, lat = centroid.x, centroid.y

            if not source_crs.equals(cls.DEFAULT_GEOGRAPHIC_CRS):
                transformer_to_wgs84 = pyproj.Transformer.from_crs(
                    source_crs, cls.DEFAULT_GEOGRAPHIC_CRS, always_xy=True
                )
                lon, lat = transformer_to_wgs84.transform(lon, lat)

            # Check polar boundaries
            if lat > 84.0 or lat < -80.0:
                return cls.EQUAL_AREA_FALLBACK_CRS, "EPSG:6933 (World Cylindrical Equal Area - Polar)"

            # Standard UTM calculation
            zone_number = int(math.floor((lon + 180.0) / 6.0)) + 1
            zone_number = max(1, min(60, zone_number))

            if lat >= 0.0:
                epsg_code = 32600 + zone_number
                hemisphere = "N"
            else:
                epsg_code = 32700 + zone_number
                hemisphere = "S"

            target_crs = pyproj.CRS.from_epsg(epsg_code)
            crs_desc = f"EPSG:{epsg_code} (WGS 84 / UTM Zone {zone_number}{hemisphere})"
            return target_crs, crs_desc

        except Exception as e:
            logger.warning(f"Error determining UTM zone: {e}. Using EPSG:6933.")
            return cls.EQUAL_AREA_FALLBACK_CRS, "EPSG:6933 (World Cylindrical Equal Area)"

    @classmethod
    def reproject_geometry(
        cls, geometry: BaseGeometry, source_crs: pyproj.CRS, target_crs: pyproj.CRS
    ) -> BaseGeometry:
        """
        Reprojects a Shapely geometry from source_crs to target_crs.
        Ensures resulting geometry is topologically valid.
        """
        if geometry is None or geometry.is_empty:
            return geometry

        if source_crs.equals(target_crs):
            return geometry

        try:
            import numpy as np
            transformer = pyproj.Transformer.from_crs(source_crs, target_crs, always_xy=True)
            transformed_geom = shapely.transform(
                geometry, lambda coords: np.column_stack(transformer.transform(coords[:, 0], coords[:, 1]))
            )

            # Repair any minor self-intersections or precision issues caused by reprojection
            if not transformed_geom.is_valid:
                transformed_geom = shapely.make_valid(transformed_geom)

            return transformed_geom
        except Exception as e:
            raise CRSTransformationException(
                f"Failed to transform geometry from {source_crs} to {target_crs}: {str(e)}"
            )


def crs_is_metric_projected(crs: pyproj.CRS) -> bool:
    """Helper to check if a CRS is projected and uses meters as unit."""
    try:
        if not crs.is_projected:
            return False
        # Check axis units
        axis_info = crs.axis_info
        if axis_info:
            unit_name = str(axis_info[0].unit_name).lower()
            return "metre" in unit_name or "meter" in unit_name
        return True
    except Exception:
        return False
