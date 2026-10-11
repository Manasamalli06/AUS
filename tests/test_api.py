from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SAMPLE_DIR = Path(__file__).resolve().parent / "sample_data"


def test_health_check():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "Shapefile (.zip)" in data["supported_formats"]


def test_upload_kml_file():
    kml_path = SAMPLE_DIR / "survey.kml"
    assert kml_path.exists(), "Sample KML file missing"

    with open(kml_path, "rb") as f:
        response = client.post(
            "/api/files/",
            files={"file": ("survey.kml", f, "application/vnd.google-earth.kml+xml")},
        )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["filename"] == "survey.kml"
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 3  # 1 Polygon, 1 LineString, 1 Point
    assert "EPSG:4326" in data["crs"]

    file_id = data["id"]

    # Verify GET /api/files/{id}/
    info_res = client.get(f"/api/files/{file_id}/")
    assert info_res.status_code == 200
    info_data = info_res.json()
    assert info_data["id"] == file_id
    assert info_data["filename"] == "survey.kml"
    assert info_data["feature_count"] == 3
    assert info_data["status"] == "COMPLETED"

    # Verify GET /api/files/{id}/measurements/
    meas_res = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_res.status_code == 200
    meas_data = meas_res.json()
    assert meas_data["id"] == file_id
    assert len(meas_data["measurements"]) == 3

    # Check Polygon measurement
    poly_item = next(m for m in meas_data["measurements"] if m["geometry_type"] == "Polygon")
    assert poly_item["measurement"]["type"] == "area"
    assert poly_item["measurement"]["value"] > 0
    assert poly_item["measurement"]["unit"] == "square_meters"

    # Check LineString measurement
    line_item = next(m for m in meas_data["measurements"] if m["geometry_type"] == "LineString")
    assert line_item["measurement"]["type"] == "length"
    assert line_item["measurement"]["value"] > 0
    assert line_item["measurement"]["unit"] == "meters"

    # Check Point measurement
    point_item = next(m for m in meas_data["measurements"] if m["geometry_type"] == "Point")
    assert point_item["measurement"]["value"] is None
    assert point_item["measurement"]["status"] == "not_applicable"

    # Verify GET /api/files/{id}/features/ (GeoJSON)
    features_res = client.get(f"/api/files/{file_id}/features/")
    assert features_res.status_code == 200
    geojson_data = features_res.json()
    assert geojson_data["type"] == "FeatureCollection"
    assert len(geojson_data["features"]) == 3


def test_upload_shapefile_zip():
    shp_path = SAMPLE_DIR / "parcels.zip"
    assert shp_path.exists(), "Sample Parcels ZIP missing"

    with open(shp_path, "rb") as f:
        response = client.post(
            "/api/files/",
            files={"file": ("parcels.zip", f, "application/zip")},
        )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["filename"] == "parcels.zip"
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 3

    file_id = data["id"]

    # Verify measurements
    meas_res = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_res.status_code == 200
    meas_data = meas_res.json()
    assert meas_data["summary"]["polygon_count"] == 3
    assert meas_data["summary"]["total_area_sq_meters"] > 0


def test_upload_invalid_file_extension():
    response = client.post(
        "/api/files/",
        files={"file": ("document.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


def test_get_nonexistent_file():
    response = client.get("/api/files/nonexistent_id/")
    assert response.status_code == 404


def test_delete_file():
    # Upload temporary file first
    kml_path = SAMPLE_DIR / "survey.kml"
    with open(kml_path, "rb") as f:
        upload_res = client.post(
            "/api/files/",
            files={"file": ("survey_to_delete.kml", f, "application/vnd.google-earth.kml+xml")},
        )
    file_id = upload_res.json()["id"]

    # Delete it
    del_res = client.delete(f"/api/files/{file_id}/")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # Ensure it's now 404
    get_res = client.get(f"/api/files/{file_id}/")
    assert get_res.status_code == 404
