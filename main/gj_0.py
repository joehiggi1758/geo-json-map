import geopandas as gpd
from shapely.geometry import shape
import json


# File paths
counties_file = "../data/input/counties_0.geojson"
zip_codes_file = "../data/input/zip_codes_0.geojson"
output_file = "../data/input/joined_counties_zip_codes.geojson"


def load_and_repair_geojson(filepath):
    """Load GeoJSON and repair invalid geometries."""
    with open(filepath, "r") as f:
        data = json.load(f)
    features = data["features"]
    repaired_features = []
    for feature in features:
        try:
            geom = shape(feature["geometry"])
            if not geom.is_valid:
                geom = geom.buffer(0)  # Repair invalid geometry
            feature["geometry"] = geom.__geo_interface__
            repaired_features.append(feature)
        except Exception as e:
            print(f"Error processing feature: {e}")
    data["features"] = repaired_features
    return gpd.GeoDataFrame.from_features(data["features"])


# Load and repair GeoJSON files
counties = load_and_repair_geojson(counties_file)
zip_codes = load_and_repair_geojson(zip_codes_file)

# Ensure CRS consistency
if counties.crs != zip_codes.crs:
    zip_codes = zip_codes.to_crs(counties.crs)

# Perform spatial join
joined_data = gpd.sjoin(counties, zip_codes, how="inner", predicate="intersects")

# Select relevant columns to include in the output
columns_to_keep = [
    "COUNTYFP",  # County FIPS code
    "STATEFP",  # State FIPS code
    "ZIPCODE",  # ZIP code
    "TYPE",  # ZIP code type
    "geometry",  # Geometry for spatial representation
]
columns_to_keep = [col for col in columns_to_keep if col in joined_data.columns]
joined_data = joined_data[columns_to_keep]

# Save the resulting GeoDataFrame to a file
joined_data.to_file(output_file, driver="GeoJSON")

# Display a sample of the data
print(joined_data.head())
