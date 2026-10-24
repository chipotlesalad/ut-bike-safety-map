"""
UT Austin Bike Safety Map — Version 1
Colors every bikeable road near campus by how safe its bike infrastructure is,
then saves an interactive map you can open in any browser.

Setup (once):   pip install osmnx folium
Run:            python bike_map.py
Output:         bike_map.html  (double-click to open)
"""

import osmnx as ox
import folium

# ---------------------------------------------------------------
# 1. Settings — change these to move or resize the map
# ---------------------------------------------------------------
CENTER = (30.2849, -97.7341)   # UT Tower (lat, lon)
RADIUS_M = 2000                # how far out to pull roads, in meters (~1.2 miles)

# OpenStreetMap stores bike-lane info in these tags. OSMnx drops them by
# default, so we tell it to keep them.
CYCLEWAY_COLS = ["cycleway", "cycleway:left", "cycleway:right", "cycleway:both"]
ox.settings.useful_tags_way = list(ox.settings.useful_tags_way) + CYCLEWAY_COLS + ["bicycle"]

# ---------------------------------------------------------------
# 2. Download the bike network from OpenStreetMap
# ---------------------------------------------------------------
print("Downloading street network (takes ~30 seconds)...")
G = ox.graph_from_point(CENTER, dist=RADIUS_M, network_type="bike")
edges = ox.graph_to_gdfs(G, nodes=False).reset_index(drop=True)
print(f"Got {len(edges)} road segments.")

# ---------------------------------------------------------------
# 3. Classify each road segment
# ---------------------------------------------------------------
def as_list(value):
    """OSM tags can be a single value, a list, or missing (NaN). Normalize to a list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return []  # missing / NaN


def classify(row):
    highways = as_list(row.get("highway"))
    bike_tags = []
    for col in CYCLEWAY_COLS:
        bike_tags += as_list(row.get(col))
    bicycle = as_list(row.get("bicycle"))

    # Dedicated bike paths or physically separated lanes
    if "cycleway" in highways or "track" in bike_tags:
        return "Protected / bike path"
    if "path" in highways and "designated" in bicycle:
        return "Protected / bike path"
    # Painted bike lane on the road
    if "lane" in bike_tags:
        return "Painted bike lane"
    # Sharrows: bikes share the lane with cars
    if "shared_lane" in bike_tags or "share_busway" in bike_tags:
        return "Shared lane"
    # Sidewalks, campus walkways, and other paths (bikes allowed, but not built for them)
    if any(h in ("footway", "pedestrian", "path", "steps", "track", "bridleway") for h in highways):
        return "Sidewalk / footpath"
    # Parking lots, driveways, alleys
    if "service" in highways:
        return "Alley / parking lot"
    # Low-traffic neighborhood streets
    if any(h in ("residential", "living_street", "unclassified") for h in highways):
        return "Quiet street"
    # What's left are real through-roads with no bike lane
    return "No bike facility"


edges["category"] = edges.apply(classify, axis=1)

# Clean up street names for the hover tooltip
if "name" in edges.columns:
    edges["name"] = edges["name"].apply(
        lambda v: ", ".join(v) if isinstance(v, list) else (v if isinstance(v, str) else "Unnamed")
    )
else:
    edges["name"] = "Unnamed"

print("\nRoad segments by category:")
print(edges["category"].value_counts().to_string())

# ---------------------------------------------------------------
# 4. Build the interactive map
# ---------------------------------------------------------------
COLORS = {
    "Protected / bike path": "#1a9850",  # dark green  = safest
    "Painted bike lane":     "#66bd63",  # light green
    "Quiet street":          "#4575b4",  # blue
    "Shared lane":           "#f46d43",  # orange
    "No bike facility":      "#d73027",  # red         = least safe
    "Sidewalk / footpath":   "#9e9e9e",  # gray
    "Alley / parking lot":   "#cfcfcf",  # light gray
}

# Light-gray background map from Esri (free, no API key, works when you
# open the HTML file directly from your computer)
m = folium.Map(location=CENTER, zoom_start=15, tiles=None)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
          "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
    name="Light gray map",
    max_zoom=16,
).add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/"
          "MapServer/tile/{z}/{y}/{x}",
    attr="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
    name="Street map",
    max_zoom=19,
).add_to(m)

# One toggleable layer per category. Drawn in reverse so gray paths sit
# underneath and the safest routes (green) are drawn on top.
for category, color in reversed(list(COLORS.items())):
    subset = edges[edges["category"] == category][["geometry", "name", "category"]]
    if subset.empty:
        continue
    weight = 2 if category in ("Sidewalk / footpath", "Alley / parking lot") else 4
    layer = folium.FeatureGroup(name=category)
    folium.GeoJson(
        subset,
        style_function=lambda feature, c=color, w=weight: {"color": c, "weight": w, "opacity": 0.85},
        tooltip=folium.GeoJsonTooltip(fields=["name", "category"], aliases=["Street:", "Type:"]),
    ).add_to(layer)
    layer.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

# Legend in the bottom-left corner
legend_items = "".join(
    f'<div><span style="display:inline-block;width:14px;height:4px;background:{c};'
    f'margin-right:6px;vertical-align:middle"></span>{name}</div>'
    for name, c in COLORS.items()
)
legend_html = f"""
<div style="position:fixed;bottom:24px;left:24px;z-index:9999;background:white;
            padding:10px 14px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);
            font:13px sans-serif;line-height:1.7">
  <b>Bike safety</b>{legend_items}
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

m.save("bike_map.html")
print("\nSaved bike_map.html — open it in your browser.")
