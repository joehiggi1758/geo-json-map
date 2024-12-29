# -------------------------------------------------------------------
# Import statements
# -------------------------------------------------------------------
import matplotlib.pyplot as plt
import geopandas as gpd
import streamlit as st
import pandas as pd
import logging  # Optional for debugging
import folium
import random
import json
import io
import os

from streamlit_folium import st_folium
from shapely.geometry import shape
from datetime import datetime
from folium import plugins
from fpdf import FPDF

# -------------------------------------------------------------------
# Configuration & Basic Setup
# -------------------------------------------------------------------
st.set_page_config(page_title="Redistricting Portal", layout="wide")

PRIMARY_COLOR = "#B58264"   # Primary color for states
HIGHLIGHT_COLOR = "#3A052E" # Color for the highlighted county
PROPOSED_COLOR_DEFAULT = "#474546" # Default color for proposed districts
BACKGROUND_COLOR = "#F9FAFB"       # Background color for the app

# -------------------------------------------------------------------
# Paths and Folder Configuration
# -------------------------------------------------------------------
GEOJSON_FILE = "../data/input/counties_0.geojson"
VERSION_FOLDER = "../data/output/"

os.makedirs(VERSION_FOLDER, exist_ok=True)

# -------------------------------------------------------------------
# State Codes Mapping
# -------------------------------------------------------------------
with open("../data/input/state_code_to_name_0.json", "r") as file:
    STATE_CODE_TO_NAME = json.load(file)

# -------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------
def compute_union_all(geometry_series):
    """Use shapely's union_all() to compute the union of geometries."""
    return geometry_series.union_all()

def load_geojson(file_path):
    """
    Load GeoJSON into a GeoDataFrame and assign default color to existing districts.
    Existing districts retain their 'color' if already set; otherwise, they are assigned PRIMARY_COLOR.
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
        st.error("GeoJSON file not found. Please check the path.")
        return gpd.GeoDataFrame({"geometry": []})
    except Exception as e:
        st.error(f"Error loading GeoJSON: {e}")
        return gpd.GeoDataFrame({"geometry": []})

def save_geojson(data, file_path):
    """Save a GeoDataFrame as a GeoJSON file."""
    try:
        data.to_file(file_path, driver="GeoJSON")
        st.success(f"Saved version to `{file_path}`")
    except Exception as e:
        st.error(f"Error saving GeoJSON: {e}")

def list_saved_versions(folder_path):
    """List .geojson version files sorted by timestamp descending (most recent first)."""
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
                timestamp_str = f"{date_part}_{time_part}"
                return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            else:
                return datetime.min
        except:
            return datetime.min

    return sorted(geojson_files, key=extract_timestamp, reverse=True)

def generate_map_snapshot(gdf, title="Proposed Districts Snapshot"):
    """Generate a PNG snapshot of a GeoDataFrame using matplotlib."""
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
    """Create an in-memory PDF containing text, snapshot, etc., in landscape mode."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Territory Plan", ln=True, align="C")

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Version: {version_name}", ln=True)

    if map_png is not None:
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
    """Generate a random hex color."""
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
def get_sales_info():
    """Stub function to return sales information."""
    return pd.DataFrame({
        "NAME": [],
        "STATEFP": [],
        "SalesRep": [],
        "Product": [],
    })

# -------------------------------------------------------------------
# Main Script
# -------------------------------------------------------------------
full_gdf = load_geojson(GEOJSON_FILE)

# Initialize session state
if "pending_polygons" not in st.session_state:
    st.session_state["pending_polygons"] = []

if "selected_version" not in st.session_state:
    st.session_state["selected_version"] = None

if "last_polygon" not in st.session_state:
    st.session_state["last_polygon"] = None

# List of visited states
if "updated_states_list" not in st.session_state:
    st.session_state["updated_states_list"] = []

# Set of states that actually have newly proposed polygons
if "states_with_proposed" not in st.session_state:
    st.session_state["states_with_proposed"] = set()

st.title("Interactive Redistricting Portal")

# -------------------------------------------------------------------
# Sidebar
# -------------------------------------------------------------------
st.sidebar.header("Select a State")

if "STATEFP" not in full_gdf.columns:
    st.error("No 'STATEFP' column found in the GeoJSON file.")
    st.stop()

states_in_data = sorted(set(full_gdf["STATEFP"].unique()) & set(STATE_CODE_TO_NAME.keys()))
if "All" not in states_in_data:
    states_in_data.insert(0, "All")

selected_code = st.sidebar.selectbox(
    "Choose State:",
    states_in_data,
    format_func=lambda c: STATE_CODE_TO_NAME.get(c, f"Unknown ({c})"),
)

if selected_code not in st.session_state["updated_states_list"] and selected_code != "All":
    st.session_state["updated_states_list"].append(selected_code)

# Filter gdf based on selected_code
if selected_code == "All":
    filtered_gdf = full_gdf
else:
    filtered_gdf = full_gdf[full_gdf["STATEFP"] == selected_code]

if not filtered_gdf.empty:
    combined_geom = compute_union_all(filtered_gdf.geometry)
    state_centroid = combined_geom.centroid
else:
    state_centroid = None

st.sidebar.header("Select a County")
if "NAME" not in filtered_gdf.columns:
    st.error("No 'NAME' column found in the GeoJSON file.")
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

    sales_df = get_sales_info()

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

        # Group by geometry to combine any duplicated rows
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
        # No sales data
        final_gdf = filtered_gdf.copy()
        final_gdf["SalesRep"] = None
        final_gdf["Product"] = None
        final_gdf["color"] = final_gdf["color"].fillna(PRIMARY_COLOR)

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

    # Ensure columns for Folium tooltips
    if "SalesRep" not in final_gdf.columns:
        final_gdf["SalesRep"] = None
    if "Product" not in final_gdf.columns:
        final_gdf["Product"] = None

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

    # Add GeoJSON layer
    folium.GeoJson(
        final_gdf.__geo_interface__,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=["NAME", "SalesRep", "Product"],
            aliases=["County:", "Sales Rep:", "Product:"],
        ),
    ).add_to(m)

    # Add Draw plugin
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

    # Render the map
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

                    # If we actually drew a polygon in a real state (not "All"), track it
                    if selected_code != "All":
                        st.session_state["states_with_proposed"].add(selected_code)

                    st.success(
                        f"Added new Territory ({drawn_shape.geom_type}) with color {rand_color}."
                    )
                else:
                    st.error(f"You drew a {drawn_shape.geom_type}. Only polygons are accepted!")
            else:
                st.error("No valid geometry found in the drawn feature.")

    num_pending = len(st.session_state["pending_polygons"])
    st.write(f"**Updated Districts:** {num_pending}")

    # Input for version name
    version_name = st.text_input("Enter version name (e.g., 'Draft 1'):")

    if st.button("Save Proposed Territories"):
        if num_pending == 0:
            st.error("No polygons drawn to save!")
        elif not version_name.strip():
            st.error("Please enter a version name before saving.")
        else:
            # 1) Start with your base final_gdf (copy of 'filtered_gdf')
            final_gdf = filtered_gdf.copy()

            # 2) Determine which states actually got new polygons
            updated_states_local = set()
            for poly, color in st.session_state["pending_polygons"]:
                if selected_code != "All":
                    updated_states_local.add(selected_code)

            # 3) If any states truly got updates, color all counties in those states FIRST
            if updated_states_local:
                # Pull ALL counties from full_gdf for these states
                updated_counties = full_gdf[full_gdf["STATEFP"].isin(updated_states_local)]
                
                # Append them to final_gdf, remove duplicates
                final_gdf = pd.concat([final_gdf, updated_counties]).drop_duplicates(
                    subset=["STATEFP", "NAME", "geometry"]
                ).reset_index(drop=True)
                
                # Color all those original counties as PRIMARY_COLOR
                mask_updated = final_gdf["STATEFP"].isin(updated_states_local)
                final_gdf.loc[mask_updated, "color"] = PRIMARY_COLOR

            # 4) Now append the newly drawn polygons (with random color)
            for poly, color in st.session_state["pending_polygons"]:
                statefp_value = selected_code if selected_code != "All" else None
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

            # 5) Clear pending polygons
            st.session_state["pending_polygons"].clear()
            st.success("All counties have been colored, and new polygons have been added.")

            # 6) Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            sanitized_version_name = "".join(
                c for c in version_name if c.isalnum() or c in (" ", "_", "-")
            ).rstrip()
            version_file = os.path.join(
                VERSION_FOLDER, f"{sanitized_version_name}_{timestamp}.geojson"
            )

            # 7) Save final_gdf to GeoJSON
            try:
                final_gdf.to_file(version_file, driver="GeoJSON")
                st.success(f"Proposed district saved as `{version_file}`")
            except Exception as e:
                st.error(f"Error saving GeoJSON: {e}")
                st.stop()

            # 8) Update selected_version for the Versions tab
            st.session_state["selected_version"] = os.path.basename(version_file)
            st.info("Version saved successfully! Please navigate to the 'Versions' tab to view it.")

# ===================== TAB: SAVED VERSION SNAPSHOT =====================
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

                # Ensure columns exist for Folium tooltips
                if "SalesRep" not in version_gdf.columns:
                    version_gdf["SalesRep"] = None
                if "Product" not in version_gdf.columns:
                    version_gdf["Product"] = None

                st.subheader(f"Map for `{selected_version}`")

                if not version_gdf.empty:
                    combined_geom = compute_union_all(version_gdf.geometry)
                    if not combined_geom.is_empty:
                        version_centroid = combined_geom.centroid
                        map_location = [version_centroid.y, version_centroid.x]
                        map_zoom = 6
                    else:
                        map_location = [39.833, -98.5795]
                        map_zoom = 4

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

                    # Export PDF
                    st.markdown("### Export PDF")
                    pdf_highlights = st.text_area("Key highlights or comments for this version:")

                    pdf_data = generate_pdf(
                        generate_map_snapshot(version_gdf, title=""),
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
        if fname_lower.endswith(".csv"):
            try:
                df_uploaded = pd.read_csv(uploaded_file)
                st.success(f"Loaded {len(df_uploaded)} rows from `{uploaded_file.name}`.")
            except Exception as e:
                st.error(f"Error reading CSV file: {e}")
                df_uploaded = None
        elif fname_lower.endswith(".xlsx"):
            try:
                df_uploaded = pd.read_excel(uploaded_file)
                st.success(f"Loaded {len(df_uploaded)} rows from `{uploaded_file.name}`.")
            except Exception as e:
                st.error(f"Error reading Excel file: {e}")
                df_uploaded = None
        else:
            st.error("Unsupported file type. Please upload a CSV or XLSX file.")
            df_uploaded = None

        if df_uploaded is not None:
            # Placeholder for DB insertion logic
            # insert_into_staging_table(df_uploaded)
            st.info("Uploaded data is ready for processing.")
            st.dataframe(df_uploaded)
