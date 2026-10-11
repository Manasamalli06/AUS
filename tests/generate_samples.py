import os
import shutil
import tempfile
import zipfile
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon

SAMPLE_DIR = Path(__file__).resolve().parent / "sample_data"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)


def create_sample_kml(output_path: Path):
    """Creates a sample KML file with Polygon, LineString, and Point in WGS84."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Survey Area Sample</name>
    <description>Sample geospatial survey containing Polygons, LineStrings, and Points.</description>
    
    <!-- Polygon: Farm Parcel (around Bangalore, India: 12.97 N, 77.59 E) -->
    <Placemark>
      <name>Agricultural Field 101</name>
      <description>Rice cultivation parcel</description>
      <Polygon>
        <extrude>1</extrude>
        <altitudeMode>clampToGround</altitudeMode>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5900,12.9700,0
              77.5950,12.9700,0
              77.5950,12.9750,0
              77.5900,12.9750,0
              77.5900,12.9700,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>

    <!-- LineString: Access Road (around Bangalore) -->
    <Placemark>
      <name>Survey Access Road</name>
      <description>Secondary access corridor</description>
      <LineString>
        <extrude>1</extrude>
        <tessellate>1</tessellate>
        <coordinates>
          77.5900,12.9700,0
          77.5925,12.9725,0
          77.5960,12.9730,0
          77.6000,12.9750,0
        </coordinates>
      </LineString>
    </Placemark>

    <!-- Point: Monitoring Station (around Bangalore) -->
    <Placemark>
      <name>Station Alpha</name>
      <description>Weather and IoT monitoring beacon</description>
      <Point>
        <coordinates>77.5930,12.9720,0</coordinates>
      </Point>
    </Placemark>

  </Document>
</kml>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(kml_content)
    print(f"Created sample KML at: {output_path}")


def create_sample_shapefile_zip(output_path: Path):
    """Creates a sample zipped Shapefile (.zip) containing .shp, .shx, .dbf, .prj."""
    temp_dir = Path(tempfile.mkdtemp(prefix="aus_shp_gen_"))
    try:
        # Create a sample GeoDataFrame with Polygon, LineString, and Point (or separate polygon & linestring shapefiles)
        # Note: Shapefiles traditionally hold one geometry type per layer. Let's create a polygon parcel shapefile.
        data = {
            "name": ["Plot Alpha", "Plot Beta", "Green Park"],
            "category": ["Commercial", "Residential", "Recreational"],
            "zoning_id": [101, 102, 103],
            "geometry": [
                # New York Central Park region (around -73.966, 40.781)
                Polygon([
                    (-73.970, 40.780),
                    (-73.960, 40.780),
                    (-73.960, 40.790),
                    (-73.970, 40.790),
                    (-73.970, 40.780),
                ]),
                Polygon([
                    (-73.960, 40.780),
                    (-73.950, 40.780),
                    (-73.950, 40.790),
                    (-73.960, 40.790),
                    (-73.960, 40.780),
                ]),
                Polygon([
                    (-73.970, 40.770),
                    (-73.950, 40.770),
                    (-73.950, 40.780),
                    (-73.970, 40.780),
                    (-73.970, 40.770),
                ]),
            ],
        }

        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        shp_file = temp_dir / "parcels.shp"
        gdf.to_file(shp_file, driver="ESRI Shapefile")

        # Create zip archive containing all generated shapefile components (.shp, .shx, .dbf, .prj)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file in temp_dir.glob("parcels.*"):
                zipf.write(file, arcname=file.name)

        print(f"Created sample Shapefile zip at: {output_path}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def create_sample_lines_shapefile_zip(output_path: Path):
    """Creates a sample LineString Shapefile zip."""
    temp_dir = Path(tempfile.mkdtemp(prefix="aus_shp_lines_"))
    try:
        data = {
            "route_name": ["Route 101", "Express Highway", "River Trail"],
            "speed_limit": [60, 100, 20],
            "geometry": [
                LineString([(-73.98, 40.75), (-73.97, 40.76), (-73.96, 40.78)]),
                LineString([(-73.95, 40.74), (-73.94, 40.76), (-73.93, 40.79)]),
                LineString([(-73.99, 40.76), (-73.98, 40.77), (-73.97, 40.79)]),
            ],
        }

        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        shp_file = temp_dir / "routes.shp"
        gdf.to_file(shp_file, driver="ESRI Shapefile")

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file in temp_dir.glob("routes.*"):
                zipf.write(file, arcname=file.name)

        print(f"Created sample Routes LineString zip at: {output_path}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    kml_file = SAMPLE_DIR / "survey.kml"
    shp_zip = SAMPLE_DIR / "parcels.zip"
    lines_zip = SAMPLE_DIR / "routes.zip"

    create_sample_kml(kml_file)
    create_sample_shapefile_zip(shp_zip)
    create_sample_lines_shapefile_zip(lines_zip)
