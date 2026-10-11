import pytest
import pyproj
from shapely.geometry import Point, LineString, Polygon, GeometryCollection

from app.models.schemas import MeasurementType
from app.services.measurement import MeasurementService


@pytest.fixture
def wgs84():
    return pyproj.CRS.from_epsg(4326)


def test_polygon_area_calculation(wgs84):
    # ~1.1km x 1.1km square in Bangalore
    poly = Polygon([
        (77.59, 12.97),
        (77.60, 12.97),
        (77.60, 12.98),
        (77.59, 12.98),
        (77.59, 12.97)
    ])

    meas = MeasurementService.calculate_measurement(poly, wgs84)

    assert meas.type == MeasurementType.AREA
    assert meas.unit == "square_meters"
    assert meas.status == "calculated"
    assert meas.value is not None
    # Roughly 1.1km * 1.1km is ~1.2 million m²
    assert 1_000_000 < meas.value < 1_500_000
    assert "hectares" in meas.additional_units
    assert "square_kilometers" in meas.additional_units
    assert "UTM" in meas.projected_crs


def test_linestring_length_calculation(wgs84):
    # ~1.1km line
    line = LineString([(77.59, 12.97), (77.60, 12.97)])

    meas = MeasurementService.calculate_measurement(line, wgs84)

    assert meas.type == MeasurementType.LENGTH
    assert meas.unit == "meters"
    assert meas.status == "calculated"
    assert meas.value is not None
    # Roughly 1000m to 1200m
    assert 1000 < meas.value < 1200
    assert "kilometers" in meas.additional_units
    assert "miles" in meas.additional_units


def test_point_graceful_handling(wgs84):
    pt = Point(77.59, 12.97)

    meas = MeasurementService.calculate_measurement(pt, wgs84)

    assert meas.type == MeasurementType.NOT_APPLICABLE
    assert meas.value is None
    assert meas.status == "not_applicable"
    assert "zero area and length" in meas.note


def test_empty_geometry_graceful_handling(wgs84):
    empty_poly = Polygon()

    meas = MeasurementService.calculate_measurement(empty_poly, wgs84)

    assert meas.value is None
    assert meas.status == "empty_geometry"
