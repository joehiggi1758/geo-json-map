# Import statements
import matplotlib.pyplot as plt
import geopandas as gpd
import streamlit as st
import pandas as pd
import folium
import random
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

PRIMARY_COLOR = "#B58264"  # Primary color for states with proposed updates
HIGHLIGHT_COLOR = "#3A052E"  # Color for the highlighted county
PROPOSED_COLOR_DEFAULT = (
    "#B58264"  # Default color for proposed districts (overridden by random colors)
)
BACKGROUND_COLOR = "#F9FAFB"  # Background color for the app

# Optional Custom CSS for styling (currently commented out)
# Uncomment and modify as needed
# st.markdown(
#     f"""
#     <style>
#     .main > div {{
#         background-color: {BACKGROUND_COLOR};
#     }}
#     h1, h2, h3, h4, h5, h6 {{
#         color: {PRIMARY_COLOR};
#     }}
#     .css-18ni7ap > p {{
#         color: #333333;
#     }}
#     </style>
#     """,
#     unsafe_allow_html=True,
# )

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
STATE_CODE_TO_NAME = {
    "All": "All States",
    "01": "Alabama",
    "02": "Alaska",
    "04": "Arizona",
    "05": "Arkansas",
    "06": "California",
    "08": "Colorado",
    "09": "Connecticut",
    "10": "Delaware",
    "11": "District of Columbia",
    "12": "Florida",
    "13": "Georgia",
    "15": "Hawaii",
    "16": "Idaho",
    "17": "Illinois",
    "18": "Indiana",
    "19": "Iowa",
    "20": "Kansas",
    "21": "Kentucky",
    "22": "Louisiana",
    "23": "Maine",
    "24": "Maryland",
    "25": "Massachusetts",
    "26": "Michigan",
    "27": "Minnesota",
    "28": "Mississippi",
    "29": "Missouri",
    "30": "Montana",
    "31": "Nebraska",
    "32": "Nevada",
    "33": "New Hampshire",
    "34": "New Jersey",
    "35": "New Mexico",
    "36": "New York",
    "37": "North Carolina",
    "38": "North Dakota",
    "39": "Ohio",
    "40": "Oklahoma",
    "41": "Oregon",
    "42": "Pennsylvania",
    "44": "Rhode Island",
    "45": "South Carolina",
    "46": "South Dakota",
    "47": "Tennessee",
    "48": "Texas",
    "49": "Utah",
    "50": "Vermont",
    "51": "Virginia",
    "53": "Washington",
    "54": "West Virginia",
    "55": "Wisconsin",
    "56": "Wyoming",
    "72": "Puerto Rico",
}


# -------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------
def union_all(geometry_series):
    """Replicate the behavior of unary_union using the union_all() method."""
    return geometry_series.union_all()


def load_geojson(file_path):
    """
    Load GeoJSON into a GeoDataFrame and assign default color to existing districts.
    Existing districts are assigned PRIMARY_COLOR only if their state has proposed updates.
    """
    try:
        gdf = gpd.read_file(file_path)
        # Initially, set 'color' to PRIMARY_COLOR for all existing districts
        gdf["color"] = PRIMARY_COLOR
        return gdf
    except FileNotFoundError:
        st.error("GeoJSON file not found. Please check the path.")
        return gpd.GeoDataFrame({"geometry": []})


def save_geojson(data, file_path):
    """Save a GeoDataFrame as a GeoJSON file."""
    try:
        data.to_file(file_path, driver="GeoJSON")
        st.success(f"Saved version to `{file_path}`")
    except Exception as e:
        st.error(f"Error saving GeoJSON: {e}")


def list_saved_versions(folder_path):
    """List .geojson version files in descending order."""
    if not os.path.exists(folder_path):
        return []
    return sorted(
        [f for f in os.listdir(folder_path) if f.endswith(".geojson")], reverse=True
    )


def generate_map_snapshot(gdf, title="Proposed Districts Snapshot"):
    """Generate a PNG snapshot of a GeoDataFrame using matplotlib."""
    if gdf.empty:
        fig, ax = plt.subplots(figsize=(12, 9))  # Landscape orientation
        ax.text(0.5, 0.5, "No geometry to display", ha="center", va="center")
        ax.axis("off")
    else:
        fig, ax = plt.subplots(figsize=(12, 9))  # Landscape orientation
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
    pdf = FPDF(orientation="L", unit="mm", format="A4")  # Landscape orientation
    pdf.add_page()

    # Set fonts
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Redistricting Report", ln=True, align="C")

    pdf.set_font("Arial", size=12)
    pdf.ln(5)
    pdf.cell(0, 10, f"Version: {version_name}", ln=True)

    # Create a multi-cell for highlights
    pdf.multi_cell(0, 10, f"Highlights:\n{highlights}", align="L")
    pdf.ln(5)

    if map_png is not None:
        temp_file = "temp_map_snapshot.png"
        try:
            with open(temp_file, "wb") as temp_img:
                temp_img.write(map_png.getbuffer())
            # Calculate positions and dimensions
            # A4 landscape: 297mm x 210mm
            # Margins: 10mm
            image_width = 222.75  # 75% of page width
            image_x = 10
            image_y = pdf.get_y()
            pdf.image(temp_file, x=image_x, y=image_y, w=image_width)

            # Comments position
            comments_x = image_x + image_width + 10  # 10mm gap
            comments_width = 297 - comments_x - 10  # 10mm right margin
            pdf.set_xy(comments_x, image_y)
            pdf.multi_cell(comments_width, 10, highlights, align="L")
        finally:
            try:
                os.remove(temp_file)
            except FileNotFoundError:
                pass

    pdf_buffer = io.BytesIO(pdf.output(dest="S").encode("latin-1"))
    return pdf_buffer


def get_random_color():
    """Generate a random hex color."""
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))


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

st.title("Interactive Redistricting Portal")

# -------------------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------------------
st.sidebar.header("Select a State (or All)")

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

# Filter GeoDataFrame based on selected state
if selected_code == "All":
    filtered_gdf = full_gdf
else:
    filtered_gdf = full_gdf[full_gdf["STATEFP"] == selected_code]

# Compute the centroid of the selected state or use default US center
if not filtered_gdf.empty:
    combined_geom = union_all(filtered_gdf.geometry)
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
tab_main, tab_snapshot, tab_upload = st.tabs(
    ["Main Map", "Saved Version Snapshot", "Upload Data"]
)

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
        # Merge sales data with GeoDataFrame
        merged_df = pd.merge(
            filtered_gdf,
            sales_df.rename(columns={"CountyName": "NAME", "StateFIPS": "STATEFP"}),
            on=["NAME", "STATEFP"],
            how="left",
        )
        final_gdf = gpd.GeoDataFrame(
            merged_df, geometry="geometry", crs=filtered_gdf.crs
        )
    else:
        final_gdf = filtered_gdf.copy()
        final_gdf["SalesRep"] = None
        final_gdf["Product"] = None
        # Ensure all districts have the PRIMARY_COLOR
        final_gdf["color"] = final_gdf["color"].fillna(PRIMARY_COLOR)

    # Identify states with proposed updates
    states_with_updates = final_gdf[final_gdf["color"] != PRIMARY_COLOR][
        "STATEFP"
    ].unique()

    # Assign PRIMARY_COLOR to existing districts in states with updates
    for state in states_with_updates:
        final_gdf.loc[
            (final_gdf["STATEFP"] == state) & (final_gdf["color"] == PRIMARY_COLOR),
            "color",
        ] = PRIMARY_COLOR

        # Define style function for Folium

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
            color = feature["properties"].get("color", PROPOSED_COLOR_DEFAULT)
            return {"fillColor": color, "color": color, "weight": 1, "fillOpacity": 0.4}

    # Create Folium map with light base tiles
    m = folium.Map(
        location=map_location,
        zoom_start=map_zoom,
        width="100%",
        height="600",
        tiles="cartodbpositron",  # Use a light-colored base map to ensure visibility
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
                        f"Added new {drawn_shape.geom_type} to memory with color {random_color}."
                    )
                else:
                    st.error(
                        f"You drew a {drawn_shape.geom_type}. Only polygons are accepted!"
                    )
            else:
                st.error("No valid geometry found in the drawn feature.")

    # Display number of pending polygons
    num_pending = len(st.session_state.get("pending_polygons", []))
    st.write(f"**Pending Polygons:** {num_pending}")

    # Input for version name
    version_name = st.text_input("Enter version name (e.g., 'Draft 1'):")

    # Button to save proposed district
    if st.button("Save Proposed District"):
        if num_pending == 0:
            st.error("No polygons drawn to save!")
        elif not version_name.strip():
            st.error("Please enter a version name before saving.")
        else:
            # Merge pending polygons into final_gdf with random colors
            for poly, color in st.session_state["pending_polygons"]:
                new_row = gpd.GeoDataFrame(
                    {
                        "STATEFP": [None if selected_code == "All" else selected_code],
                        "NAME": [f"{selected_county} (Proposed)"],
                        "SalesRep": [None],
                        "Product": [None],
                        "color": [color],  # Assign random color
                        "geometry": [poly],
                    },
                    crs=final_gdf.crs,
                )
                final_gdf = pd.concat([final_gdf, new_row], ignore_index=True)

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
                "Version saved successfully! Please navigate to the 'Saved Version Snapshot' tab to view it."
            )

# ------------------ TAB: SAVED VERSION SNAPSHOT --------------------
with tab_snapshot:
    st.header("Saved Version Snapshot")

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
                    # Identify states with proposed updates in the saved version
                    states_with_updates = version_gdf[
                        version_gdf["color"] != PRIMARY_COLOR
                    ]["STATEFP"].unique()

                    # Assign PRIMARY_COLOR to existing districts in states with updates
                    for state in states_with_updates:
                        version_gdf.loc[
                            (version_gdf["STATEFP"] == state)
                            & (version_gdf["color"] == PRIMARY_COLOR),
                            "color",
                        ] = PRIMARY_COLOR

                    # Define style function for saved versions
                    def style_function_version(feature):
                        statefp = feature["properties"].get("STATEFP")
                        color = feature["properties"].get("color")

                        if statefp in states_with_updates:
                            if color != PRIMARY_COLOR:
                                # Proposed district
                                return {
                                    "fillColor": color,
                                    "color": color,
                                    "weight": 1,
                                    "fillOpacity": 0.4,
                                }
                            else:
                                # Existing district in a state with updates
                                return {
                                    "fillColor": PRIMARY_COLOR,
                                    "color": PRIMARY_COLOR,
                                    "weight": 1,
                                    "fillOpacity": 0.4,
                                }
                        else:
                            # State without updates: no fill
                            return {
                                "fillColor": "#FFFFFF",  # White or any neutral color
                                "color": "black",
                                "weight": 1,
                                "fillOpacity": 0,
                            }

                    # Compute the centroid for map centering
                    if "All" in states_with_updates:
                        map_location = [39.833, -98.5795]  # Center of the contiguous US
                        map_zoom = 4
                    elif len(states_with_updates) > 0:
                        # Calculate centroid of all updated states
                        combined_geom = union_all(
                            version_gdf[
                                version_gdf["STATEFP"].isin(states_with_updates)
                            ].geometry
                        )
                        version_centroid = combined_geom.centroid
                        map_location = [version_centroid.y, version_centroid.x]
                        map_zoom = 6
                    else:
                        # Default to US center if no geometry
                        map_location = [39.833, -98.5795]
                        map_zoom = 4

                    # Create Folium map with light base tiles
                    m_version = folium.Map(
                        location=map_location,
                        zoom_start=map_zoom,
                        width="100%",
                        height="600",
                        tiles="cartodbpositron",  # Ensure consistent base map styling
                    )

                    # Add GeoJSON layer
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
                    if st.download_button(
                        label="Export PDF",
                        data=generate_pdf(
                            generate_map_snapshot(
                                version_gdf, title=f"Snapshot: {selected_version}"
                            ),
                            selected_version,
                            pdf_highlights,
                        ),
                        file_name=f"redistricting_report_{selected_version}.pdf",
                        mime="application/pdf",
                    ):
                        st.success(
                            "PDF report generated and download initiated successfully."
                        )
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
