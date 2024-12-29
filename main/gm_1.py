# Import statements
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


# From statements
from streamlit_folium import st_folium
from shapely.geometry import shape
from datetime import datetime
from folium import plugins
from fpdf import FPDF

# -------------------------------------------------------------------
# Configuration & Basic Setup
# -------------------------------------------------------------------
st.set_page_config(page_title="Redistricting Portal", layout="wide")

PRIMARY_COLOR = "#B58264"  # Primary color for states
HIGHLIGHT_COLOR = "#3A052E"  # Color for the highlighted county
PROPOSED_COLOR_DEFAULT = "#474546"  # Default color for proposed districts
BACKGROUND_COLOR = "#F9FAFB"  # Background color for the app

# -------------------------------------------------------------------
# Paths and Folder Configuration
# -------------------------------------------------------------------
GEOJSON_FILE = "../data/input/counties_0.geojson"  # Adjust the path as needed
VERSION_FOLDER = "../data/output/"  # Directory to save versions

# Ensure the versions folder exists
os.makedirs(VERSION_FOLDER, exist_ok=True)

# -------------------------------------------------------------------
# State Codes Mapping
# -------------------------------------------------------------------
# Load the JSON file
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
            # If 'color' column doesn't exist, initialize it with PRIMARY_COLOR
            gdf["color"] = PRIMARY_COLOR
        else:
            # Fill NaN or None values in 'color' with PRIMARY_COLOR
            gdf["color"] = gdf["color"].fillna(PRIMARY_COLOR)

        # Ensure 'STATEFP' is a string with leading zeros
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
    """List .geojson version files sorted by timestamp descendingly (most recent first)."""
    if not os.path.exists(folder_path):
        return []

    # List all GeoJSON files in the folder
    geojson_files = [f for f in os.listdir(folder_path) if f.endswith(".geojson")]

    # Function to extract timestamp from filename
    def extract_timestamp(filename):
        try:
            # Remove the file extension
            base = os.path.splitext(filename)[0]
            # Split the filename by underscores
            parts = base.split("_")
            # Assume the last two parts are date and time
            if len(parts) >= 2:
                date_part = parts[-2]  # e.g., '20230412'
                time_part = parts[-1]  # e.g., '153000'
                timestamp_str = f"{date_part}_{time_part}"
                # Convert to datetime object
                return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            else:
                # If the filename doesn't have the expected format, assign the earliest possible date
                return datetime.min
        except Exception:
            # In case of any parsing errors, assign the earliest possible date
            return datetime.min

    # Sort the files based on the extracted timestamps in descending order
    geojson_files_sorted = sorted(
        geojson_files, key=extract_timestamp, reverse=True  # Most recent first
    )

    return geojson_files_sorted

def generate_map_snapshot(gdf, title="Proposed Districts Snapshot"):
    """Generate a PNG snapshot of a GeoDataFrame using matplotlib."""
    if gdf.empty:
        fig, ax = plt.subplots(figsize=(8, 6))  # Landscape orientation
        ax.text(0.5, 0.5, "No geometry to display", ha="center", va="center")
        ax.axis("off")
    else:
        fig, ax = plt.subplots(figsize=(8, 6))  # Landscape orientation
        gdf.plot(ax=ax, edgecolor="black", color=gdf["color"], alpha=0.6)
        ax.set_title(title)
        ax.axis("off")
        ax.set_aspect("equal")  # Preserve aspect ratio
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf

def generate_pdf(map_png, version_name, highlights):
    """Create an in-memory PDF containing text, snapshot, etc., in landscape mode."""
    pdf = FPDF(
        orientation="L", unit="mm", format="A4"
    )  # Landscape orientation (297x210mm)
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

            # Calculate dimensions
            page_width = 297  # A4 landscape width in mm
            margin = 10
            map_width = int(page_width * 0.7) - (2 * margin)  # 70% of usable width
            comments_width = int(page_width * 0.3) - margin  # 30% of usable width

            # Position the map on the left
            map_x = margin
            map_y = pdf.get_y()
            pdf.image(temp_file, x=map_x, y=map_y, w=map_width)

            # Position comments on the right
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
    else:
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
    else:
        color = feature["properties"].get("color", PRIMARY_COLOR)
        return {"fillColor": color, "color": color, "weight": 1, "fillOpacity": 0.4}

def style_function_version(feature):
    # Retrieve the district's color; default to PRIMARY_COLOR if not set
    district_color = feature["properties"].get("color", PRIMARY_COLOR)

    return {
        "fillColor": district_color,
        "color": district_color,
        "weight": 1,
        "fillOpacity": 0.6 if district_color != PRIMARY_COLOR else 0.4,
    }

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
# Load GeoJSON data
full_gdf = load_geojson(GEOJSON_FILE)

# Initialize session state variables
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
    st.error("No 'STATEFP' column found in the GeoJSON file.")
    st.stop()

states_in_data = sorted(
    set(full_gdf["STATEFP"].unique()) & set(STATE_CODE_TO_NAME.keys())
)
if "All" not in states_in_data:
    states_in_data.insert(0, "All")

selected_code = st.sidebar.selectbox(
    "Choose State:",
    states_in_data,
    format_func=lambda c: STATE_CODE_TO_NAME.get(c, f"Unknown ({c})"),
)

# Initialize ls_0 if not already done
if 'ls_0' not in st.session_state:
    st.session_state['ls_0'] = []

# Append the selected state if it's not already in the list
if selected_code not in st.session_state['ls_0'] and selected_code != 'All':
    st.session_state['ls_0'].append(selected_code)

# Ensure the list contains only unique elements
unique_ls_0 = list({i for i in st.session_state['ls_0']})

# Display the updated unique list
st.write("Unique Selected States:", unique_ls_0)

# Filter GeoDataFrame based on selected state
if selected_code == "All":
    filtered_gdf = full_gdf
else:
    filtered_gdf = full_gdf[full_gdf["STATEFP"] == selected_code]

# Compute the centroid of the selected state or use default US center
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
            # Merge pending polygons into final_gdf with random colors
            # print(final_gdf.shape)
            for poly, color in st.session_state["pending_polygons"]:
                # Capture the values for the current polygon
                statefp_value = selected_code if selected_code != "All" else None
                name_value = f"{selected_county} (Proposed)"
                sales_rep_value = None
                product_value = None

                # Create a new GeoDataFrame row for the current polygon
                new_row = gpd.GeoDataFrame(
                    {
                        "STATEFP": [statefp_value],
                        "NAME": [name_value],
                        "SalesRep": [sales_rep_value],
                        "Product": [product_value],
                        "color": [color],  # Assign random color
                        "geometry": [poly],
                    },
                    crs=final_gdf.crs,
                )

                # Append the new row to the existing final_gdf
                final_gdf = pd.concat([final_gdf, new_row], ignore_index=True)
                # print(final_gdf.shape)


            # Clear pending polygons
            st.session_state["pending_polygons"].clear()
            st.success("Pending polygons have been merged into the dataset.")

            # Generate timestamp and file name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Sanitize version name to create a valid filename
            sanitized_version_name = "".join(
                c for c in version_name if c.isalnum() or c in (" ", "_", "-")
            ).rstrip()
            version_file = os.path.join(
                VERSION_FOLDER, f"{sanitized_version_name}_{timestamp}.geojson"
            )

            # Save to GeoJSON
            try:
                # Ensure all non-proposed districts have PRIMARY_COLOR
                final_gdf["color"] = final_gdf.apply(
                    lambda row: (
                        row["color"]
                        if pd.notnull(row["color"]) and row["color"] != PRIMARY_COLOR
                        else PRIMARY_COLOR
                    ),
                    axis=1,
                )
                final_gdf.to_file(version_file, driver="GeoJSON")
                st.success(f"Proposed district saved as `{version_file}`")
            except Exception as e:
                st.error(f"Error saving GeoJSON: {e}")
                st.stop()

            # Placeholder for ODM API Auditing
            # Replace with actual auditing logic when ready
            # audit_to_odm_api({
            #     "version_name": sanitized_version_name,
            #     "count_polygons": len(final_gdf),
            #     "time_saved": timestamp
            # })

            # Update selected version without rerunning
            st.session_state["selected_version"] = os.path.basename(version_file)

            # Notify the user to switch tabs to view the saved version
            st.info(
                "Version saved successfully! Please navigate to the 'Saved Versions' tab to view it."
            )

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
