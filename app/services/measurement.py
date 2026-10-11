import logging
from typing import Optional
from shapely.geometry.base import BaseGeometry
import pyproj

from app.models.schemas import MeasurementDetail, MeasurementType
from app.services.crs_service import CRSService

logger = logging.getLogger(__name__)


class MeasurementService:
    """
    Computes accurate geometric measurements (Area for Polygons, Length for LineStrings)
    by transforming geometries to optimal metric projected coordinate systems.
    Handles unsupported, empty, and point geometries gracefully without crashing.
    """

    @classmethod
    def calculate_measurement(
        cls,
        geometry: Optional[BaseGeometry],
        source_crs: pyproj.CRS,
    ) -> MeasurementDetail:
        """
        Main measurement calculation dispatcher.
        """
        if geometry is None or geometry.is_empty:
            return MeasurementDetail(
                type=MeasurementType.NOT_APPLICABLE,
                value=None,
                unit=None,
                formatted=None,
                projected_crs=None,
                status="empty_geometry",
                note="Geometry is empty or has no coordinates.",
            )

        geom_type = geometry.geom_type

        # Point / MultiPoint: specifically required to not have measurements
        if geom_type in ("Point", "MultiPoint"):
            return MeasurementDetail(
                type=MeasurementType.NOT_APPLICABLE,
                value=None,
                unit=None,
                formatted=None,
                projected_crs=None,
                status="not_applicable",
                note=f"{geom_type} geometries have zero area and length by definition.",
            )

        # Polygon / MultiPolygon -> Area
        if geom_type in ("Polygon", "MultiPolygon"):
            return cls._calculate_area(geometry, source_crs)

        # LineString / MultiLineString -> Length
        if geom_type in ("LineString", "MultiLineString", "LinearRing"):
            return cls._calculate_length(geometry, source_crs)

        # GeometryCollection -> Graceful handling
        if geom_type == "GeometryCollection":
            return cls._calculate_collection(geometry, source_crs)

        # Other unsupported types (e.g. 3D TIN, PolyhedralSurface, etc.)
        return MeasurementDetail(
            type=MeasurementType.NOT_APPLICABLE,
            value=None,
            unit=None,
            formatted=None,
            projected_crs=None,
            status="unsupported",
            note=f"Geometry type '{geom_type}' is not supported for measurement calculation.",
        )

    @classmethod
    def _calculate_area(
        cls, geometry: BaseGeometry, source_crs: pyproj.CRS
    ) -> MeasurementDetail:
        try:
            # 1. Determine optimal projected metric CRS (e.g. local UTM zone)
            projected_crs, crs_name = CRSService.get_optimal_projected_crs(geometry, source_crs)

            # 2. Transform geometry to the projected metric CRS
            metric_geom = CRSService.reproject_geometry(geometry, source_crs, projected_crs)

            # 3. Calculate area in square meters
            area_sq_m = float(metric_geom.area)

            # Derived units
            hectares = area_sq_m / 10_000.0
            sq_km = area_sq_m / 1_000_000.0
            acres = area_sq_m * 0.000247105

            formatted_str = format_area(area_sq_m, hectares, sq_km)

            return MeasurementDetail(
                type=MeasurementType.AREA,
                value=round(area_sq_m, 4),
                unit="square_meters",
                formatted=formatted_str,
                additional_units={
                    "hectares": round(hectares, 4),
                    "square_kilometers": round(sq_km, 6),
                    "acres": round(acres, 4),
                },
                projected_crs=crs_name,
                status="calculated",
                note="Calculated using planar projection in metric UTM coordinate system.",
            )

        except Exception as e:
            logger.error(f"Error calculating area for polygon: {e}", exc_info=True)
            return MeasurementDetail(
                type=MeasurementType.AREA,
                value=None,
                unit="square_meters",
                formatted=None,
                projected_crs=None,
                status="error",
                note=f"Failed to calculate area: {str(e)}",
            )

    @classmethod
    def _calculate_length(
        cls, geometry: BaseGeometry, source_crs: pyproj.CRS
    ) -> MeasurementDetail:
        try:
            # 1. Determine optimal projected metric CRS (e.g. local UTM zone)
            projected_crs, crs_name = CRSService.get_optimal_projected_crs(geometry, source_crs)

            # 2. Transform geometry to projected metric CRS
            metric_geom = CRSService.reproject_geometry(geometry, source_crs, projected_crs)

            # 3. Calculate length in meters
            length_m = float(metric_geom.length)

            # Derived units
            km = length_m / 1000.0
            miles = length_m / 1609.344

            formatted_str = format_length(length_m, km)

            return MeasurementDetail(
                type=MeasurementType.LENGTH,
                value=round(length_m, 4),
                unit="meters",
                formatted=formatted_str,
                additional_units={
                    "kilometers": round(km, 4),
                    "miles": round(miles, 4),
                },
                projected_crs=crs_name,
                status="calculated",
                note="Calculated using planar projection in metric UTM coordinate system.",
            )

        except Exception as e:
            logger.error(f"Error calculating length for linestring: {e}", exc_info=True)
            return MeasurementDetail(
                type=MeasurementType.LENGTH,
                value=None,
                unit="meters",
                formatted=None,
                projected_crs=None,
                status="error",
                note=f"Failed to calculate length: {str(e)}",
            )

    @classmethod
    def _calculate_collection(
        cls, geometry: BaseGeometry, source_crs: pyproj.CRS
    ) -> MeasurementDetail:
        """
        Gracefully handles GeometryCollection by analyzing contained geometries.
        """
        try:
            polygons = [g for g in geometry.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
            lines = [g for g in geometry.geoms if g.geom_type in ("LineString", "MultiLineString")]

            if polygons and not lines:
                # Treat as composite polygon
                from shapely.ops import unary_union
                merged = unary_union(polygons)
                return cls._calculate_area(merged, source_crs)
            elif lines and not polygons:
                from shapely.ops import unary_union
                merged = unary_union(lines)
                return cls._calculate_length(merged, source_crs)
            elif polygons and lines:
                # Mixed collection: calculate both and return summary in note
                area_res = cls._calculate_area(geometry, source_crs)
                length_res = cls._calculate_length(geometry, source_crs)
                return MeasurementDetail(
                    type=MeasurementType.AREA,
                    value=area_res.value,
                    unit="square_meters",
                    formatted=f"Area: {area_res.formatted}, Length: {length_res.formatted}",
                    additional_units={
                        "total_area_sq_meters": area_res.value or 0.0,
                        "total_length_meters": length_res.value or 0.0,
                    },
                    projected_crs=area_res.projected_crs,
                    status="calculated",
                    note="Mixed GeometryCollection: calculated combined area and length.",
                )
            else:
                return MeasurementDetail(
                    type=MeasurementType.NOT_APPLICABLE,
                    value=None,
                    unit=None,
                    formatted=None,
                    projected_crs=None,
                    status="not_applicable",
                    note="GeometryCollection contains only points or unsupported types.",
                )
        except Exception as e:
            return MeasurementDetail(
                type=MeasurementType.NOT_APPLICABLE,
                value=None,
                unit=None,
                formatted=None,
                projected_crs=None,
                status="error",
                note=f"Error processing GeometryCollection: {str(e)}",
            )


def format_area(sq_m: float, ha: float, sq_km: float) -> str:
    """Formats area nicely according to scale."""
    if sq_m >= 1_000_000:
        return f"{sq_km:,.2f} km² ({ha:,.1f} ha)"
    elif sq_m >= 10_000:
        return f"{ha:,.2f} ha ({sq_m:,.1f} m²)"
    else:
        return f"{sq_m:,.2f} m²"


def format_length(m: float, km: float) -> str:
    """Formats length nicely according to scale."""
    if m >= 1000:
        return f"{km:,.2f} km ({m:,.1f} m)"
    else:
        return f"{m:,.2f} m"
