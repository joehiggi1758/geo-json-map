# -------------------------------------------------------------------
# Import statements
# -------------------------------------------------------------------
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

# -------------------------------------------------------------------
# Configuration & Basic Setup
# -------------------------------------------------------------------
st.set_page_config(page_title="Redistricting Portal", layout="wide")

PRIMARY_COLOR = "#B58264"
HIGHLIGHT_COLOR = "#3A052E"
VERSION_FOLDER = "data/output/"
GEOJSON_FILE = "data/input/counties_0.geojson"
STATE_CODE_FILE = "data/input/state_code_to_name_0.json"

os.makedirs(VERSION_FOLDER, exist_ok=True)

# -------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------
@st.cache_data
def load_state_codes(path):
    with open(path, "r") as file:
        return json.load(file)

def compute_union_all(geometry_series):
    """
    Use shapely's union_all() to compute the union of geometries.
    This is more efficient than iterating union step by step.
    """
    return geometry_series.union_all()

@st.cache_data
def load_geojson(file_path):
    """
    Load GeoJSON into a GeoDataFrame and ensure consistent coloring.
    - If 'color' is missing or null, assign PRIMARY_COLOR.
    - Ensure 'STATEFP' is zero-padded (2 digits).
    """
    try:
        gdf = gpd.read_file(file_path)
        if "color" not in gdf.columns:
            gdf["color"] = PRIMARY_COLOR
        else:
            gdf["color"] = gdf["color"].fillna(PRIMARY_COLOR)

        if "STATEFP" in gdf.columns:
            gdf["STATEFP"] = gdf["STATEFP"].astype(str).str.zfill(2)
        return gdf

    except FileNotFoundError:
        st.error("GeoJSON file not found. Check the path.")
        return gpd.GeoDataFrame({"geometry": []})

    except Exception as e:
        st.error(f"Error loading GeoJSON: {e}")
        return gpd.GeoDataFrame({"geometry": []})

def save_geojson(data, file_path):
    """
    Save a GeoDataFrame as GeoJSON, with robust error handling.
    """
    try:
        data.to_file(file_path, driver="GeoJSON")
        st.success(f"Saved version to `{file_path}`")
    except Exception as e:
        st.error(f"Error saving GeoJSON: {e}")

def list_saved_versions(folder_path):
    """
    List .geojson version files sorted by timestamp descending (most recent first).
    Uses a simple pattern: 'someName_YYYYMMDD_HHMMSS.geojson'.
    """
    if not os.path.exists(folder_path):
        return []

    geojson_files = [f for f in os.listdir(folder_path) if f.endswith(".geojson")]

    def extract_timestamp(filename):
        try:
            base = os.path.splitext(filename)[0]
            parts = base.split("_")
            if len(parts) >= 2:
                date_part = parts[-2]  # e.g. '20230412'
                time_part = parts[-1]  # e.g. '153000'
                timestamp_str = f"{date_part}_{time_part}"
                return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            else:
                return datetime.min
        except:
            return datetime.min

    return sorted(geojson_files, key=extract_timestamp, reverse=True)

def generate_map_snapshot(gdf, title="Proposed Districts Snapshot"):
    """
    Generate a PNG snapshot of a GeoDataFrame with matplotlib.
    Return an in-memory buffer for further usage (e.g., embedding in PDF).
    """
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
    """
    Create an in-memory PDF with the provided map snapshot, version text, etc.
    """
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

def get_random_color():
    """
    Generate a random hex color for proposed polygons.
    """
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

# -------------------------------------------------------------------
# Placeholder / Stub for additional Data/DB logic
# -------------------------------------------------------------------
@st.cache_data
def get_sales_info():
    """Return sales info in a DataFrame, used for optional merging with counties."""
    return pd.DataFrame({
        "NAME": [],
        "STATEFP": [],
        "SalesRep": [],
        "Product": [],
    })

# -------------------------------------------------------------------
# IBM ODM or Align Star Integration
# (Comment out the relevant code blocks if not in use)
# -------------------------------------------------------------------
# def call_ibm_odm_api(final_gdf):
#     # IBM ODM code here
#     # e.g., send final_gdf as JSON to an ODM endpoint
#     pass

# def align_star_export(final_gdf):
#     # Align Star code or export logic
#     # e.g., produce a specialized file format for Align Star
#     pass

# -------------------------------------------------------------------
# Optional: Write final_gdf to PostgreSQL in Docker
# -------------------------------------------------------------------
# from sqlalchemy import create_engine

# def write_to_postgres(final_gdf, table_name="final_districts"):
#     """
#     Example usage of SQLAlchemy to insert final_gdf into a PostGIS-enabled PostgreSQL DB.
#     Docker container must be running with port exposed.
#     """
#     # connection_string = "postgresql://user:password@localhost:5432/mydb"
#     # engine = create_engine(connection_string)
#     # if final_gdf.crs and final_gdf.crs.to_epsg() != 4326:
#     #     final_gdf = final_gdf.to_crs(epsg=4326)
#     # final_gdf.to_postgis(table_name, engine, if_exists="append", index=False)
#     pass

# -------------------------------------------------------------------
# Main Script
# -------------------------------------------------------------------
full_gdf = load_geojson(GEOJSON_FILE)
STATE_CODE_TO_NAME = load_state_codes(STATE_CODE_FILE)

# Initialize session states for polygons & versions
if "pending_polygons" not in st.session_state:
    st.session_state["pending_polygons"] = []
if "selected_version" not in st.session_state:
    st.session_state["selected_version"] = None
if "last_polygon" not in st.session_state:
    st.session_state["last_polygon"] = None

# Keep a list of visited states
if "updated_states_list" not in st.session_state:
    st.session_state["updated_states_list"] = []

# Track states that actually have newly proposed polygons
if "states_with_proposed" not in st.session_state:
    st.session_state["states_with_proposed"] = set()

# Title
st.title("Interactive Redistricting Portal")

# -------------------------------------------------------------------
# Sidebar
# -------------------------------------------------------------------
st.sidebar.header("Select a State")

if "STATEFP" not in full_gdf.columns:
    st.error("No 'STATEFP' column found in the GeoJSON.")
    st.stop()

states_in_data = sorted(set(full_gdf["STATEFP"].unique()) & set(STATE_CODE_TO_NAME.keys()))
if "All" not in states_in_data:
    states_in_data.insert(0, "All")

selected_code = st.sidebar.selectbox(
    "Choose State:",
    states_in_data,
    format_func=lambda c: STATE_CODE_TO_NAME.get(c, f"Unknown ({c})"),
)

# Populate visited states list
if selected_code not in st.session_state["updated_states_list"] and selected_code != "All":
    st.session_state["updated_states_list"].append(selected_code)

# Filter GDF for chosen state
if selected_code == "All":
    filtered_gdf = full_gdf
else:
    filtered_gdf = full_gdf[full_gdf["STATEFP"] == selected_code]

# Compute centroid
if not filtered_gdf.empty:
    combined_geom = compute_union_all(filtered_gdf.geometry)
    state_centroid = combined_geom.centroid
else:
    state_centroid = None

st.sidebar.header("Select a County")
if "NAME" not in filtered_gdf.columns:
    st.error("No 'NAME' column in the GeoJSON.")
    st.stop()

county_names = sorted(filtered_gdf["NAME"].unique())
selected_county = st.sidebar.selectbox("Choose a county:", county_names)

# -------------------------------------------------------------------
# Tabs
# -------------------------------------------------------------------
tab_main, tab_versions, tab_upload = st.tabs(["Main", "Versions", "Upload"])

# ===================== TAB: MAIN MAP =====================
with tab_main:
    st.subheader("Current County Map")

    if selected_code == "All" or state_centroid is None:
        map_location = [39.833, -98.5795]
        map_zoom = 4
    else:
        map_location = [state_centroid.y, state_centroid.x]
        map_zoom = 6

    # Load optional sales data
    sales_df = get_sales_info()

    # Merge if we have sales data
    if not sales_df.empty:
        filtered_gdf["STATEFP"] = filtered_gdf["STATEFP"].astype(str)
        sales_df["STATEFP"] = sales_df["STATEFP"].astype(str)

        merged_df = pd.merge(
            filtered_gdf,
            sales_df.rename(columns={"CountyName": "NAME", "StateFIPS": "STATEFP"}),
            on=["NAME", "STATEFP"],
            how="outer",
            indicator=True
        )
        # Group once to minimize duplicates
        merged_df = (
            merged_df.groupby("geometry", as_index=False)
            .agg({
                "STATEFP": lambda x: list(filter(None, set(x))),
                "NAME": "first",
                "SalesRep": "first",
                "Product": "first",
                "color": "first",
                "geometry": "first",
            })
        )
        final_gdf = gpd.GeoDataFrame(merged_df, geometry="geometry", crs=filtered_gdf.crs)
    else:
        # No sales data, proceed with filtered_gdf
        final_gdf = filtered_gdf.copy()
        final_gdf["SalesRep"] = None
        final_gdf["Product"] = None
        final_gdf["color"] = final_gdf["color"].fillna(PRIMARY_COLOR)

        # Group once to ensure uniqueness
        final_gdf = (
            final_gdf.groupby("geometry", as_index=False)
            .agg({
                "STATEFP": lambda x: list(filter(None, set(x))),
                "NAME": "first",
                "SalesRep": "first",
                "Product": "first",
                "color": "first",
                "geometry": "first",
            })
        )
        final_gdf = gpd.GeoDataFrame(final_gdf, geometry="geometry", crs=filtered_gdf.crs)

    # Ensure tooltip fields exist
    if "SalesRep" not in final_gdf.columns:
        final_gdf["SalesRep"] = None
    if "Product" not in final_gdf.columns:
        final_gdf["Product"] = None

    # Convert STATEFP list to a comma-separated string
    final_gdf["STATEFP"] = final_gdf["STATEFP"].apply(
        lambda x: ", ".join(x) if isinstance(x, list) else x
    )

    # Create Folium map
    m = folium.Map(
        location=map_location,
        zoom_start=map_zoom,
        width="100%",
        height="600",
        tiles="OpenStreetMap",
    )

    folium.GeoJson(
        final_gdf.__geo_interface__,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=["NAME", "SalesRep", "Product"],
            aliases=["County:", "Sales Rep:", "Product:"],
        ),
    ).add_to(m)

    draw_control = plugins.Draw(
        export=False,
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

    # Render map
    map_result = st_folium(m, width="100%", height=600)

    # Capture newly drawn polygons
    if map_result and "last_active_drawing" in map_result:
        new_drawing = map_result["last_active_drawing"]
        if new_drawing and (new_drawing != st.session_state.get("last_polygon")):
            st.session_state["last_polygon"] = new_drawing
            geom_type = new_drawing.get("type")
            geom_data = new_drawing.get("geometry")

            if geom_type == "Feature" and geom_data:
                drawn_shape = shape(geom_data)
                if drawn_shape.geom_type in ["Polygon", "MultiPolygon"]:
                    rand_color = get_random_color()
                    st.session_state["pending_polygons"].append((drawn_shape, rand_color))

                    # If user draws a polygon in a real state, track it
                    if selected_code != "All":
                        st.session_state["states_with_proposed"].add(selected_code)

                    st.success(f"Added new territory with color {rand_color}.")
                else:
                    st.error(f"Only polygons are accepted (you drew {drawn_shape.geom_type}).")
            else:
                st.error("No valid geometry found in the drawn feature.")

    num_pending = len(st.session_state["pending_polygons"])
    st.write(f"**Updated Districts:** {num_pending}")

    version_name = st.text_input("Enter version name (e.g., 'Draft 1'):")

    # ------------------ SAVE PROPOSED TERRITORIES ------------------
    if st.button("Save Proposed Territories"):
        if num_pending == 0:
            st.error("No polygons drawn to save!")
        elif not version_name.strip():
            st.error("Please enter a version name before saving.")
        else:
            # 1) Start with a copy of filtered_gdf
            final_gdf = filtered_gdf.copy()

            # 2) Append newly drawn polygons
            for poly, color in st.session_state["pending_polygons"]:
                
                # 3) If any states have proposed polygons, color their counties
                if st.session_state["states_with_proposed"]:
                    updated_states_gdf = full_gdf[
                        full_gdf["STATEFP"].isin(st.session_state["states_with_proposed"])
                    ]
                    final_gdf = pd.concat([final_gdf, updated_states_gdf]).drop_duplicates(
                        subset=["STATEFP", "NAME", "geometry"]
                    ).reset_index(drop=True)

                    # Color original counties in these states
                    mask_updated = final_gdf["STATEFP"].isin(st.session_state["states_with_proposed"])
                    mask_proposed = final_gdf["NAME"].str.endswith("(Proposed)")
                    final_gdf.loc[mask_updated & ~mask_proposed, "color"] = PRIMARY_COLOR
                
                statefp_val = selected_code if selected_code != "All" else None
                new_row = gpd.GeoDataFrame(
                    {
                        "STATEFP": [statefp_val],
                        "NAME": [f"{selected_county} (Proposed)"],
                        "color": [color],
                        "geometry": [poly],
                    },
                    crs=final_gdf.crs,
                )
                final_gdf = pd.concat([final_gdf, new_row], ignore_index=True)

            # Clear pending polygons to free memory
            st.session_state["pending_polygons"].clear()
            st.success("Pending polygons merged into dataset.")

            # 4) Generate version file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            sanitized_name = "".join(
                c for c in version_name if c.isalnum() or c in (" ", "_", "-")
            ).rstrip()
            version_file = os.path.join(VERSION_FOLDER, f"{sanitized_name}_{timestamp}.geojson")

            # 5) Save
            try:
                final_gdf.to_file(version_file, driver="GeoJSON")
                st.success(f"Proposed district saved as `{version_file}`")
            except Exception as e:
                st.error(f"Error saving GeoJSON: {e}")
                st.stop()

            st.session_state["selected_version"] = os.path.basename(version_file)
            st.info("Version saved. Navigate to 'Versions' tab to view.")

            # 6) Optional: IBM ODM or Align Star calls
            # call_ibm_odm_api(final_gdf)
            # align_star_export(final_gdf)

            # 7) Optional: Write to Postgres
            # write_to_postgres(final_gdf, table_name="final_districts")

# ===================== TAB: VERSIONS =====================
with tab_versions:
    st.header("Saved Versions")
    saved_versions = list_saved_versions(VERSION_FOLDER)
    if not saved_versions:
        st.info("No saved versions available.")
    else:
        selected_version = st.selectbox("Choose a saved version to view:", saved_versions)
        if selected_version:
            version_path = os.path.join(VERSION_FOLDER, selected_version)
            if os.path.exists(version_path):
                version_gdf = load_geojson(version_path)

                # Ensure columns for tooltip
                for col in ["SalesRep", "Product"]:
                    if col not in version_gdf.columns:
                        version_gdf[col] = None

                st.subheader(f"Map for `{selected_version}`")

                if not version_gdf.empty:
                    combined_geom = compute_union_all(version_gdf.geometry)
                    if not combined_geom.is_empty:
                        version_centroid = combined_geom.centroid
                        map_location = [version_centroid.y, version_centroid.x]
                        map_zoom = 6
                    else:
                        map_location, map_zoom = [39.833, -98.5795], 4

                    m_version = folium.Map(
                        location=map_location,
                        zoom_start=map_zoom,
                        width="100%",
                        height="600",
                        tiles="OpenStreetMap",
                    )

                    folium.GeoJson(
                        version_gdf.__geo_interface__,
                        style_function=style_function_version,
                        tooltip=folium.GeoJsonTooltip(
                            fields=["NAME", "SalesRep", "Product"],
                            aliases=["County:", "Sales Rep:", "Product:"],
                        ),
                    ).add_to(m_version)

                    st_folium(m_version, width="100%", height=600)

                    # -----------------------------------
                    # PDF Highlights / Comments Section
                    # -----------------------------------
                    st.markdown("### Export PDF")

                    # 1) Initialize a key in session_state to store the text
                    if "pdf_highlights" not in st.session_state:
                        st.session_state["pdf_highlights"] = ""

                    # 2) Define a callback that updates session_state whenever the text changes
                    def update_text():
                        st.session_state["pdf_highlights"] = st.session_state["pdf_text_input"]

                    # 3) Create the text area with the callback
                    pdf_text_input = st.text_area(
                        "Key highlights or comments for this version:",
                        key="pdf_text_input",
                        on_change=update_text
                    )

                    # 4) When generating PDF, use the latest text from session_state
                    pdf_data = generate_pdf(
                        generate_map_snapshot(version_gdf, title=""),
                        selected_version,
                        st.session_state["pdf_highlights"],  # <<--- Updated here
                    )

                    # 5) Provide the download button as before
                    if pdf_data:
                        st.download_button(
                            label="Export PDF",
                            data=pdf_data,
                            file_name=f"redistricting_report_{selected_version}.pdf",
                            mime="application/pdf",
                        )
                        st.success("PDF download ready.")
                    else:
                        st.error("Failed to generate PDF.")

# ===================== TAB: UPLOAD DATA =====================
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
        df_uploaded = None

        if fname_lower.endswith(".csv"):
            try:
                df_uploaded = pd.read_csv(uploaded_file)
                st.success(f"Loaded {len(df_uploaded)} rows from `{uploaded_file.name}`.")
            except Exception as e:
                st.error(f"Error reading CSV: {e}")
        elif fname_lower.endswith(".xlsx"):
            try:
                df_uploaded = pd.read_excel(uploaded_file)
                st.success(f"Loaded {len(df_uploaded)} rows from `{uploaded_file.name}`.")
            except Exception as e:
                st.error(f"Error reading Excel: {e}")
        else:
            st.error("Unsupported file type. Please upload CSV or XLSX.")

        if df_uploaded is not None:
            # Placeholder for DB insertion logic
            # insert_into_staging_table(df_uploaded)
            st.info("Data is ready for processing.")
            st.dataframe(df_uploaded)
