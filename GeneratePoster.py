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

# =====================================================================
# CONFIGURATION
# =====================================================================
CONFIG_FILE = "config.toml"

#Load configuration from file

if not os.path.exists(CONFIG_FILE):
    print(f"❌ ERROR: Configuration file '{CONFIG_FILE}' not found!")
    sys.exit(1)

with open(CONFIG_FILE, "rb") as f:
    config = tomllib.load(f)

# File and Map settings
GPX_FILENAME = config["files"]["gpx_filename"]
OUTPUT_PDF = config["files"]["output_pdf"]
MAPBOX_ACCESS_TOKEN = config["mapbox"]["access_token"]
MAPBOX_STYLE_ID = config["mapbox"]["style_id"]
TARGET_POINTS = config["processing"]["target_points"]

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
        pdfmetrics.registerFont(TTFont('Montserrat-Bold', './fonts/Montserrat-Bold.ttf'))
        print(" -> Montserrat-Bold registered successfully.")
    except Exception as e:
        print(f" -> ⚠️ Montserrat-Bold.ttf load failed ({e}). Falling back to Helvetica-Bold.")
        pdfmetrics.registerFont(TTFont('Montserrat-Bold', 'Helvetica-Bold'))

    try:
        pdfmetrics.registerFont(TTFont('Inter-Regular', './fonts/Inter-Regular.ttf'))
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
    """Fetches a map snapshot with the route pre-baked onto it by Mapbox servers."""
    
    # Static API dimensions must be integers and capped under 1280
    req_w = min(1280, int(img_w))
    req_h = min(1280, int(img_h))

    coord_pairs = [(p[0], p[1]) for p in points]
    encoded_track = polyline.encode(coord_pairs, precision=5)
    safe_polyline = urllib.parse.quote(encoded_track)

    path_styling = f"path-3+e65c00-1({safe_polyline})"
    safe_style_path = "".join([urllib.parse.quote(c) if c != '/' else c for c in MAPBOX_STYLE_ID])

    url = (
        f"https://api.mapbox.com/styles/v1/{safe_style_path}/static/"
        f"{path_styling}/"                       
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
    strava_orange = HexColor("#e65c00")
    dark_gray = HexColor("#2b2b2b")
    muted_gray = HexColor("#7a705a")
    line_color = HexColor("#d1c7b2")
    light_gray = HexColor("#CBCCD0")

    # Paint canvas background white
    c.setFillColor(white_bg)
    c.rect(0, 0, width, height, fill=True, stroke=False)

    # Define Map Container Layout Parameters
    map_padding = 40
    render_x = map_padding
    map_w = width - (map_padding * 2)  
    
    max_top_y = height - 40   
    render_y = 250            #Was 285
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

    # Uncomment the three lines below if you want a border around the map
    #c.setStrokeColor(line_color)
    #c.setLineWidth(1.5)
    #c.rect(render_x, render_y, map_w, map_h, fill=False, stroke=True)

    # Elevation Profile Section (y=180 to y=280)
    prof_x, prof_y, prof_w, prof_h = 40, 180, width - 80, 50
    prof_path = c.beginPath()
    prof_path.moveTo(prof_x, prof_y)
    num_p = len(eles)
    for idx, ele in enumerate(eles):
        x = prof_x + (idx / (num_p - 1)) * prof_w
        y = prof_y + (((ele - min_ele) / (max_ele - min_ele if max_ele != min_ele else 1)) * prof_h)
        prof_path.lineTo(x, y)
    prof_path.lineTo(prof_x + prof_w, prof_y)
    prof_path.close()

    # Use light gray for the elevation profile (change if wanted)
    c.setFillColor(light_gray)
    c.setStrokeColor(light_gray)
       
    c.setLineWidth(1.5)
    c.drawPath(prof_path, fill=True, stroke=True)

    # Typography Layout Section
    c.setFillColor(strava_orange)
    c.setFont("Montserrat-Bold", 30)
    c.drawCentredString(width / 2.0, 130, RIDE_TITLE)

    c.setFillColor(dark_gray)
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
            c.setFillColor(strava_orange)
            c.setFont("Montserrat-Bold", 14)
            c.drawCentredString(col_cx, 58, val_text)
            
            # Render descriptive data caption string layer
            c.setFillColor(muted_gray)
            c.setFont("Inter-Regular", 8)
            c.drawCentredString(col_cx, 45, lbl_text)

    c.showPage()
    c.save()
    print(f"\nCompleted! Final poster compiled successfully at: {OUTPUT_PDF}")

if __name__ == "__main__":
    draw_poster()