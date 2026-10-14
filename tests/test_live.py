import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000")

# 1. Health
r1 = client.get("/api/health")
print("1. Health check:", r1.status_code, r1.json())

# 2. Upload KML
with open("tests/sample_data/survey.kml", "rb") as f:
    r2 = client.post("/api/files/", files={"file": ("survey.kml", f, "application/vnd.google-earth.kml+xml")})
print("2. Upload KML:", r2.status_code, r2.json())
kml_id = r2.json()["id"]

# 3. File Info
r3 = client.get(f"/api/files/{kml_id}/")
print("3. File Info:", r3.status_code, r3.json())

# 4. Measurements
r4 = client.get(f"/api/files/{kml_id}/measurements/")
meas_data = r4.json()
print("4. Measurements summary:", r4.status_code, meas_data["summary"])
for m in meas_data["measurements"]:
    disp = m["measurement"]["formatted"] or m["measurement"]["note"]
    crs = m["measurement"]["projected_crs"]
    print(f"   - Feature {m['feature_id']} ({m['geometry_type']}): {disp} [Projection: {crs}]")

# 5. Upload Shapefile Zip
with open("tests/sample_data/parcels.zip", "rb") as f:
    r5 = client.post("/api/files/", files={"file": ("parcels.zip", f, "application/zip")})
print("5. Upload Shapefile ZIP:", r5.status_code, r5.json())
shp_id = r5.json()["id"]

# 6. Shapefile Measurements
r6 = client.get(f"/api/files/{shp_id}/measurements/")
shp_meas = r6.json()
print("6. Shapefile measurements summary:", r6.status_code, shp_meas["summary"])
for m in shp_meas["measurements"]:
    disp = m["measurement"]["formatted"]
    crs = m["measurement"]["projected_crs"]
    print(f"   - Parcel {m['properties'].get('name')} ({m['geometry_type']}): {disp} [Projection: {crs}]")
