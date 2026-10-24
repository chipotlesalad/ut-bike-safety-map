"""
UT Austin Safest Bike Route Finder
Click a start point and a destination on the map, and it draws the SAFEST
bike route (favoring bike paths, bike lanes, and quiet streets) next to the
SHORTEST route, so you can compare them.

Setup (once):   pip3 install osmnx folium
Run:            python3 route_finder.py
Output:         route_map.html  (open it in your browser)

The routing runs entirely in the browser, so the HTML file also works when
uploaded to GitHub Pages.
"""

import json

import osmnx as ox

# ---------------------------------------------------------------
# 1. Settings
# ---------------------------------------------------------------
CENTER = (30.2849, -97.7341)   # UT Tower (lat, lon)
RADIUS_M = 4000                # ~2.5 miles. Bigger = more of Austin, but slower and a bigger file.
OUTPUT_FILE = "route_map.html"
VERSION = "1.5 (keyword search)"

# Each category gets a color and a "penalty." The route finder treats
# 1 meter on a road as costing (penalty) meters, so it will happily ride
# a bit farther to stay on safer streets. Tweak these to change how much
# the router avoids dangerous roads.
CATEGORIES = [
    # name                    color      penalty
    ("Protected / bike path", "#1a9850", 1.0),
    ("Painted bike lane",     "#66bd63", 1.3),
    ("Quiet street",          "#4575b4", 1.2),
    ("Shared lane",           "#f46d43", 2.0),
    ("No bike facility",      "#d73027", 4.0),
    ("Sidewalk / footpath",   "#9e9e9e", 1.6),
    ("Alley / parking lot",   "#bdbdbd", 1.5),
]
CAT_INDEX = {name: i for i, (name, _, _) in enumerate(CATEGORIES)}

CYCLEWAY_COLS = ["cycleway", "cycleway:left", "cycleway:right", "cycleway:both"]


# ---------------------------------------------------------------
# 2. Classify a road segment (same logic as bike_map.py)
# ---------------------------------------------------------------
def as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return []


def classify(row):
    highways = as_list(row.get("highway"))
    bike_tags = []
    for col in CYCLEWAY_COLS:
        bike_tags += as_list(row.get(col))
    bicycle = as_list(row.get("bicycle"))

    if "cycleway" in highways or "track" in bike_tags:
        return "Protected / bike path"
    if "path" in highways and "designated" in bicycle:
        return "Protected / bike path"
    if "lane" in bike_tags:
        return "Painted bike lane"
    if "shared_lane" in bike_tags or "share_busway" in bike_tags:
        return "Shared lane"
    if any(h in ("footway", "pedestrian", "path", "steps", "track", "bridleway") for h in highways):
        return "Sidewalk / footpath"
    if "service" in highways:
        return "Alley / parking lot"
    if any(h in ("residential", "living_street", "unclassified") for h in highways):
        return "Quiet street"
    return "No bike facility"


# ---------------------------------------------------------------
# 2b. Named places for the search box (shops, cafes, UT buildings, ...)
# ---------------------------------------------------------------
# Anything with one of these tags and a name becomes searchable.
PLACE_TAGS = {
    "amenity": True, "shop": True, "leisure": True, "tourism": True, "office": True,
    "building": True, "healthcare": True, "craft": True, "historic": True,
    "club": True, "place": ["neighbourhood", "suburb", "quarter"],
}
# Tags whose values describe what a place IS, in priority order
KIND_KEYS = ["amenity", "shop", "leisure", "tourism", "healthcare", "office",
             "craft", "historic", "club", "place", "building"]
# Other names a place goes by
ALT_NAME_KEYS = ["alt_name", "short_name", "official_name", "old_name", "loc_name",
                 "brand", "operator", "ref"]
# Extra words people search with, by place type
SYNONYMS = {
    "cafe": "coffee espresso tea cafe", "coffee": "coffee cafe espresso",
    "restaurant": "food restaurant eat lunch dinner", "fast_food": "food fast food quick eat",
    "food_court": "food court eat", "bar": "bar drinks", "pub": "pub bar drinks",
    "biergarten": "beer garden bar drinks", "nightclub": "club nightlife",
    "ice_cream": "ice cream dessert", "bakery": "bakery bread pastry dessert",
    "supermarket": "grocery groceries supermarket market food store",
    "convenience": "convenience store snacks", "greengrocer": "grocery produce market",
    "pharmacy": "pharmacy drugstore medicine", "chemist": "pharmacy drugstore",
    "hospital": "hospital medical er", "clinic": "clinic doctor medical", "doctors": "doctor clinic medical",
    "dentist": "dentist dental", "fuel": "gas station fuel", "bank": "bank atm money", "atm": "atm cash bank",
    "fitness_centre": "gym fitness workout", "sports_centre": "gym sports recreation rec center",
    "swimming_pool": "pool swimming", "park": "park green", "playground": "playground park",
    "stadium": "stadium sports", "pitch": "field sports", "library": "library books study",
    "university": "university college campus school", "college": "college campus school",
    "school": "school", "kindergarten": "preschool daycare",
    "apartments": "apartments apartment housing", "dormitory": "dorm dormitory residence hall housing",
    "residential": "housing residential", "hotel": "hotel lodging", "hostel": "hostel lodging",
    "parking": "parking garage lot", "bicycle_parking": "bike parking rack bicycle",
    "bicycle_rental": "bike rental bicycle share", "bicycle": "bike shop bicycle repair",
    "place_of_worship": "church worship", "post_office": "post office mail usps",
    "cinema": "movies movie theater cinema", "theatre": "theater theatre shows",
    "museum": "museum", "laundry": "laundromat laundry", "dry_cleaning": "dry cleaner laundry",
    "hairdresser": "haircut barber salon hair", "clothes": "clothing clothes store",
    "books": "bookstore books", "electronics": "electronics tech store",
    "mobile_phone": "phone store", "department_store": "department store shopping",
    "mall": "mall shopping", "car_repair": "auto repair mechanic", "veterinary": "vet animal",
    "pet": "pet store", "alcohol": "liquor store", "beverages": "drinks store",
    "community_centre": "community center", "townhall": "city hall",
    "police": "police", "fire_station": "fire station",
}


def _text(row, key):
    v = row.get(key)
    return v.strip() if isinstance(v, str) and v.strip() else ""


def _pretty(kind):
    return kind.replace("_", " ").capitalize() if kind else ""


def build_places():
    try:
        gdf = ox.features_from_point(CENTER, tags=PLACE_TAGS, dist=RADIUS_M)
    except Exception as err:   # no data or download error: search still works via Photon
        print(f"Couldn't download places for search ({err}). Address search will still work.")
        return []
    if "name" not in gdf.columns:
        return []
    gdf = gdf[gdf["name"].notna()]

    places, seen = [], set()
    for _, row in gdf.iterrows():
        if _text(row, "highway"):            # streets are found by address search instead
            continue
        name = _text(row, "name")
        if not name:
            continue
        geom = row.geometry
        pt = geom if geom.geom_type == "Point" else geom.representative_point()
        lat, lon = round(pt.y, 5), round(pt.x, 5)
        key = (name.lower(), round(lat, 3), round(lon, 3))
        if key in seen:
            continue
        seen.add(key)

        kinds = [_text(row, k) for k in KIND_KEYS]
        kinds = [k for k in kinds if k and k not in ("yes", "no")]
        kind = kinds[0] if kinds else ""

        words = set()
        for k in ALT_NAME_KEYS:
            words.add(_text(row, k))
        for k in kinds:
            words.add(k.replace("_", " "))
            words.add(SYNONYMS.get(k, ""))
        for c in _text(row, "cuisine").split(";"):
            words.add(c.replace("_", " "))
            words.add(SYNONYMS.get(c.strip(), ""))
        words.discard("")

        house, street = _text(row, "addr:housenumber"), _text(row, "addr:street")
        address = f"{house} {street}".strip() if street else ""
        detail = " · ".join(x for x in (_pretty(kind), address) if x)
        places.append([name, detail, lat, lon, " ".join(sorted(words))])
    return places


# ---------------------------------------------------------------
# 3. Turn the street network into compact data for the browser
# ---------------------------------------------------------------
def build_data(G, places=None):
    nodes = ox.graph_to_gdfs(G, edges=False)
    edges = ox.graph_to_gdfs(G, nodes=False)

    node_ids = list(nodes.index)
    node_pos = {n: i for i, n in enumerate(node_ids)}
    node_coords = [[round(y, 5), round(x, 5)] for x, y in zip(nodes["x"], nodes["y"])]

    edge_list = []
    for (u, v, _key), row in edges.iterrows():
        cat = CAT_INDEX[classify(row)]
        coords = [[round(lat, 5), round(lon, 5)] for lon, lat in row["geometry"].coords]
        edge_list.append([node_pos[u], node_pos[v], round(float(row["length"]), 1), cat, coords])

    return {
        "center": list(CENTER),
        "categories": [{"name": n, "color": c, "penalty": p} for n, c, p in CATEGORIES],
        "nodes": node_coords,
        "edges": edge_list,
        "places": places or [],
    }


# ---------------------------------------------------------------
# 4. The web page: Leaflet map + routing code (JavaScript)
# ---------------------------------------------------------------
HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UT Austin Safe Bike Routes</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body { margin: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  #map { position: absolute; inset: 0; }
  #panel {
    position: absolute; top: 12px; left: 56px; z-index: 1000; width: 300px;
    background: #fff; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,.25);
    padding: 14px 16px; font-size: 14px; line-height: 1.45; color: #222;
  }
  #panel h1 { font-size: 17px; margin: 0 0 4px; }
  #hint { color: #555; margin: 0 0 10px; }
  .field { position: relative; display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
  .field input {
    flex: 1; min-width: 0; padding: 8px 10px; font-size: 14px;
    border: 1px solid #ccc; border-radius: 6px; outline: none;
  }
  .field input:focus { border-color: #0b6e4f; box-shadow: 0 0 0 2px rgba(11,110,79,.15); }
  .pin { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .pin-start { background: #fff; border: 3px solid #0b6e4f; }
  .pin-end { background: #c62828; }
  button.icon { flex: none; width: 34px; height: 34px; padding: 0; font-size: 16px; line-height: 1; }
  .sugg {
    display: none; position: absolute; left: 16px; right: 40px; top: 100%; z-index: 2000;
    background: #fff; border: 1px solid #ddd; border-radius: 6px; margin-top: 2px;
    box-shadow: 0 4px 12px rgba(0,0,0,.18); max-height: 260px; overflow-y: auto;
  }
  .sugg.open { display: block; }
  .sg-item { padding: 7px 10px; cursor: pointer; border-bottom: 1px solid #f0f0f0; }
  .sg-item:last-child { border-bottom: none; }
  .sg-item:hover, .sg-item.active { background: #eef6f2; }
  .sg-item.disabled { color: #999; cursor: default; background: none; }
  .sg-title { font-size: 14px; }
  .sg-detail { font-size: 12px; color: #777; }
  .sg-msg { padding: 8px 10px; font-size: 13px; color: #666; }
  .btns { display: flex; gap: 8px; margin: 8px 0; }
  button {
    flex: 1; padding: 7px 8px; border: 1px solid #ccc; border-radius: 6px;
    background: #f7f7f7; cursor: pointer; font-size: 13px;
  }
  button:hover { background: #eee; }
  button.primary { background: #0b6e4f; color: #fff; border-color: #0b6e4f; width: 100%; margin-top: 4px; font-weight: 600; }
  button.primary:hover { background: #095c42; }
  .route { border-left: 5px solid; padding: 4px 0 4px 10px; margin: 8px 0; }
  .route b { display: block; }
  .muted { color: #666; font-size: 13px; }
  .bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden; margin-top: 4px; background: #eee; }
  label { display: flex; align-items: center; gap: 6px; font-size: 13px; margin-top: 6px; }
  #legend { margin-top: 8px; font-size: 12px; display: none; }
  #legend div { display: flex; align-items: center; gap: 6px; }
  #legend span { display: inline-block; width: 14px; height: 4px; }
  @media (max-width: 600px) {
    #panel { left: 8px; right: 8px; top: auto; bottom: 18px; width: auto; }
  }
</style>
</head>
<body>
<div id="map"></div>
<div id="panel">
  <h1>Safe bike routes near UT</h1>
  <p id="hint">Search for a place, or click the map.</p>
  <div class="field">
    <span class="pin pin-start"></span>
    <input id="in-start" type="search" placeholder="Start: address, building, apartments…" autocomplete="off" spellcheck="false">
    <button id="locate" class="icon" title="Use my location" aria-label="Use my location">&#9678;</button>
    <div class="sugg" id="sg-start" role="listbox"></div>
  </div>
  <div class="field">
    <span class="pin pin-end"></span>
    <input id="in-end" type="search" placeholder="Destination" autocomplete="off" spellcheck="false">
    <button id="swap" class="icon" title="Swap start and destination" aria-label="Swap start and destination">&#8645;</button>
    <div class="sugg" id="sg-end" role="listbox"></div>
  </div>
  <div class="btns">
    <button id="reset">Reset</button>
  </div>
  <div id="results"></div>
  <label><input type="checkbox" id="showNet"> Show bike network colors</label>
  <div id="legend"></div>
</div>

<script>
const DATA = __DATA__;
const CATS = DATA.categories, NODES = DATA.nodes, EDGES = DATA.edges;
const FRIENDLY = new Set(["Protected / bike path", "Painted bike lane", "Quiet street"]);
const BIKE_MPH = 10;

// ---------- Map ----------
const map = L.map("map", { preferCanvas: true }).setView(DATA.center, 15);
L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
  { maxZoom: 19, attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors" }
).addTo(map);

// Outline of the area the router covers
const bounds = L.latLngBounds(NODES);
L.rectangle(bounds, { color: "#555", weight: 1, dashArray: "4 6", fill: false, interactive: false }).addTo(map);

// ---------- Optional bike-network layer ----------
const netLayer = L.layerGroup();
(function buildNetwork() {
  const seen = new Set();
  for (const e of EDGES) {
    const key = Math.min(e[0], e[1]) + "-" + Math.max(e[0], e[1]) + "-" + e[3];
    if (seen.has(key)) continue;
    seen.add(key);
    L.polyline(e[4], { color: CATS[e[3]].color, weight: 2, opacity: 0.6, interactive: false }).addTo(netLayer);
  }
  document.getElementById("legend").innerHTML = CATS.map(c =>
    `<div><span style="background:${c.color}"></span>${c.name}</div>`).join("");
})();
document.getElementById("showNet").addEventListener("change", ev => {
  const on = ev.target.checked;
  if (on) netLayer.addTo(map); else map.removeLayer(netLayer);
  document.getElementById("legend").style.display = on ? "block" : "none";
  if (on) bringRoutesToFront();
});

// ---------- Graph ----------
const adj = NODES.map(() => []);
EDGES.forEach((e, i) => adj[e[0]].push(i));

class MinHeap {
  constructor() { this.a = []; }
  get size() { return this.a.length; }
  push(item) {
    const a = this.a; a.push(item);
    let i = a.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (a[p][0] <= a[i][0]) break;
      [a[p], a[i]] = [a[i], a[p]]; i = p;
    }
  }
  pop() {
    const a = this.a, top = a[0], last = a.pop();
    if (a.length) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < a.length && a[l][0] < a[m][0]) m = l;
        if (r < a.length && a[r][0] < a[m][0]) m = r;
        if (m === i) break;
        [a[m], a[i]] = [a[i], a[m]]; i = m;
      }
    }
    return top;
  }
}

// Dijkstra's algorithm. Returns the list of edge indices on the cheapest path.
function findRoute(start, goal, costFn) {
  const dist = new Float64Array(NODES.length).fill(Infinity);
  const prevEdge = new Int32Array(NODES.length).fill(-1);
  const heap = new MinHeap();
  dist[start] = 0; heap.push([0, start]);
  while (heap.size) {
    const [d, n] = heap.pop();
    if (n === goal) break;
    if (d > dist[n]) continue;
    for (const ei of adj[n]) {
      const e = EDGES[ei], nd = d + costFn(e);
      if (nd < dist[e[1]]) { dist[e[1]] = nd; prevEdge[e[1]] = ei; heap.push([nd, e[1]]); }
    }
  }
  if (start !== goal && prevEdge[goal] === -1) return null;
  const path = [];
  for (let n = goal; n !== start; n = EDGES[prevEdge[n]][0]) path.push(prevEdge[n]);
  return path.reverse();
}

const safestCost  = e => e[2] * CATS[e[3]].penalty;
const shortestCost = e => e[2];

function nearestNode(latlng) {
  const cos = Math.cos(latlng.lat * Math.PI / 180);
  let best = -1, bestD = Infinity;
  for (let i = 0; i < NODES.length; i++) {
    const dy = NODES[i][0] - latlng.lat, dx = (NODES[i][1] - latlng.lng) * cos;
    const d = dy * dy + dx * dx;
    if (d < bestD) { bestD = d; best = i; }
  }
  return { node: best, meters: Math.sqrt(bestD) * 111320 };
}

// ---------- Google Maps hand-off ----------
// Google Maps plans each leg between stops on its own, using its usual
// preferred (roughly shortest) path. If a stop sits where Google's preferred
// path to the NEXT stop goes back the way it came, you get an out-and-back
// spur. So we simulate Google before sending anything:
//
//   From the current point, follow the safe route as far as a plain
//   shortest-path router would ALSO go. Put a stop just before the two
//   would split, then repeat from that stop.
//
// Every leg is then a path a shortest-path router follows forward, so
// Google has no reason to turn around. Stops go mid-block on bike-friendly
// streets so Google can't snap them to a cross street or a busy road.
// If there are more stops than one Google link allows, the trip is split
// into parts instead of dropping stops.
const IS_PHONE = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
const STOPS_PER_LINK = IS_PHONE ? 3 : 8;   // Google allows fewer stops on phones
const MIN_STOP_EDGE_M = 100;               // prefer blocks at least this long for stops
const MARGIN_FRAC = 0.8;                   // a U-turn must cost Google this much of the block extra
const LOOKAHEAD_M = 400;                   // how far ahead to check when leaving a stop
const MATCH_TOLERANCE_M = 2;               // rounding slack when comparing distances
const GOOD_STOP = new Set(["Protected / bike path", "Painted bike lane", "Quiet street"]);

// Shortest plain distance from one intersection to every other (up to maxDist)
function distancesFrom(start, maxDist) {
  const dist = new Float64Array(NODES.length).fill(Infinity);
  const heap = new MinHeap();
  dist[start] = 0; heap.push([0, start]);
  while (heap.size) {
    const [d, n] = heap.pop();
    if (d > dist[n]) continue;
    if (d > maxDist) break;
    for (const ei of adj[n]) {
      const e = EDGES[ei], nd = d + e[2];
      if (nd < dist[e[1]]) { dist[e[1]] = nd; heap.push([nd, e[1]]); }
    }
  }
  return dist;
}

// Returns { stops: [segment indices into the route], approximate: bool }.
//
// A stop sits mid-block on one route segment. Google treats it as a place
// it must touch, and Google scores streets a bit differently than we do.
// So a stop is only safe where riding through it FORWARD is clearly better
// for Google than any way of touching it and turning back:
//   * arriving: reaching the block's far end and riding back in must cost
//     clearly more than arriving from its near end,
//   * leaving: turning around after the stop must cost clearly more than
//     continuing along the route,
//   * in between: the safe route must be Google's natural path, and turning
//     back at the previous stop must never be a shortcut.
// "Clearly more" means a big part of the stop's block length (MARGIN_FRAC),
// so small differences in how Google weighs streets can't flip the choice.
function planStops(route) {
  const n = route.length;
  const len = k => EDGES[route[k]][2];
  const destNode = EDGES[route[n - 1]][1];
  const stops = [];
  let a = -1, approximate = false;            // a = -1 means "at the start point"

  for (;;) {
    const fwdSrc = a < 0 ? EDGES[route[0]][0] : EDGES[route[a]][1];   // leaving forward
    const backSrc = a < 0 ? -1 : EDGES[route[a]][0];                  // turning back
    const uturnMargin = a < 0 ? 0 : MARGIN_FRAC * len(a);
    let remaining = 0;
    for (let k = a + 1; k < n; k++) remaining += len(k);
    const dF = distancesFrom(fwdSrc, remaining + 50);
    const dB = backSrc < 0 ? null : distancesFrom(backSrc, remaining + 50 + len(a));

    // Is following the safe route to `node` Google's natural choice from here?
    const followsRoute = (node, inner) =>
      inner <= dF[node] + MATCH_TOLERANCE_M &&
      (!dB || dB[node] >= inner + uturnMargin - MATCH_TOLERANCE_M);
    const quickest = node => dB ? Math.min(dF[node], dB[node]) : dF[node];

    if (followsRoute(destNode, remaining)) break;   // Google can finish from here

    // Candidate blocks for the next stop, in route order
    const cands = [];
    let inner = 0;
    for (let b = a + 1; b < n; b++) {
      const e = EDGES[route[b]];
      if (!followsRoute(e[0], inner)) break;
      const arrivesRightWay = quickest(e[1]) >= inner + MARGIN_FRAC * e[2] - MATCH_TOLERANCE_M;
      if (arrivesRightWay) cands.push(b);
      inner += e[2];
    }

    // Prefer the farthest robust stop on a long bike-friendly block
    const goodBlock = b => GOOD_STOP.has(CATS[EDGES[route[b]][3]].name) && len(b) >= MIN_STOP_EDGE_M;
    let s = -1;
    for (let i = cands.length - 1; i >= 0 && s < 0; i--) if (goodBlock(cands[i]) && leavesRightWay(route, cands[i])) s = cands[i];
    for (let i = cands.length - 1; i >= 0 && s < 0; i--) if (leavesRightWay(route, cands[i])) s = cands[i];
    if (s < 0 && cands.length) { s = cands[cands.length - 1]; approximate = true; }
    if (s < 0) { s = a + 1; approximate = true; }
    if (s >= n) break;
    stops.push(s);
    a = s;
  }
  return { stops, approximate };
}

// After a stop on block b, is continuing forward clearly better than turning around?
function leavesRightWay(route, b) {
  const e = EDGES[route[b]];
  let along = 0, k = b + 1;
  while (k < route.length && along < LOOKAHEAD_M) { along += EDGES[route[k]][2]; k++; }
  if (k === b + 1) return true;                        // stop is on the last block
  const target = EDGES[route[k - 1]][1];
  const fromNearEnd = distancesFrom(e[0], along + e[2] + 50);
  return fromNearEnd[target] >= along + MARGIN_FRAC * e[2] - MATCH_TOLERANCE_M;
}

const edgeKey = e => Math.min(e[0], e[1]) + "-" + Math.max(e[0], e[1]);

// The point halfway along a street segment's actual shape
function edgeMidpoint(e) {
  const c = e[4];
  if (c.length < 2) return c[0];
  const cos = Math.cos(c[0][0] * Math.PI / 180);
  const seg = [];
  let tot = 0;
  for (let i = 0; i < c.length - 1; i++) {
    const d = Math.hypot(c[i + 1][0] - c[i][0], (c[i + 1][1] - c[i][1]) * cos);
    seg.push(d); tot += d;
  }
  let half = tot / 2;
  for (let i = 0; i < seg.length; i++) {
    if (half <= seg[i]) {
      const t = seg[i] ? half / seg[i] : 0;
      return [c[i][0] + (c[i + 1][0] - c[i][0]) * t, c[i][1] + (c[i + 1][1] - c[i][1]) * t];
    }
    half -= seg[i];
  }
  return c[c.length - 1];
}

function googleMapsUrl(origin, waypoints, destination) {
  const fmt = p => p[0].toFixed(6) + "," + p[1].toFixed(6);
  const params = new URLSearchParams({
    api: "1",
    origin: fmt(origin),
    destination: fmt(destination),
    travelmode: "bicycling",
  });
  if (waypoints.length) params.set("waypoints", waypoints.map(fmt).join("|"));
  return "https://www.google.com/maps/dir/?" + params.toString();
}

// One link if the stops fit, otherwise Part 1, Part 2, ...
function googleLinks(stopPoints) {
  const pts = [NODES[startNode], ...stopPoints, NODES[endNode]];
  const links = [];
  let a = 0;
  while (a < pts.length - 1) {
    const b = Math.min(a + STOPS_PER_LINK + 1, pts.length - 1);
    links.push(googleMapsUrl(pts[a], pts.slice(a + 1, b), pts[b]));
    a = b;
  }
  return links;
}

// ---------- Route drawing & stats ----------
let startMarker = null, endMarker = null, startNode = null, endNode = null;
const routeLayers = [];

function clearRoutes() { routeLayers.forEach(l => map.removeLayer(l)); routeLayers.length = 0; }
function bringRoutesToFront() { routeLayers.forEach(l => l.bringToFront && l.bringToFront()); }

function routeLine(path) {
  const pts = [];
  for (const ei of path) {
    const c = EDGES[ei][4];
    pts.push(...(pts.length ? c.slice(1) : c));
  }
  return pts;
}

function stats(path) {
  const byCat = new Array(CATS.length).fill(0);
  let total = 0;
  for (const ei of path) { const e = EDGES[ei]; byCat[e[3]] += e[2]; total += e[2]; }
  let friendly = 0;
  CATS.forEach((c, i) => { if (FRIENDLY.has(c.name)) friendly += byCat[i]; });
  const noFacility = byCat[CATS.findIndex(c => c.name === "No bike facility")];
  return { total, byCat, friendly, noFacility };
}

function summaryHTML(title, color, s) {
  const miles = s.total / 1609.34;
  const mins = Math.max(1, Math.round(miles / BIKE_MPH * 60));
  const pct = x => s.total ? Math.round(100 * x / s.total) : 0;
  const bar = CATS.map((c, i) => s.byCat[i] ?
    `<div title="${c.name}" style="width:${100 * s.byCat[i] / s.total}%;background:${c.color}"></div>` : "").join("");
  return `<div class="route" style="border-color:${color}">
      <b>${title}: ${miles.toFixed(2)} mi &middot; ~${mins} min</b>
      <span class="muted">${pct(s.friendly)}% bike-friendly &middot; ${pct(s.noFacility)}% on roads with no bike lane</span>
      <div class="bar">${bar}</div>
    </div>`;
}

function update() {
  clearRoutes();
  const res = document.getElementById("results");
  if (startNode === null || endNode === null) { res.innerHTML = ""; return; }
  if (startNode === endNode) {
    res.innerHTML = `<p class="muted">Your start and destination are the same spot. Pick a different destination.</p>`;
    return;
  }

  const safe = findRoute(startNode, endNode, safestCost);
  const fast = findRoute(startNode, endNode, shortestCost);
  if (!safe || !fast) {
    res.innerHTML = `<p class="muted">No bike route found between those points. Try moving a marker onto a nearby street.</p>`;
    return;
  }

  const fastLine = L.polyline(routeLine(fast), { color: "#555", weight: 4, opacity: 0.8, dashArray: "6 8" }).addTo(map);
  const safeHalo = L.polyline(routeLine(safe), { color: "#fff", weight: 9, opacity: 0.9 }).addTo(map);
  const safeLine = L.polyline(routeLine(safe), { color: "#0b6e4f", weight: 6, opacity: 1 }).addTo(map);
  routeLayers.push(fastLine, safeHalo, safeLine);
  map.fitBounds(safeLine.getBounds().extend(fastLine.getBounds()), { padding: [60, 60] });

  const sSafe = stats(safe), sFast = stats(fast);
  let html = summaryHTML("Safest route", "#0b6e4f", sSafe);
  if (Math.abs(sSafe.total - sFast.total) < 1) {
    html += `<p class="muted">The shortest route is also the safest one here.</p>`;
  } else {
    html += summaryHTML("Shortest route", "#555", sFast);
    const extra = ((sSafe.total - sFast.total) / 1609.34).toFixed(2);
    html += `<p class="muted">The safe route adds ${extra} mi to avoid busier roads.</p>`;
  }

  const plan = planStops(safe);
  const stopPoints = plan.stops.map(k => edgeMidpoint(EDGES[safe[k]]));
  const links = googleLinks(stopPoints);
  stopPoints.forEach((p, i) => {
    routeLayers.push(L.circleMarker(p, { radius: 6, color: "#0b6e4f", weight: 3, fillColor: "#fff", fillOpacity: 1 })
      .bindTooltip(`Google Maps stop ${i + 1}`).addTo(map));
  });
  if (links.length === 1) {
    html += `<button class="primary gmaps" data-i="0">Open safe route in Google Maps</button>`;
  } else {
    html += `<p class="muted" style="margin-bottom:2px">Google Maps only takes ${STOPS_PER_LINK} stops per trip, so this route opens in ${links.length} parts. Start Part 2 when Part 1 ends.</p>`;
    html += links.map((_, i) => `<button class="primary gmaps" data-i="${i}">Google Maps &middot; Part ${i + 1} of ${links.length}</button>`).join("");
  }
  html += `<p class="muted">${stopPoints.length
      ? `${stopPoints.length} stop${stopPoints.length > 1 ? "s" : ""} (white dots) keep Google on this route.`
      : "Google's own directions already match this route."}</p>`;
  res.innerHTML = html;
  res.querySelectorAll(".gmaps").forEach(btn => btn.addEventListener("click", () => {
    window.open(links[+btn.dataset.i], "_blank", "noopener");
  }));
}

// ---------- Start / destination ----------
const points = { start: null, end: null };   // { latlng, label } for each
const inputs = { start: document.getElementById("in-start"), end: document.getElementById("in-end") };

function setHint() {
  document.getElementById("hint").innerHTML =
    !points.start ? "Search for your <b>start</b>, or click the map." :
    !points.end   ? "Now search for your <b>destination</b>, or click the map." :
                    "Drag either marker to adjust, or click <b>Reset</b>.";
}

// Put the start or destination at a spot. Returns false if it's outside the mapped area.
function placePoint(latlng, which, label) {
  const snap = nearestNode(latlng);
  if (snap.meters > 400) {
    document.getElementById("hint").innerHTML =
      "That place is outside the area this map covers (dashed box). Pick something closer to campus.";
    return false;
  }
  const snapped = L.latLng(NODES[snap.node]);
  points[which] = { latlng: L.latLng(latlng), label: label || "Pin on map" };
  inputs[which].value = points[which].label;

  if (which === "start") {
    startNode = snap.node;
    if (startMarker) startMarker.setLatLng(snapped);
    else {
      startMarker = L.marker(snapped, { draggable: true, title: "Start" }).addTo(map)
        .bindTooltip("Start", { permanent: true, direction: "top", offset: [-15, -12] });
      startMarker.on("dragend", ev => placePoint(ev.target.getLatLng(), "start"));
    }
  } else {
    endNode = snap.node;
    if (endMarker) endMarker.setLatLng(snapped);
    else {
      endMarker = L.marker(snapped, { draggable: true, title: "Destination" }).addTo(map)
        .bindTooltip("Destination", { permanent: true, direction: "top", offset: [-15, -12] });
      endMarker.on("dragend", ev => placePoint(ev.target.getLatLng(), "end"));
    }
  }
  setHint();
  if (startNode === null || endNode === null) map.panTo(snapped);
  update();
  return true;
}

function clearPoint(which) {
  if (which === "start") { if (startMarker) map.removeLayer(startMarker); startMarker = null; startNode = null; }
  else { if (endMarker) map.removeLayer(endMarker); endMarker = null; endNode = null; }
  points[which] = null;
  inputs[which].value = "";
}

map.on("click", ev => {
  if (startNode === null) placePoint(ev.latlng, "start");
  else if (endNode === null) placePoint(ev.latlng, "end");
});

function reset() {
  clearRoutes();
  clearPoint("start"); clearPoint("end");
  document.getElementById("results").innerHTML = "";
  setHint();
}
document.getElementById("reset").addEventListener("click", reset);

document.getElementById("swap").addEventListener("click", () => {
  const s = points.start, e = points.end;
  clearRoutes(); clearPoint("start"); clearPoint("end");
  document.getElementById("results").innerHTML = "";
  if (e) placePoint(e.latlng, "start", e.label);
  if (s) placePoint(s.latlng, "end", s.label);
  setHint();
});

document.getElementById("locate").addEventListener("click", () => {
  const hint = document.getElementById("hint");
  if (!navigator.geolocation) { hint.textContent = "Your browser doesn't support location."; return; }
  hint.textContent = "Finding your location...";
  navigator.geolocation.getCurrentPosition(
    pos => placePoint(L.latLng(pos.coords.latitude, pos.coords.longitude), "start", "My location"),
    () => { hint.innerHTML = "Couldn't get your location. Search for your <b>start</b> or click the map instead."; },
    { enableHighAccuracy: true, timeout: 10000 }
  );
});

// ---------- Place search (type-ahead) ----------
// Two sources, merged:
//  1. LOCAL: every named place around campus (shops, cafes, UT buildings,
//     apartments, parks...) saved into this page with keywords, so "coffee",
//     "grocery" or "gym" work, and typos like "gregroy gym" still match.
//     Instant, no internet request.
//  2. PHOTON: free OpenStreetMap search for street addresses and anything
//     not in the local list. If it can't be reached, Enter falls back to
//     OpenStreetMap's own search (Nominatim), which doesn't allow type-ahead.
const AREA = bounds.pad(0.5);                 // search a bit beyond the routable area
const MAX_RESULTS = 8;

function inArea(lat, lon) { return bounds.pad(0.05).contains([lat, lon]); }

const normText = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
                       .replace(/['’]/g, "").replace(/&/g, " and ");
const tokenize = s => normText(s).split(/[^a-z0-9]+/).filter(Boolean);
const squash = s => normText(s).replace(/[^a-z0-9]/g, "");     // "H-E-B" -> "heb"


// Is a within `max` typos of b? A typo = one wrong, missing, or extra letter,
// or two neighboring letters swapped ("gregroy" -> "gregory" is one typo).
function closeEnough(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return false;
  let prev2 = null, prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let rowMin = i;
    for (let j = 1; j <= b.length; j++) {
      let v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (prev2 && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, prev2[j - 2] + 1);
      cur[j] = v;
      rowMin = Math.min(rowMin, v);
    }
    if (rowMin > max) return false;
    prev2 = prev; prev = cur;
  }
  return prev[b.length] <= max;
}
const typoAllowance = q => q.length >= 8 ? 2 : q.length >= 4 ? 1 : 0;

// Common abbreviations people type -> the word places actually use
const ABBREVIATIONS = {
  apts: "apartments", apt: "apartments", st: "street", ave: "avenue", av: "avenue", blvd: "boulevard",
  dr: "drive", ln: "lane", rd: "road", pkwy: "parkway", ctr: "center", cntr: "center", centre: "center",
  univ: "university", rec: "recreation", lib: "library", bldg: "building", mkt: "market",
  intl: "international", natl: "national", hosp: "hospital", n: "north", s: "south", e: "east", w: "west",
};

// Search index: every distinct word gets an id, and each place stores the
// ids of its name words and keyword words. Typing then checks each DISTINCT
// word once (thousands) instead of every word of every place (much more),
// which keeps search instant even with many thousands of places.
const VOCAB = [], VOCAB_ID = new Map();
const wordId = t => { let id = VOCAB_ID.get(t); if (id === undefined) { id = VOCAB.length; VOCAB.push(t); VOCAB_ID.set(t, id); } return id; };
const PLACE_INDEX = (DATA.places || []).map(p => ({
  title: p[0], detail: p[1], lat: p[2], lon: p[3], nameSquashed: squash(p[0]),
  nameIds: Uint32Array.from(new Set(tokenize(p[0]).map(wordId))),
  keyIds: Uint32Array.from(new Set(tokenize(p[4]).map(wordId))),
}));

// Score every distinct word against one typed word: [nameScores, keywordScores]
function scoreVocab(q, isLastWord) {
  const nameS = new Float32Array(VOCAB.length), keyS = new Float32Array(VOCAB.length);
  const forms = [q];
  if (ABBREVIATIONS[q]) forms.push(ABBREVIATIONS[q]);
  for (const f of forms) {
    const allow = typoAllowance(f);
    for (let id = 0; id < VOCAB.length; id++) {
      const t = VOCAB[id];
      let n = 0, k = 0;
      if (t === f) { n = 3; k = 2; }
      else if (isLastWord && t.startsWith(f)) { n = 2.5; if (f.length >= 3) k = 1.5; }      // still typing
      else {
        if (f.length >= 3 && t.includes(f)) n = 1.5;
        if (allow && Math.abs(t.length - f.length) <= allow && closeEnough(f, t, allow)) { n = Math.max(n, 1.3); if (f.length >= 5) k = 1; }
        else if (!n && isLastWord && allow && t.length > f.length && closeEnough(f, t.slice(0, f.length), 1)) n = 1.0;
      }
      if (n > nameS[id]) nameS[id] = n;
      if (k > keyS[id]) keyS[id] = k;
    }
  }
  return [nameS, keyS];
}

function localSearch(query) {
  const words = tokenize(query), whole = squash(query);
  if (!words.length || !PLACE_INDEX.length) return [];
  const tables = words.map((q, i) => scoreVocab(q, i === words.length - 1));
  const center = bounds.getCenter();
  const scored = [];
  for (const p of PLACE_INDEX) {
    let score = 0;
    if (whole.length >= 2 && p.nameSquashed.startsWith(whole)) score += 4;      // "heb" -> "H-E-B"
    else if (whole.length >= 4 && p.nameSquashed.includes(whole)) score += 2;
    let sum = 0, allWords = true;
    for (const [nameS, keyS] of tables) {
      let best = 0;
      for (const id of p.nameIds) if (nameS[id] > best) best = nameS[id];
      for (const id of p.keyIds) if (keyS[id] > best) best = keyS[id];
      if (!best) { allWords = false; break; }
      sum += best;
    }
    if (allWords) score += sum;
    if (!score) continue;
    // Small nudge toward places nearer the middle of the map
    const km = center.distanceTo([p.lat, p.lon]) / 1000;
    scored.push({ p, score: score - 0.05 * km });
  }
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, MAX_RESULTS).map(({ p }) => ({ title: p.title, detail: p.detail, lat: p.lat, lon: p.lon, inside: true }));
}

function dedupe(items) {
  const kept = [];
  for (const it of items) {
    const dup = kept.some(k =>
      (squash(k.title) === squash(it.title) && L.latLng(k.lat, k.lon).distanceTo([it.lat, it.lon]) < 150) ||
      (k.title === it.title && k.detail === it.detail));
    if (!dup) kept.push(it);
  }
  return kept;
}

async function photonSearch(q, signal) {
  const c = bounds.getCenter();
  const params = new URLSearchParams({
    q, limit: "8", lang: "en", lat: c.lat.toFixed(5), lon: c.lng.toFixed(5), zoom: "13",
    bbox: [AREA.getWest(), AREA.getSouth(), AREA.getEast(), AREA.getNorth()].map(v => v.toFixed(5)).join(","),
  });
  const res = await fetch("https://photon.komoot.io/api/?" + params, { signal });
  if (!res.ok) throw new Error("Photon HTTP " + res.status);
  const json = await res.json();
  return json.features.map(f => {
    const p = f.properties, [lon, lat] = f.geometry.coordinates;
    const street = p.street ? (p.housenumber ? p.housenumber + " " + p.street : p.street) : "";
    const place = [street, p.city || p.district || p.county].filter(Boolean).join(", ");
    const title = p.name || street || place || "Unnamed place";
    const detail = p.name ? place : [p.city, p.postcode].filter(Boolean).join(" ");
    return { title, detail, lat, lon, inside: inArea(lat, lon) };
  });
}

async function nominatimSearch(q) {
  const params = new URLSearchParams({
    q, format: "jsonv2", limit: "6", bounded: "1",
    viewbox: [AREA.getWest(), AREA.getNorth(), AREA.getEast(), AREA.getSouth()].map(v => v.toFixed(5)).join(","),
  });
  const res = await fetch("https://nominatim.openstreetmap.org/search?" + params);
  if (!res.ok) throw new Error("Nominatim HTTP " + res.status);
  const json = await res.json();
  return json.map(r => {
    const parts = r.display_name.split(", ");
    const lat = +r.lat, lon = +r.lon;
    return { title: r.name || parts[0], detail: parts.slice(1, 3).join(", "), lat, lon, inside: inArea(lat, lon) };
  });
}

function setupSearch(which) {
  const input = inputs[which];
  const box = document.getElementById(which === "start" ? "sg-start" : "sg-end");
  let timer = null, controller = null, items = [], active = -1, photonDown = false, shownFor = "";

  const open = () => box.classList.add("open");
  const close = () => { box.classList.remove("open"); active = -1; };
  const esc = s => s.replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

  // Show a list of results (plus an optional status line under them)
  function show(list, q, note) {
    items = dedupe(list).slice(0, MAX_RESULTS);
    shownFor = q;
    if (active < 0 || active >= items.length || !items[active].inside) active = items.findIndex(it => it.inside);
    const rows = items.map((it, i) => `
      <div class="sg-item${it.inside ? "" : " disabled"}${i === active ? " active" : ""}" data-i="${i}" role="option">
        <div class="sg-title">${esc(it.title)}</div>
        <div class="sg-detail">${it.inside ? esc(it.detail) : "Outside the mapped area"}</div>
      </div>`).join("");
    const msg = note || (items.length ? "" : "No matching places near campus. Try a street address or another word.");
    box.innerHTML = rows + (msg ? `<div class="sg-msg">${msg}</div>` : "");
    open();
  }

  function choose(it) {
    if (!it || !it.inside) return;
    close();
    input.blur();
    placePoint(L.latLng(it.lat, it.lon), which, it.title);
  }

  // Ask Photon (or Nominatim) and merge with the local results already shown
  async function remote(q, useFallback) {
    if (controller) controller.abort();
    controller = new AbortController();
    const local = localSearch(q);
    let found;
    try {
      found = useFallback ? await nominatimSearch(q) : await photonSearch(q, controller.signal);
      photonDown = false;
    } catch (err) {
      if (err.name === "AbortError") return;
      if (q !== input.value.trim()) return;
      if (!useFallback) photonDown = true;
      show(local, q, useFallback
        ? "Address search isn't reachable right now."
        : "Address suggestions unavailable. Press <b>Enter</b> to search addresses.");
      return;
    }
    if (q !== input.value.trim()) return;      // a newer search is on its way
    show([...local, ...found], q);
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    if (controller) controller.abort();
    const q = input.value.trim();
    if (q.length < 2) { close(); items = []; shownFor = ""; return; }
    const local = localSearch(q);              // instant
    active = -1;
    if (q.length < 3) { if (local.length) show(local, q); else close(); return; }
    if (photonDown) { show(local, q, "Press <b>Enter</b> to also search addresses."); return; }
    show(local, q, local.length ? "" : "Searching…");
    timer = setTimeout(() => remote(q, false), 300);
  });

  input.addEventListener("keydown", ev => {
    const usable = items.map((it, i) => it.inside ? i : -1).filter(i => i >= 0);
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      if (!usable.length) return;
      ev.preventDefault();
      const pos = usable.indexOf(active);
      active = usable[(pos + (ev.key === "ArrowDown" ? 1 : -1) + usable.length) % usable.length];
      show(items, shownFor);
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      const q = input.value.trim();
      if (q.length < 2) return;
      // Pick the highlighted result; if there's nothing to pick, run a full search
      if (box.classList.contains("open") && active >= 0 && q === shownFor) choose(items[active]);
      else { clearTimeout(timer); remote(q, photonDown); }
    } else if (ev.key === "Escape") {
      close();
    }
  });

  // Picking a suggestion (mousedown fires before the input loses focus)
  box.addEventListener("mousedown", ev => {
    const el = ev.target.closest(".sg-item");
    if (!el) return;
    ev.preventDefault();
    choose(items[+el.dataset.i]);
  });

  input.addEventListener("focus", () => { if (points[which]) input.select(); });
  input.addEventListener("blur", () => {
    setTimeout(close, 120);
    // If they typed but didn't pick anything, show the current place again
    if (points[which]) input.value = points[which].label;
  });
  input.addEventListener("search", () => {            // the little "x" clears the point
    if (!input.value && points[which]) { clearRoutes(); clearPoint(which); document.getElementById("results").innerHTML = ""; setHint(); }
  });
}
setupSearch("start");
setupSearch("end");

// Keep map clicks from passing through the panel
L.DomEvent.disableClickPropagation(document.getElementById("panel"));
L.DomEvent.disableScrollPropagation(document.getElementById("panel"));
</script>
</body>
</html>
"""


def main():
    CYCLE_TAGS = CYCLEWAY_COLS + ["bicycle"]
    ox.settings.useful_tags_way = list(ox.settings.useful_tags_way) + CYCLE_TAGS

    print(f"Route finder version {VERSION}")
    print(f"Downloading bike network within {RADIUS_M} m of campus (can take 1-2 minutes)...")
    G = ox.graph_from_point(CENTER, dist=RADIUS_M, network_type="bike")
    print(f"Got {len(G.nodes)} intersections and {len(G.edges)} road segments.")

    print("Downloading named places for search (shops, cafes, buildings)...")
    places = build_places()
    print(f"Got {len(places)} searchable places.")
    data = build_data(G, places)
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    size_mb = len(html.encode("utf-8")) / 1_000_000
    print(f"Saved {OUTPUT_FILE} ({size_mb:.1f} MB). Open it in your browser.")


if __name__ == "__main__":
    main()
