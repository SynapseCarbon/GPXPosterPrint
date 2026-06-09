import os
import sys
import math
import xml.etree.ElementTree as ET
import requests
import polyline 
import urllib.parse
import tomllib

from io import BytesIO
from reportlab.lib.pagesizes import A3
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pydantic import BaseModel, Field, FilePath, field_validator, conlist
from pydantic_extra_types.color import Color
from typing import List, Dict, Any, Literal

# Check if PyMuPDF is available for high-res PNG rendering (PDF>PNG)
try:
    import pymupdf
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

class FilesModel(BaseModel):
    # FilePath ensures the file path is a string AND the file actually exists
    gpx_filename: FilePath  
    output_pdf: str

class MapboxModel(BaseModel):
    # Enforces explicit string inputs for API configuration
    access_token: str
    style_id: str

class ProcessingModel(BaseModel):
    target_points: int

class ThemeModel(BaseModel):
    map_border: bool
    overlay_elevation: bool
    transparent_elevation_fill: bool
    transparent_elevation_alpha: float = Field(
            default=0.80, 
            ge=0.0, 
            le=1.0
        )
    metrics_position: Literal["bottom","side"]
    title_position: Literal["left","centre","center"]
    page_background_colour: Color
    metric_box_outline_colour: Color
    title_font_colour: Color
    date_font_colour: Color
    elevation_profile_colour: Color
    metric_value_colour: Color
    metric_title_colour: Color
    map_border_colour: Color
    bottom_line_colour: Color

class MetricItemModel(BaseModel):
    # Child class for RideMetadata
    value: str  
    label: str  

class RideMetadataModel(BaseModel):
    title: str
    date: str
    
    # Enforce that metrics is a list of MetricItemModel objects 
    # and restrict the list size between 1 and 6 items
    metrics: list[MetricItemModel] = Field(..., min_length=1, max_length=6)

class ConfigValidator(BaseModel):
    # Master class of all config items
    files: FilesModel
    mapbox: MapboxModel
    processing: ProcessingModel
    ride_metadata: RideMetadataModel
    theme: ThemeModel

print(f"GPXPosterPrint started - processing configuration")

# =====================================================================
# CONFIGURATION
# =====================================================================
# 1. Get the absolute directory where GeneratePoster.py actually lives
# (Inside Docker, this will always be "/app")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Define your font path relative to the script location
# (This works perfectly both inside Docker AND on local machine)
MONTSERRAT_BOLD_PATH = os.path.join(SCRIPT_DIR, "fonts", "Montserrat-Bold.ttf")
INTER_REGULAR_PATH = os.path.join(SCRIPT_DIR, "fonts", "Inter-Regular.ttf")

CONFIG_FILE = "config.toml"

# When running in Docker, the bind mount should be into ./data (input and output files)
if os.path.exists("/app/data"):
    os.chdir("/app/data")

# =====================================================================
# CORE FUNCTIONS
# =====================================================================

def load_and_validate_poster_config(file_path: str):
    try:

        with open(CONFIG_FILE, "rb") as f:
            raw_config = tomllib.load(f)
        
        # Parse and validate everything at once
        validated_data = ConfigValidator(**raw_config)
        
        print("✅ Success: config.toml passed all structural checks!")
        return validated_data

    except FileNotFoundError:
        print(f"❌ File Error: The file at '{file_path}' could not be found.")
    except tomllib.TOMLDecodeError as e:
        print(f"❌ TOML Syntax Error: Your file has structural typos.\nDetails: {e}")
    except Exception as e:
        print(f"❌ Configuration Typo Detected:\n{e}")
        return None

def register_custom_fonts():
    # Registers fonts with fallback if not found

    print("Registering fonts...")
    try:
        pdfmetrics.registerFont(TTFont('Montserrat-Bold', MONTSERRAT_BOLD_PATH))
        print(" -> Montserrat-Bold registered successfully.")
    except Exception as e:
        print(f" -> ⚠️ Montserrat-Bold.ttf load failed ({e}). Falling back to Helvetica-Bold.")
        pdfmetrics.registerFont(TTFont('Montserrat-Bold', 'Helvetica-Bold'))

    try:
        pdfmetrics.registerFont(TTFont('Inter-Regular', INTER_REGULAR_PATH))
        print(" -> Inter-Regular registered successfully.")
    except Exception as e:
        print(f" -> ⚠️ Inter-Regular.ttf load failed ({e}). Falling back to Helvetica.")
        pdfmetrics.registerFont(TTFont('Inter-Regular', 'Helvetica'))

def parse_gpx(filepath, target_points):
    print(f"Parsing {os.path.getsize(filepath)/(1024*1024):.1f}MB GPX file...")
    namespaces = {'gpx': 'http://www.topografix.com/GPX/1/1'}
    tree = ET.parse(filepath)
    root = tree.getroot()
    
    raw_points = []
    for trkseg in root.findall('.//gpx:trkseg', namespaces):
        for trkpt in trkseg.findall('gpx:trkpt', namespaces):
            lat = float(trkpt.get('lat'))
            lon = float(trkpt.get('lon'))
            ele_node = trkpt.find('gpx:ele', namespaces)
            ele = float(ele_node.text) if ele_node is not None else 0.0
            raw_points.append((lat, lon, ele))
            
    if not raw_points:
        raise ValueError("No valid GPS points found in the GPX file.")

    step = max(1, len(raw_points) // target_points)
    return raw_points[::step]

def get_mapbox_overlay_map(points, center_lat, center_lon, zoom_level, img_w, img_h, mapbox_style_id, mapbox_token):
    #Fetches a map snapshot with the route pre-baked onto it by Mapbox servers
    
    # Static API dimensions must be integers and capped under 1280
    req_w = min(1280, int(img_w))
    req_h = min(1280, int(img_h))

    coord_pairs = [(p[0], p[1]) for p in points]
    encoded_track = polyline.encode(coord_pairs, precision=5)
    safe_polyline = urllib.parse.quote(encoded_track)
    path_styling = f"path-3+e65c00-1({safe_polyline})"

    # Start and finish coordinates for markers
    start_lon, start_lat = points[0][1], points[0][0]
    end_lon, end_lat = points[-1][1], points[-1][0]

    # Calculate distance between Start and Finish (Haversine formula in meters)
    lon1, lat1, lon2, lat2 = map(math.radians, [start_lon, start_lat, end_lon, end_lat])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c_math = 2 * math.asin(math.sqrt(a))
    distance_meters = 6371000 * c_math  # Radius of Earth in meters

    # If start/finish points are closer than 100 meters, use a single unified "Loop" pin
    if distance_meters < 100:
        print(f" -> Loop detected ({distance_meters:.1f}m gap). Rendering a single start/end marker.")
        # 'pin-s-bicycle+2b2b2b' -> A sleek, dark gray bicycle pin denoting a closed circuit
        loop_marker = f"pin-s-star+2b2b2b({start_lon},{start_lat})"
        complete_overlay = f"{path_styling},{loop_marker}"
    else:
        # Point-to-point ride: Render separate Start pins
        start_marker = f"pin-s-star+2ecc71({start_lon},{start_lat})"
        finish_marker = f"pin-s-marker+e74c3c({end_lon},{end_lat})"
        complete_overlay = f"{path_styling},{start_marker},{finish_marker}"

    # Split user account and style key into clean components
    user_part, style_part =  mapbox_style_id.split('/')
    clean_user = urllib.parse.quote(user_part.strip())
    clean_style = urllib.parse.quote(style_part.strip())

    print(f"Requesting map from Mapbox API")
    url = (
        f"https://api.mapbox.com/styles/v1/{clean_user}/{clean_style}/static/"
        f"{complete_overlay}/"                       
        f"{center_lon},{center_lat},{zoom_level},0,0/"  
        f"{req_w}x{req_h}@2x"                     
        f"?attribution=false&logo=false"
        f"&access_token={mapbox_token}"
    )
    
    try:
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            return BytesIO(response.content)
        else:
            print(f"\n❌ Mapbox Engine Rejected Request (Status {response.status_code})")
            print(f"Error Message: {response.text}\n")
    except Exception as e:
        print(f"Network asset retrieval failed: {e}")
    return None

def build_elevation_profile(c,parsed_gpx,page_width,elevations,minimum_elevation, maximum_elevation, profile_x, profile_y, profile_height,profile_width):
    # Build the elevation profile as a path on the canvas

    # Elevation Profile Section (y=180 to y=280)
    # prof_x, prof_y, prof_w, prof_h = 20, 180, page_width - 40, 80
    
    prof_path = c.beginPath()
    prof_path.moveTo(profile_x, profile_y)
    
    # Build elevation profile
    # Calculate cumulative distance along the route
    cum_distances = [0.0]
    total_dist = 0.0
    
    for i in range(1, len(parsed_gpx)):
        lat1, lon1 = math.radians(parsed_gpx[i-1][0]), math.radians(parsed_gpx[i-1][1])
        lat2, lon2 = math.radians(parsed_gpx[i][0]), math.radians(parsed_gpx[i][1])
        
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c_math = 2 * math.asin(math.sqrt(a))
        r = 6371000  # Earth's radius in meters
        
        total_dist += c_math * r
        cum_distances.append(total_dist)

    # Cut out empty space at the bottom of the profile
    baseline_offset = minimum_elevation - 20

    # Plot points by physical distance (X) and true elevation (Y) (rather than by time)
    for idx, ele in enumerate(elevations):
        # Calculate X based on actual progress along the route, not point index
        if total_dist > 0:
            x_ratio = cum_distances[idx] / total_dist
        else:
            x_ratio = idx / (len(elevations) - 1)
            
        x = profile_x + (x_ratio * profile_width)
        
        # Calculate Y using linear scaling from the offset baseline
        clamped_ele = max(baseline_offset, ele)
        y_ratio = (clamped_ele - baseline_offset) / (maximum_elevation - baseline_offset if maximum_elevation != baseline_offset else 1)
        y = profile_y + (y_ratio * profile_height)
        
        prof_path.lineTo(x, y)

    prof_path.lineTo(profile_x + profile_width, profile_y)
    prof_path.close()

    return prof_path

def draw_poster():

    # Load and validate the config file
    config_data = load_and_validate_poster_config(CONFIG_FILE)

    OUTPUT_PNG = os.path.splitext(config_data.files.output_pdf)[0] + ".png"

    # Replace spaces in output filename if running on Linux (avoids extra quotes around output filename)
    if sys.platform == "linux":
        config_data.files.output_pdf.replace(" ","_")
        OUTPUT_PNG.replace(" ","_")

    # Register fonts
    register_custom_fonts()
    
    # Parse the GPX file
    try:
        points = parse_gpx(config_data.files.gpx_filename,config_data.processing.target_points)
    except Exception as e:
        print(f"Error: {e}")
        return

    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    eles = [p[2] for p in points]

    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    min_ele, max_ele = min(eles), max(eles)

    center_lat = (min_lat + max_lat) / 2.0
    center_lon = (min_lon + max_lon) / 2.0

    c = canvas.Canvas(config_data.files.output_pdf, pagesize=A3)
    width, height = A3

    line_color = HexColor("#d1c7b2")
    
    # Paint canvas
    c.setFillColor(HexColor(config_data.theme.page_background_colour.as_hex(format="long")))
    c.rect(0, 0, width, height, fill=True, stroke=False)

    if config_data.theme.metrics_position == "side":
        # Metrics are on side of page

        # Define Map Container Layout Parameters
        map_padding = 15
        render_x = map_padding
        map_w = width - (map_padding * 2)  
    
        max_top_y = height - 15
        if config_data.theme.overlay_elevation:
            # Overlay elevation over bottom of map, so map is longer
            render_y = 90           #Was 180
        else:
            render_y = 180          #Was 285, was 250
        map_h = max_top_y - render_y

        # Elevation Profile Bounds
        prof_x = 20
        prof_y = 90
        prof_w = width - 40
        prof_h = 80

        # Ride Typography Placement (Absolute Bottom)
        title_y = 55
        caption_y = 35

        # Floating Metrics Panel Card Geometry
        sidebar_w = 140
        sidebar_h = (len(config_data.ride_metadata.metrics) * 65) + 30  # Height auto-scales with metric count

        # Position card in the upper-right region of the map canvas
        panel_x = (width - map_padding) - sidebar_w - 20
        panel_y = max_top_y - sidebar_h - 20

        # Map dynamic coordinates for the stacked metrics
        metric_positions = []
        start_y = (panel_y + sidebar_h) - 55
        y_gap = 65
        for idx in range(len(config_data.ride_metadata.metrics)):
            m_x = panel_x + 20  # Inset padding inside card
            m_y = start_y - (idx * y_gap)
            metric_positions.append((m_x, m_y))
    else:
        # Metrics are at bottom of page

        map_padding = 15          
        render_x = map_padding
        map_w = width - (map_padding * 2)

        max_top_y = height - 15
        if config_data.theme.overlay_elevation:
            # Overlay elevation over bottom of map, so map is longer
            render_y = 160           #Was 180
        else:
            render_y = 250           #Was 285, was 250
        map_h = max_top_y - render_y

        # Elevation Profile Bounds
        prof_x = 20
        prof_y = 160
        prof_w = width - 40
        prof_h = 80

        # Ride Typography Placement
        title_y = 125
        caption_y = 100

        # Horizontal Metrics Grid Alignment
        metric_positions = []
        num_metrics = len(config_data.ride_metadata.metrics)
        available_w = width - 160
        col_w = available_w / num_metrics
        for idx in range(num_metrics):
            # Center points for each column block
            m_x = 80 + (idx * col_w) + (col_w / 2)
            m_y = 45
            metric_positions.append((m_x, m_y))

    # Calculate optimal zoom level for map
    max_span = max(max_lat - min_lat, max_lon - min_lon)
    if max_span > 1.2: zoom = 8
    elif max_span > 0.5: zoom = 9
    elif max_span > 0.2: zoom = 10
    else: zoom = 11

    # Fetch map asset from Mapbox
    img_stream = get_mapbox_overlay_map(points, center_lat, center_lon, zoom, map_w, map_h, config_data.mapbox.style_id, config_data.mapbox.access_token)
    
    if img_stream is not None:
        img_reader = ImageReader(img_stream)
        # Directly drawing the image removes the fragile clipping box overlay logic entirely
        c.drawImage(img_reader, render_x, render_y, width=map_w, height=map_h)
        print(" -> Success! Unified map tile asset rendered on layout plane.")
    else:
        print("⚠️ Map background asset failed to load cleanly. Proceeding with layout.")

    # Print border around map if set to true in config
    if (config_data.theme.map_border):
        c.setStrokeColor(HexColor(config_data.theme.map_border_colour.as_hex(format="long")))
        c.setLineWidth(1.5)
        c.rect(render_x, render_y, map_w, map_h, fill=False, stroke=True)

    elevation_profile = build_elevation_profile(c,points,width,eles,min_ele,max_ele,prof_x,prof_y,prof_h,prof_w)

    # Draw elevation profile on page
    if config_data.theme.transparent_elevation_fill:
        transparent_fill = HexColor(config_data.theme.elevation_profile_colour.as_hex(format="long")).clone(alpha=config_data.theme.transparent_elevation_alpha)
        c.setFillColor(transparent_fill)
        c.setStrokeColor(HexColor(config_data.theme.elevation_profile_colour.as_hex(format="long")))
        c.setLineWidth(2.0)
    else:    
        c.setFillColor(HexColor(config_data.theme.elevation_profile_colour.as_hex(format="long")))
        c.setStrokeColor(HexColor(config_data.theme.elevation_profile_colour.as_hex(format="long")))
        c.setLineWidth(1.5)

    c.drawPath(elevation_profile, fill=True, stroke=True)

    # Typography Layout Section

    # Main Header Title Block
    c.setFillColor(HexColor(config_data.theme.title_font_colour.as_hex(format="long")))
    c.setFont("Montserrat-Bold", 30)
    if config_data.theme.title_position == "left":
        c.drawString(render_x, title_y, config_data.ride_metadata.title)
    else:
        c.drawCentredString(width / 2, title_y, config_data.ride_metadata.title)

    # Date or Subtitle Block
    c.setFillColor(HexColor(config_data.theme.date_font_colour.as_hex(format="long")))
    c.setFont("Montserrat-Bold", 13)
    if config_data.theme.title_position == "left":
        c.drawString(render_x, caption_y, config_data.ride_metadata.date)
    else:
        c.drawCentredString(width / 2, caption_y, config_data.ride_metadata.date)

    # Render metrics
    if config_data.theme.metrics_position == "side":
        panel_fill = HexColor(config_data.theme.page_background_colour.as_hex(format="long")).clone(alpha=0.70)  # Let subtle map textures bleed through
        c.setFillColor(panel_fill)
        c.setStrokeColor((HexColor(config_data.theme.metric_box_outline_colour.as_hex(format="long"))).clone(alpha=0.5))
        c.setLineWidth(1)
        c.roundRect(panel_x, panel_y, sidebar_w, sidebar_h, 12, fill=True, stroke=True)

        for idx, item in enumerate(config_data.ride_metadata.metrics):
            m_x, m_y = metric_positions[idx]
            
            c.setFont("Montserrat-Bold", 20)
            c.setFillColor(HexColor(config_data.theme.metric_value_colour.as_hex(format="long")))
            c.drawString(m_x, m_y + 14, item.value)
            
            c.setFont("Inter-Regular", 12)
            c.setFillColor(HexColor(config_data.theme.metric_title_colour.as_hex(format="long")))
            c.drawString(m_x, m_y, item.label.upper())
    else:
        for idx, item in enumerate(config_data.ride_metadata.metrics):
            m_x, m_y = metric_positions[idx]
            
            c.setFont("Montserrat-Bold", 14)
            c.setFillColor(HexColor(config_data.theme.metric_value_colour.as_hex(format="long")))
            c.drawCentredString(m_x, m_y + 16, item.value)
            
            c.setFont("Inter-Regular", 8)
            c.setFillColor(HexColor(config_data.theme.metric_title_colour.as_hex(format="long")))
            c.drawCentredString(m_x, m_y, item.label.upper())
        c.setStrokeColor(HexColor(config_data.theme.bottom_line_colour_colour.as_hex(format="long")))
        c.setLineWidth(1.0)
        c.line(40, 88, width - 40, 88)

    c.showPage()
    c.save()
    print(f"\nPDF poster compiled successfully at: {config_data.files.output_pdf}")

    if PYMUPDF_AVAILABLE:
        print(f"Converting PDF to high-res PNG via PyMuPDF (300 DPI)...")
        try:
            doc = pymupdf.open(config_data.files.output_pdf)
            page = doc.load_page(0)  # Load the generated file
            
            # 300 DPI scaling math: 300 DPI / standard 72 points per inch = 4.166x zoom factor
            zoom_factor = 300 / 72  
            matrix = pymupdf.Matrix(zoom_factor, zoom_factor)
            
            # Render the vector structures to crisp raster pixels
            pix = page.get_pixmap(matrix=matrix)
            pix.save(OUTPUT_PNG)
            print(f"🎉 Generated high-res PNG at: {OUTPUT_PNG}")
            doc.close()
        except Exception as e:
            print(f"⚠️ Image raster conversion failed: {e}")
    else:
        print(f"⚠️ PyMuPDF library not available - PNG file not generated")

if __name__ == "__main__":
    draw_poster()