import pytest
import pyproj
from shapely.geometry import Point, Polygon

from app.services.crs_service import CRSService


def test_normalize_crs_standard():
    crs, name, is_fallback = CRSService.normalize_crs("EPSG:4326")
    assert crs.to_epsg() == 4326
    assert "EPSG:4326" in name
    assert is_fallback is False


def test_normalize_crs_fallback():
    crs, name, is_fallback = CRSService.normalize_crs(None)
    assert crs.to_epsg() == 4326
    assert is_fallback is True


def test_is_geographic():
    wgs84 = pyproj.CRS.from_epsg(4326)
    utm = pyproj.CRS.from_epsg(32643)
    assert CRSService.is_geographic(wgs84) is True
    assert CRSService.is_geographic(utm) is False


def test_utm_zone_selection_bangalore():
    # Bangalore: lon 77.59, lat 12.97 -> UTM zone 43N (EPSG:32643)
    poly = Polygon([
        (77.59, 12.97),
        (77.60, 12.97),
        (77.60, 12.98),
        (77.59, 12.98),
        (77.59, 12.97)
    ])
    wgs84 = pyproj.CRS.from_epsg(4326)
    target_crs, crs_desc = CRSService.get_optimal_projected_crs(poly, wgs84)
    assert target_crs.to_epsg() == 32643
    assert "UTM Zone 43N" in crs_desc


def test_utm_zone_selection_newyork():
    # New York: lon -73.97, lat 40.78 -> UTM zone 18N (EPSG:32618)
    poly = Polygon([
        (-73.97, 40.78),
        (-73.96, 40.78),
        (-73.96, 40.79),
        (-73.97, 40.79),
        (-73.97, 40.78)
    ])
    wgs84 = pyproj.CRS.from_epsg(4326)
    target_crs, crs_desc = CRSService.get_optimal_projected_crs(poly, wgs84)
    assert target_crs.to_epsg() == 32618
    assert "UTM Zone 18N" in crs_desc


def test_reproject_geometry():
    poly = Polygon([
        (77.59, 12.97),
        (77.60, 12.97),
        (77.60, 12.98),
        (77.59, 12.98),
        (77.59, 12.97)
    ])
    wgs84 = pyproj.CRS.from_epsg(4326)
    utm43n = pyproj.CRS.from_epsg(32643)

    transformed = CRSService.reproject_geometry(poly, wgs84, utm43n)
    assert transformed.is_valid
    # In UTM meters, coordinates should be hundreds of thousands of meters
    minx, miny, maxx, maxy = transformed.bounds
    assert minx > 100_000
    assert miny > 1_000_000
