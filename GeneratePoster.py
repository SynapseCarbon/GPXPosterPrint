import os
import sys
import math
import xml.etree.ElementTree as ET
import requests
import polyline  # Run 'pip install polyline' to enable server-side overlays
import urllib.parse
import tomllib
from io import BytesIO
from reportlab.lib.pagesizes import A3
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

# --- Typographic Additions ---
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Check if PyMuPDF is available for high-res PNG rendering (PDF>PNG)
try:
    import pymupdf
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

print(f"GPXPosterPrint started - processing configuration")

# =====================================================================
# CONFIGURATION
# =====================================================================
# 1. Get the absolute directory where GeneratePoster.py actually lives
# (Inside Docker, this will always be "/app")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Define your font path relative to the script location
# (This works perfectly both inside Docker AND on your local machine)
MONTSERRAT_BOLD_PATH = os.path.join(SCRIPT_DIR, "fonts", "Montserrat-Bold.ttf")
INTER_REGULAR_PATH = os.path.join(SCRIPT_DIR, "fonts", "Inter-Regular.ttf")

CONFIG_FILE = "config.toml"

#Load configuration from file

if os.path.exists("/app/data"):
    os.chdir("/app/data")

if not os.path.exists(CONFIG_FILE):
    print(f"❌ ERROR: Configuration file '{CONFIG_FILE}' not found!")
    sys.exit(1)

with open(CONFIG_FILE, "rb") as f:
    config = tomllib.load(f)

# File and Map settings
GPX_FILENAME = config["files"]["gpx_filename"]
OUTPUT_PDF = config["files"]["output_pdf"]
OUTPUT_PNG = os.path.splitext(OUTPUT_PDF)[0] + ".png"
MAPBOX_ACCESS_TOKEN = config["mapbox"]["access_token"]
MAPBOX_STYLE_ID = config["mapbox"]["style_id"]
TARGET_POINTS = config["processing"]["target_points"]

# Poster Theme Settings (with defaults if missing)
MAP_BORDER = config["theme"]["map_border"]
TITLE_FONT_COLOUR = HexColor(config["theme"]["title_font_colour"],"#e65c00")
DATE_FONT_COLOUR = HexColor(config["theme"]["date_font_colour"],"#2b2b2b")
ELEVATION_COLOUR = HexColor(config["theme"]["elevation_profile_colour"],"#CBCCD0")
METRIC_VALUE_COLOUR = HexColor(config["theme"]["metric_value_colour"],"#e65c00")
METRIC_TITLE_COLOUR = HexColor(config["theme"]["metric_title_colour"], "#7a705a")

# Extract Activity Information
RIDE_TITLE = config.get("ride_metadata", {}).get("title", "").upper()
RIDE_DATE = config.get("ride_metadata", {}).get("date", "").upper()

# Extract Dynamic Metrics List
STATS_METRICS = config.get("ride_metadata", {}).get("metrics", [])

# =====================================================================
# CORE FUNCTIONS
# =====================================================================

def register_custom_fonts():
    """Registers premium fonts for a true gallery match."""
    print("Registering typography layers...")
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

def load_metadata(filepath):
    meta = {}
    if not os.path.exists(filepath):
            print(f"Unable to find parameter text file at: {os.getcwd()}\\{filepath}")
            sys.exit()
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.startswith("#"):
                if ':' in line:
                    key, val = line.split(':', 1)
                    meta[key.strip().upper()] = val.strip()
    return meta

def parse_gpx(filepath):
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

    step = max(1, len(raw_points) // TARGET_POINTS)
    return raw_points[::step]

def get_mapbox_overlay_map(points, center_lat, center_lon, zoom_level, img_w, img_h):
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
        # Point-to-point ride: Render separate Start (Green) and Finish (Red) pins
        start_marker = f"pin-s-star+2ecc71({start_lon},{start_lat})"
        finish_marker = f"pin-s-marker+e74c3c({end_lon},{end_lat})"
        complete_overlay = f"{path_styling},{start_marker},{finish_marker}"

    # Split user account and style key into clean components
    user_part, style_part = MAPBOX_STYLE_ID.split('/')
    clean_user = urllib.parse.quote(user_part.strip())
    clean_style = urllib.parse.quote(style_part.strip())

    print(f"Requesting map from Mapbox API")
    url = (
        f"https://api.mapbox.com/styles/v1/{clean_user}/{clean_style}/static/"
        f"{complete_overlay}/"                       
        f"{center_lon},{center_lat},{zoom_level},0,0/"  
        f"{req_w}x{req_h}@2x"                     
        f"?attribution=false&logo=false"
        f"&access_token={MAPBOX_ACCESS_TOKEN}"
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

def draw_poster():
    register_custom_fonts()
    
    try:
        points = parse_gpx(GPX_FILENAME)
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

    c = canvas.Canvas(OUTPUT_PDF, pagesize=A3)
    width, height = A3

    white_bg = HexColor("#ffffff")
    line_color = HexColor("#d1c7b2")
    
    # Paint canvas background white
    c.setFillColor(white_bg)
    c.rect(0, 0, width, height, fill=True, stroke=False)

    # Define Map Container Layout Parameters
    map_padding = 15
    render_x = map_padding
    map_w = width - (map_padding * 2)  
    
    max_top_y = height - 15
    render_y = 285            #Was 285, was 250
    map_h = max_top_y - render_y

    # Calculate optimal zoom level
    max_span = max(max_lat - min_lat, max_lon - min_lon)
    if max_span > 1.2: zoom = 8
    elif max_span > 0.5: zoom = 9
    elif max_span > 0.2: zoom = 10
    else: zoom = 11

    # Fetch map asset from Mapbox
    img_stream = get_mapbox_overlay_map(points, center_lat, center_lon, zoom, map_w, map_h)
    
    if img_stream is not None:
        img_reader = ImageReader(img_stream)
        # Directly drawing the image removes the fragile clipping box overlay logic entirely
        c.drawImage(img_reader, render_x, render_y, width=map_w, height=map_h)
        print("Success! Unified map tile asset rendered on layout plane.")
    else:
        print("⚠️ Map background asset failed to load cleanly. Proceeding with layout.")

    # Print border around map if set to true in config.toml
    if (MAP_BORDER):
        c.setStrokeColor(line_color)
        c.setLineWidth(1.5)
        c.rect(render_x, render_y, map_w, map_h, fill=False, stroke=True)

    # Elevation Profile Section (y=180 to y=280)
    prof_x, prof_y, prof_w, prof_h = 20, 180, width - 40, 80
    
    prof_path = c.beginPath()
    prof_path.moveTo(prof_x, prof_y)
    
    # Build elevation profile
    # 1. Calculate cumulative distance along the route
    cum_distances = [0.0]
    total_dist = 0.0
    
    for i in range(1, len(points)):
        lat1, lon1 = math.radians(points[i-1][0]), math.radians(points[i-1][1])
        lat2, lon2 = math.radians(points[i][0]), math.radians(points[i][1])
        
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c_math = 2 * math.asin(math.sqrt(a))
        r = 6371000  # Earth's radius in meters
        
        total_dist += c_math * r
        cum_distances.append(total_dist)

    # 2. Match Strava's baseline crop (cuts out empty space at the bottom of the profile)
    baseline_offset = min_ele - 20

    # 3. Plot points based on physical distance (X) and true elevation (Y)
    for idx, ele in enumerate(eles):
        # Calculate X based on actual progress along the route, not point index
        if total_dist > 0:
            x_ratio = cum_distances[idx] / total_dist
        else:
            x_ratio = idx / (len(eles) - 1)
            
        x = prof_x + (x_ratio * prof_w)
        
        # Calculate Y using linear scaling from our offset baseline
        clamped_ele = max(baseline_offset, ele)
        y_ratio = (clamped_ele - baseline_offset) / (max_ele - baseline_offset if max_ele != baseline_offset else 1)
        y = prof_y + (y_ratio * prof_h)
        
        prof_path.lineTo(x, y)

    prof_path.lineTo(prof_x + prof_w, prof_y)
    prof_path.close()

    # Elevation profile
    c.setFillColor(ELEVATION_COLOUR)
    c.setStrokeColor(ELEVATION_COLOUR)
       
    c.setLineWidth(1.5)
    c.drawPath(prof_path, fill=True, stroke=True)

    # Typography Layout Secti
    c.setFillColor(TITLE_FONT_COLOUR)
    c.setFont("Montserrat-Bold", 30)
    c.drawCentredString(width / 2.0, 130, RIDE_TITLE)

    c.setFillColor(DATE_FONT_COLOUR)
    c.setFont("Montserrat-Bold", 13)  
    c.drawCentredString(width / 2.0, 108, RIDE_DATE)

    c.setStrokeColor(line_color)
    c.setLineWidth(1.0)
    c.line(40, 88, width - 40, 88)

    # =====================================================================
    # DYNAMIC FLUID METRICS ENGINE
    # =====================================================================
    num_metrics = len(STATS_METRICS)
    
    if num_metrics > 0:
        # Constrain maximum structural boundaries to margins
        grid_start_x = 40
        grid_width = width - 80
        
        # Calculate dynamic horizontal spacing allocation per metric block
        col_width = grid_width / float(num_metrics)
        
        for idx, item in enumerate(STATS_METRICS):
            # Safe fallbacks if string parameters are omitted in the TOML
            val_text = str(item.get("value", ""))
            lbl_text = str(item.get("label", "")).upper()
            
            # Find the true horizontal center of this specific column space
            col_cx = grid_start_x + (idx * col_width) + (col_width / 2.0)
            
            # Render numerical or categorical data layer
            c.setFillColor(METRIC_VALUE_COLOUR)
            c.setFont("Montserrat-Bold", 14)
            c.drawCentredString(col_cx, 58, val_text)
            
            # Render descriptive data caption string layer
            c.setFillColor(METRIC_TITLE_COLOUR)
            c.setFont("Inter-Regular", 8)
            c.drawCentredString(col_cx, 45, lbl_text)

    c.showPage()
    c.save()
    print(f"\nPDF poster compiled successfully at: {OUTPUT_PDF}")

    if PYMUPDF_AVAILABLE:
        print(f"Converting PDF to high-res PNG via PyMuPDF (300 DPI)...")
        try:
            doc = pymupdf.open(OUTPUT_PDF)
            page = doc.load_page(0)  # Load the single page poster
            
            # 300 DPI scaling math: 300 DPI / standard 72 points per inch = 4.166x zoom factor
            zoom_factor = 300 / 72  
            matrix = pymupdf.Matrix(zoom_factor, zoom_factor)
            
            # Render the vector structures to crisp raster pixels
            pix = page.get_pixmap(matrix=matrix)
            pix.save(OUTPUT_PNG)
            print(f"🎉 Generated High-Res Poster Image at: {OUTPUT_PNG}")
            doc.close()
        except Exception as e:
            print(f"⚠️ Image raster conversion failed: {e}")
    else:
        print(f"⚠️ PyMuPDF library not available - PNG file not generated")

if __name__ == "__main__":
    draw_poster()