# UT Austin Bike Safety Map

An interactive map that color-codes every bikeable street around the University of Texas at Austin by how safe its bike infrastructure is, from protected bike paths down to busy roads with no bike lane at all.

![Bike safety map of the UT Austin area](screenshot.png)

## Why I built this

I get around Austin by bike and scooter, both to class and to get groceries. Navigation apps show the fastest route, not the safest one, and a "bike route" can mean anything from a separated path to a painted line next to fast traffic. I wanted one map that shows, at a glance, which streets are actually comfortable to ride.

## How it works

1. **Downloads the street network** around campus from [OpenStreetMap](https://www.openstreetmap.org) using [OSMnx](https://github.com/gboeing/osmnx).
2. **Classifies each road segment** using OpenStreetMap's bike tags (`cycleway`, `cycleway:left/right/both`, `bicycle`) and road type (`highway`).
3. **Draws an interactive map** with [Folium](https://python-visualization.github.io/folium/) (Leaflet), with toggleable layers, hover tooltips showing the street name and category, and a legend.

| Color | Category | What it means |
|---|---|---|
| Dark green | Protected / bike path | Dedicated bike path or physically separated lane |
| Light green | Painted bike lane | Bike lane painted on the road |
| Blue | Quiet street | Low-traffic residential street |
| Orange | Shared lane | Bikes share the travel lane with cars ("sharrows") |
| Red | No bike facility | Through-road with no bike infrastructure |
| Gray | Sidewalk / footpath | Walkways and campus paths |
| Light gray | Alley / parking lot | Service roads, driveways, parking aisles |

## Run it yourself

Requires Python 3.

```bash
pip3 install osmnx folium
python3 bike_map.py
open bike_map.html        # macOS; on Windows just double-click the file
```

To map a different area, change `CENTER` (latitude, longitude) and `RADIUS_M` (meters) at the top of `bike_map.py`.

## Roadmap

- [x] **v1:** Color-coded bike infrastructure map of the UT area
- [ ] **v2:** Bike crash hotspot layer from Texas crash records
- [ ] **v3:** Time-of-day traffic layer
- [ ] **v4:** Safest-route finder between two points

## Known limitations

OpenStreetMap is volunteer-maintained, so some streets may be mislabeled or out of date. I'm checking the map against routes I ride and correcting the classification logic as I go.

## Data and credits

Street data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). Background tiles © Esri.
