# Import statements
import matplotlib.pyplot as plt
import geopandas as gpd
import streamlit as st
import pandas as pd
import folium
import random
import json
import io
import os

# From statements
from streamlit_folium import st_folium
from sqlalchemy import create_engine
from shapely.geometry import shape
from datetime import datetime
from folium import plugins
from fpdf import FPDF

#########################
# Configuration & Setup
#########################
st.set_page_config(page_title="Redistricting Portal", layout="wide")

PRIMARY_COLOR = "#B58264"
HIGHLIGHT_COLOR = "#3A052E"
VERSION_FOLDER = "data/output/"
GEOJSON_FILE = "data/input/counties_0.geojson"
STATE_CODE_FILE = "data/input/state_code_to_name_0.json"

os.makedirs(VERSION_FOLDER, exist_ok=True)

#########################
# Helper Functions
#########################
@st.cache_data
def load_state_codes(path):
    with open(path, "r") as file:
        return json.load(file)

@st.cache_data
def load_geojson(file_path):
    gdf = gpd.read_file(file_path)
    if "color" not in gdf.columns:
        gdf["color"] = PRIMARY_COLOR
    else:
        gdf["color"] = gdf["color"].fillna(PRIMARY_COLOR)
    if "STATEFP" in gdf.columns:
        gdf["STATEFP"] = gdf["STATEFP"].astype(str).str.zfill(2)
    return gdf

def compute_union_all(geometry_series):
    return geometry_series.unary_union  # modern usage for union_all

def get_random_color():
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))

def style_function(feature):
    cty_name = feature["properties"].get("NAME", "")
    if cty_name == selected_county:
        return {
            "fillColor": HIGHLIGHT_COLOR,
            "color": HIGHLIGHT_COLOR,
            "weight": 2,
            "fillOpacity": 0.6,
        }
    color = feature["properties"].get("color", PRIMARY_COLOR)
    return {"fillColor": color, "color": color, "weight": 1, "fillOpacity": 0.4}

def style_function_version(feature):
    district_color = feature["properties"].get("color", PRIMARY_COLOR)
    return {
        "fillColor": district_color,
        "color": district_color,
        "weight": 1,
        "fillOpacity": 0.6 if district_color != PRIMARY_COLOR else 0.4,
    }

def generate_map_snapshot(gdf, title="Proposed Districts"):
    if gdf.empty:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, "No geometry to display", ha="center", va="center")
        ax.axis("off")
    else:
        fig, ax = plt.subplots(figsize=(8, 6))
        gdf.plot(ax=ax, edgecolor="black", color=gdf["color"], alpha=0.6)
        ax.set_title(title)
        ax.axis("off")
        ax.set_aspect("equal")
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf

def generate_pdf(map_png, version_name, highlights):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Territory Plan", ln=True, align="C")

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Version: {version_name}", ln=True)

    if map_png:
        temp_file = "temp_map_snapshot.png"
        try:
            with open(temp_file, "wb") as temp_img:
                temp_img.write(map_png.getbuffer())

            page_width = 297  
            margin = 10
            map_width = int(page_width * 0.7) - (2 * margin)
            comments_width = int(page_width * 0.3) - margin

            map_x = margin
            map_y = pdf.get_y()
            pdf.image(temp_file, x=map_x, y=map_y, w=map_width)

            pdf.set_xy(map_x + map_width + margin, map_y)
            pdf.set_font("Arial", "I", 10)
            pdf.multi_cell(comments_width, 10, f"Comments: {highlights}")
        finally:
            try:
                os.remove(temp_file)
            except FileNotFoundError:
                pass

        pdf_buffer = io.BytesIO(pdf.output(dest="S").encode("latin-1"))
        return pdf_buffer
    return None

def list_saved_versions(folder_path):
    if not os.path.exists(folder_path):
        return []
    geojson_files = [f for f in os.listdir(folder_path) if f.endswith(".geojson")]

    def extract_timestamp(filename):
        try:
            base = os.path.splitext(filename)[0]
            parts = base.split("_")
            if len(parts) >= 2:
                date_part = parts[-2]
                time_part = parts[-1]
                return datetime.strptime(f"{date_part}_{time_part}", "%Y%m%d_%H%M%S")
            return datetime.min
        except:
            return datetime.min

    return sorted(geojson_files, key=extract_timestamp, reverse=True)

######################################
# Write final_gdf to PostgreSQL
######################################
def get_engine():
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    db_user = os.environ.get("POSTGRES_USER", "myuser")
    db_pass = os.environ.get("POSTGRES_PASSWORD", "mypassword")
    db_name = os.environ.get("POSTGRES_DB", "mydb")

    connection_string = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    return create_engine(connection_string)

# Then wherever you need to write final_gdf:
def write_to_postgres(final_gdf, table_name="final_districts"):
    engine = get_engine()
    # Make sure final_gdf is in EPSG:4326 or whatever your DB uses
    if final_gdf.crs and final_gdf.crs.to_epsg() != 4326:
        final_gdf = final_gdf.to_crs(epsg=4326)

    final_gdf.to_postgis(name=table_name, con=engine, if_exists="append", index=False)


# -------------------------------------------------------------------
# Placeholder Functions for Database and ODM API
# -------------------------------------------------------------------

# Placeholder for Database Connection (Commented Out)
# def get_db_connection():
#     """Return a DB connection object."""
#     # Replace with your actual database connection code
#     return None

# Placeholder for Inserting into Staging Table (Commented Out)
# def insert_into_staging_table(df):
#     """Insert rows from a dataframe into the staging table."""
#     pass


# Placeholder for Getting Sales Info (Commented Out)
def get_sales_info():
    """Stub function to return sales information."""
    # Replace with actual data retrieval logic
    return pd.DataFrame(
        {
            "NAME": [],  # County names
            "STATEFP": [],  # State FIPS codes
            "SalesRep": [],
            "Product": [],
        }
    )


# Placeholder for ODM API Auditing (Commented Out)
# def audit_to_odm_api(district_data):
#     """Placeholder for ODM API auditing."""
#     pass

# -------------------------------------------------------------------
# Main Script
# -------------------------------------------------------------------
full_gdf = load_geojson(GEOJSON_FILE)
STATE_CODE_TO_NAME = load_state_codes(STATE_CODE_FILE)

if "pending_polygons" not in st.session_state:
    st.session_state["pending_polygons"] = []
if "selected_version" not in st.session_state:
    st.session_state["selected_version"] = None
if "last_polygon" not in st.session_state:
    st.session_state["last_polygon"] = None

st.title("Interactive Redistricting Portal")

# -------------------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------------------
st.sidebar.header("Select a State")
if "STATEFP" not in full_gdf.columns:
    st.error("No 'STATEFP' column in GeoJSON.")
    st.stop()

states_in_data = sorted(set(full_gdf["STATEFP"].unique()) & set(STATE_CODE_TO_NAME.keys()))
if "All" not in states_in_data:
    states_in_data.insert(0, "All")

selected_code = st.sidebar.selectbox(
    "Choose State:",
    states_in_data,
    format_func=lambda c: STATE_CODE_TO_NAME.get(c, f"Unknown ({c})"),
)

if selected_code == "All":
    filtered_gdf = full_gdf
else:
    filtered_gdf = full_gdf[full_gdf["STATEFP"] == selected_code]

combined_geom = compute_union_all(filtered_gdf.geometry) if not filtered_gdf.empty else None
state_centroid = combined_geom.centroid if combined_geom else None

st.sidebar.header("Select a County")
if "NAME" not in filtered_gdf.columns:
    st.error("No 'NAME' column in GeoJSON.")
    st.stop()

county_names = sorted(filtered_gdf["NAME"].unique())
selected_county = st.sidebar.selectbox("Choose a county:", county_names)

# -------------------------------------------------------------------
# TABS
# -------------------------------------------------------------------
tab_main, tab_versions, tab_upload = st.tabs(["Main", "Versions", "Upload"])

# -------------------- TAB: MAIN MAP --------------------
with tab_main:
    st.subheader("Current County Map")

    # Determine map center and zoom level
    if selected_code == "All" or state_centroid is None:
        map_location = [39.833, -98.5795]  # Center of the contiguous US
        map_zoom = 4
    else:
        map_location = [state_centroid.y, state_centroid.x]
        map_zoom = 6

    # Load sales data for tooltips
    sales_df = get_sales_info()

    if not sales_df.empty:
        # Ensure STATEFP values are strings for consistency
        filtered_gdf['STATEFP'] = filtered_gdf['STATEFP'].astype(str)
        sales_df['STATEFP'] = sales_df['STATEFP'].astype(str)

        # Merge sales data with GeoDataFrame
        merged_df = pd.merge(
            filtered_gdf,
            sales_df.rename(columns={"CountyName": "NAME", "StateFIPS": "STATEFP"}),
            on=["NAME", "STATEFP"],
            how="outer",  # Retain all rows
            indicator=True
        )

        # Concatenate STATEFP values as a list per geometry
        merged_df = (
            merged_df.groupby("geometry", as_index=False)
            .agg({
                "STATEFP": lambda x: list(filter(None, set(x))),  # Keep all unique STATEFPs as a list
                "NAME": "first",
                "SalesRep": "first",
                "Product": "first",
                "color": "first",
                "geometry": "first",
            })
        )

        # Convert to GeoDataFrame
        final_gdf = gpd.GeoDataFrame(merged_df, geometry="geometry", crs=filtered_gdf.crs)

        # Option 3 fallback snippet
        if 'SalesRep' not in final_gdf.columns:
            final_gdf['SalesRep'] = None
        if 'Product' not in final_gdf.columns:
            final_gdf['Product'] = None

    else:
        # Handle the case with no sales data
        final_gdf = filtered_gdf.copy()
        final_gdf['SalesRep'] = None
        final_gdf['Product'] = None
        final_gdf['color'] = final_gdf['color'].fillna(PRIMARY_COLOR)

        # Concatenate STATEFP values as a list per geometry
        final_gdf = (
            final_gdf.groupby("geometry", as_index=False)
            .agg({
                "STATEFP": lambda x: list(filter(None, set(x))),  # Keep all unique STATEFPs as a list
                "NAME": "first",
                "SalesRep": "first",
                "Product": "first",
                "color": "first",
                "geometry": "first",
            })
        )

        # Convert to GeoDataFrame
        final_gdf = gpd.GeoDataFrame(final_gdf, geometry="geometry", crs=filtered_gdf.crs)

    # Convert STATEFP list back to strings for final output if needed
    final_gdf['STATEFP'] = final_gdf['STATEFP'].apply(lambda x: ', '.join(x) if isinstance(x, list) else x)

    # Create Folium map with light base tiles
    m = folium.Map(
        location=map_location,
        zoom_start=map_zoom,
        width="100%",
        height="600",
        tiles="OpenStreetMap",  # Use a light-colored base map to ensure visibility
    )

    # Add GeoJSON layer
    folium.GeoJson(
        final_gdf.__geo_interface__,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=["NAME", "SalesRep", "Product"],
            aliases=["County:", "Sales Rep:", "Product:"],
        ),
    ).add_to(m)

    # Initialize Draw plugin without export
    draw_control = plugins.Draw(
        export=False,  # Removed 'Export' link
        edit_options={"edit": True, "remove": True},
        draw_options={
            "polygon": True,
            "polyline": False,
            "rectangle": False,
            "circle": False,
            "circlemarker": False,
            "marker": False,
        },
    )
    m.add_child(draw_control)

    # Render the Folium map
    map_result = st_folium(m, width="100%", height=600)

    # Capture new polygons drawn by the user
    if map_result and "last_active_drawing" in map_result:
        new_drawing = map_result["last_active_drawing"]
        if new_drawing and (new_drawing != st.session_state.get("last_polygon")):
            st.session_state["last_polygon"] = new_drawing
            geom_type = new_drawing.get("type")
            geom_data = new_drawing.get("geometry")

            if geom_type == "Feature" and geom_data:
                drawn_shape = shape(geom_data)
                if drawn_shape.geom_type in ["Polygon", "MultiPolygon"]:
                    # Assign a random color to the new polygon
                    random_color = get_random_color()
                    st.session_state["pending_polygons"].append(
                        (drawn_shape, random_color)
                    )
                    st.success(
                        f"Added new Territory ({drawn_shape.geom_type}) with color {random_color}."
                    )
                else:
                    st.error(
                        f"You drew a {drawn_shape.geom_type}. Only polygons are accepted!"
                    )
            else:
                st.error("No valid geometry found in the drawn feature.")

    # Display number of pending polygons
    num_pending = len(st.session_state.get("pending_polygons", []))

    st.write(f"**Updated Districts:** {num_pending}")

    # Input for version name
    version_name = st.text_input("Enter version name (e.g., 'Draft 1'):")

    # Button to save proposed districts
    if st.button("Save Proposed Territories"):
        if num_pending == 0:
            st.error("No polygons drawn to save!")
        elif not version_name.strip():
            st.error("Please enter a version name before saving.")
        else:
            # 1) Start with your base final_gdf (e.g., a copy of 'filtered_gdf')
            #    This is wherever you want to accumulate the final version.
            final_gdf = filtered_gdf.copy()

            # 2) Keep track locally of which states truly have newly drawn polygons
            updated_states_local = set()

            # 3) Merge newly drawn polygons
            for poly, color in st.session_state["pending_polygons"]:
                statefp_value = selected_code if selected_code != "All" else None
                # Collect only actual updated states in a local set
                if statefp_value:
                    updated_states_local.add(statefp_value)

                name_value = f"{selected_county} (Proposed)"
                new_row = gpd.GeoDataFrame(
                    {
                        "STATEFP": [statefp_value],
                        "NAME": [name_value],
                        "color": [color],
                        "geometry": [poly],
                    },
                    crs=final_gdf.crs,
                )
                final_gdf = pd.concat([final_gdf, new_row], ignore_index=True)

            # Clear pending polygons
            st.session_state["pending_polygons"].clear()
            st.success("Pending polygons have been merged into the dataset.")

            # 4) Only append all counties for states that *actually* got updated polygons
            if updated_states_local:
                updated_states_gdf = full_gdf[full_gdf["STATEFP"].isin(updated_states_local)]
                final_gdf = pd.concat([final_gdf, updated_states_gdf]).drop_duplicates(
                    subset=["STATEFP", "NAME", "geometry"]
                ).reset_index(drop=True)

                # Color only the *original* (non-proposed) counties in these updated states
                mask_updated = final_gdf["STATEFP"].isin(updated_states_local)
                mask_proposed = final_gdf["NAME"].astype(str).str.endswith("(Proposed)")
                final_gdf.loc[mask_updated & ~mask_proposed, "color"] = PRIMARY_COLOR

            # 5) Generate timestamp & version file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            sanitized_version_name = "".join(
                c for c in version_name if c.isalnum() or c in (" ", "_", "-")
            ).rstrip()
            version_file = os.path.join(
                VERSION_FOLDER, f"{sanitized_version_name}_{timestamp}.geojson"
            )

            # 6) Save final_gdf to GeoJSON
            try:
                final_gdf.to_file(version_file, driver="GeoJSON")
                st.success(f"Proposed district saved as `{version_file}`")
            except Exception as e:
                st.error(f"Error saving GeoJSON: {e}")
                st.stop()

            # 7) Update selected_version for the Versions tab
            st.session_state["selected_version"] = os.path.basename(version_file)
            st.info("Version saved successfully! Please navigate to the 'Versions' tab to view it.")


# ------------------ TAB: SAVED VERSION SNAPSHOT --------------------
with tab_versions:
    st.header("Saved Versions")

    # List saved versions
    saved_versions = list_saved_versions(VERSION_FOLDER)
    if not saved_versions:
        st.info("No saved versions available.")
    else:
        # Dropdown to select a saved version
        selected_version = st.selectbox(
            "Choose a saved version to view:", saved_versions
        )

        if selected_version:
            version_path = os.path.join(VERSION_FOLDER, selected_version)
            if os.path.exists(version_path):
                version_gdf = load_geojson(version_path)
                st.subheader(f"Map for `{selected_version}`")

                if not version_gdf.empty:
                    # Ensure all districts have a 'color' field
                    version_gdf["color"] = version_gdf["color"].fillna(PRIMARY_COLOR)

                    # Compute the centroid for map centering
                    combined_geom = compute_union_all(version_gdf.geometry)
                    if not combined_geom.is_empty:
                        version_centroid = combined_geom.centroid
                        map_location = [version_centroid.y, version_centroid.x]
                        map_zoom = 6
                    else:
                        map_location = [39.833, -98.5795]  # Center of the contiguous US
                        map_zoom = 4

                    # Create Folium map with light base tiles
                    m_version = folium.Map(
                        location=map_location,
                        zoom_start=map_zoom,
                        width="100%",
                        height="600",
                        tiles="OpenStreetMap",
                    )

                    # Add GeoJSON layer with the updated style function
                    folium.GeoJson(
                        version_gdf.__geo_interface__,
                        style_function=style_function_version,
                        tooltip=folium.GeoJsonTooltip(
                            fields=["NAME", "SalesRep", "Product"],
                            aliases=["County:", "Sales Rep:", "Product:"],
                        ),
                    ).add_to(m_version)

                    # Render the map
                    st_folium(m_version, width="100%", height=600)

                    # ---------------- Export PDF Section ----------------
                    st.markdown("### Export PDF")
                    pdf_highlights = st.text_area(
                        "Key highlights or comments for this version:"
                    )

                    # Single "Export PDF" button using download_button
                    pdf_data = generate_pdf(
                        generate_map_snapshot(version_gdf, title=f""),
                        selected_version,
                        pdf_highlights,
                    )

                    if pdf_data:
                        st.download_button(
                            label="Export PDF",
                            data=pdf_data,
                            file_name=f"redistricting_report_{selected_version}.pdf",
                            mime="application/pdf",
                        )
                        st.success("PDF report generated and download is ready.")
                    else:
                        st.error("Failed to generate PDF.")

                else:
                    st.error(f"No geometry found in `{selected_version}`.")
            else:
                st.error(f"Version file `{selected_version}` not found.")

# ----------------------- TAB: UPLOAD DATA --------------------------
with tab_upload:
    st.header("Upload Proposed Changes")
    st.write(
        """
        Upload an Excel or CSV with columns:
        - CountyName
        - StateFIPS
        - SalesRep
        - Product
        """
    )

    uploaded_file = st.file_uploader("Upload Proposed Changes (CSV or XLSX)")
    if uploaded_file:
        fname_lower = uploaded_file.name.lower()
        if fname_lower.endswith(".csv"):
            try:
                df_uploaded = pd.read_csv(uploaded_file)
                st.success(
                    f"Loaded {len(df_uploaded)} rows from `{uploaded_file.name}`."
                )
            except Exception as e:
                st.error(f"Error reading CSV file: {e}")
                df_uploaded = None
        elif fname_lower.endswith(".xlsx"):
            try:
                df_uploaded = pd.read_excel(uploaded_file)
                st.success(
                    f"Loaded {len(df_uploaded)} rows from `{uploaded_file.name}`."
                )
            except Exception as e:
                st.error(f"Error reading Excel file: {e}")
                df_uploaded = None
        else:
            st.error("Unsupported file type. Please upload a CSV or XLSX file.")
            df_uploaded = None

        if "df_uploaded" in locals() and df_uploaded is not None:
            # Placeholder for inserting into staging table
            # Uncomment and implement when database connection is set up
            # insert_into_staging_table(df_uploaded)
            st.info("Uploaded data is ready for processing.")
            # For now, we'll just display the uploaded data
            st.dataframe(df_uploaded)