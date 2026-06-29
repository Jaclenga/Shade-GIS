# Shade Study Builder

Streamlit platform for preparing reusable, city-wide bus stop shade studies from GTFS or CSV stop datasets. The app helps researchers, transit agencies, and municipalities configure project metadata, upload or map transit data, choose shade taxonomy and visualization settings, edit public methodology copy, and preview the resulting public Streamlit app.

The repository still includes the Tampa/HART stop and shade files as a starter project, but the app is no longer hard-coded as a Tampa-only viewer.

## What it does

- Starts with the bundled Tampa/HART dataset, or lets you upload a GTFS `.zip`, `stops.txt`, or custom bus-stop CSV.
- Provides CSV field mapping for required stop fields: `stop_id`, `stop_name`, `stop_lat`, and `stop_lon`.
- Extracts route labels from GTFS uploads when `stop_times.txt`, `trips.txt`, and `routes.txt` are present.
- Tracks project metadata, source name, license, source URL, dataset version, methodology version, owners, and visibility.
- Lets project teams edit the shade taxonomy, including category names, definitions, display colors, and sort order.
- Lets project teams choose map coloring, contextual overlays, dashboard summaries, and priority-score weights.
- Provides an editable rationale/about page for methodology, data sources, contributors, citations, limitations, and release history.
- Previews the public Streamlit app with a map, analytics, methodology page, import log, and CSV/GeoJSON/config downloads.

## App Pages

- `Data`: project setup, upload/import workflow, CSV field mapping, shade taxonomy, source metadata, and dataset health checks.
- `Visuals`: map color fields and palettes, marker shape/size/outline controls, base map style, overlay selection, dashboard metrics, priority formula controls, and map preview.
- `Methodology`: editable public rationale/about page with live preview.
- `Preview`: the generated public-facing Streamlit app experience for the current project configuration.

## Supported Input Schema

Required stop fields:

| Field | Description |
| --- | --- |
| `stop_id` | Unique stop identifier, usually from GTFS. |
| `stop_name` | Public stop name. |
| `stop_lat` | Stop latitude in WGS84. |
| `stop_lon` | Stop longitude in WGS84. |

Optional fields recognized by the builder include `agency`, `routes`, `municipality`, `shading`, `shade_coverage`, `shade_sources`, `review_status`, `confidence`, `ridership`, `heat_vulnerability_index`, `heat_vulnerability_label`, `tree_canopy_pct`, and `lst_median`.

## Platform Direction

The current app is an MVP for the reusable platform described in the project issue. It establishes the project builder workflow and public preview surface. Future work can add persistent multi-project storage, image uploads, raw label history, reviewer roles, agreement metrics, richer GIS overlays, and API-backed publishing.

See `docs/platform_schema.md` for the current project, stop, taxonomy, export, and future-entity schema notes. The repository also includes `CITATION.cff` as a starter citation file for publication workflows.

## Bundled Tampa Starter Study

The bundled starter project focuses on visualizing bus stop shading to provide better insights on Tampa's transport. The app uses GTFS stop locations and existing shade fields to seed the builder with a real city-wide example.

Classifications were based on visible shade coverage of the waiting area in available imagery rather than the mere presence of nearby vegetation or structures. This is especially important with Street View winter imagery: code what visibly shades the waiting area, not what might shade it at another time.

Waiting area: The space where a passenger would reasonably stand or sit while waiting for transit, including benches when present.

Map tooltips now focus on four heat-exposure variables that best support the project story: the county's weighted heat vulnerability index, the vulnerability category label, tree canopy percentage, and median land surface temperature. The app also summarizes these fields by shading category and highlights high-priority stops where low shade and high heat exposure overlap.

Main dataset fields used in the app:
- `shade_coverage`: observed or voted amount of shade reaching the waiting area, using no shade, limited, significant, or unknown.
- `shade_sources`: observed or voted source labels for shade reaching the waiting area. This can hold multiple labels, such as `Natural; Constructed; Manmade`, when more than one source visibly shades riders.
- `shading`: derived map label for the stop itself, using no shade, limited natural shade, significant natural shade, constructed shade, manmade shade, or unknown.
- `heat_vulnerability_index`: the county's weighted heat-vulnerability score for the surrounding block group; higher values mean greater relative vulnerability.
- `heat_vulnerability_label`: the category label paired with the weighted HVI score, making the map easier to read at a glance.
- `tree_canopy_pct`: estimated tree canopy share in the surrounding block group; lower values can suggest less natural cooling and less nearby shade context.
- `lst_median`: median land surface temperature in the surrounding block group; higher values suggest hotter nearby surfaces and stronger heat exposure.

Heat vulnerability source:
`Hillsborough County. (n.d.). Heat Vulnerability Index [Feature layer]. ArcGIS Feature Server. Retrieved June 20, 2026, from https://services1.arcgis.com/IbNXlmt2RVVRCZ6M/arcgis/rest/services/HeatVulnerabilityIndex/FeatureServer`

Heat vulnerability key used in the app:
`1-2 = Least Vulnerable, 3-4 = Low Vulnerability, 5-6 = Moderate Vulnerability, 7-8 = Elevated Vulnerability, 9-10 = Most Vulnerable`

Heat vulnerability key citation:
`Hillsborough County. (n.d.). Heat Vulnerability Index (FeatureServer) [Layer metadata]. ArcGIS REST Services Directory. Retrieved June 20, 2026, from https://services1.arcgis.com/IbNXlmt2RVVRCZ6M/arcgis/rest/services/HeatVulnerabilityIndex/FeatureServer/0`

Shade voting guide used in the app:

Shade source:

| Shade Source | Operational Definition |
| --- | --- |
| Natural | Trees, palms, hedges, or other vegetation visibly shade the waiting area |
| Constructed | A designated, purpose-built bus shelter, awning, canopy, overhang, or similar passenger shelter visibly shades the waiting area |
| Manmade | A nearby building or other non-shelter built feature visibly shades the waiting area |
| Natural; Constructed; Manmade | More than one source type visibly shades the waiting area |

Shade coverage:

| Shade Coverage | Operational Definition |
| --- | --- |
| No Shade | No shade visibly reaches the waiting area |
| Limited | Shade visibly reaches part of the waiting area, but does not cover most of it |
| Significant | Shade visibly covers most of the waiting area or seating area |

Trees, utility poles, signs, and nearby buildings are not classified as Constructed unless they are clearly intended to provide passenger shade or weather protection. Nearby buildings that visibly shade the waiting area should be coded as Manmade.

Current app labels:

| Category | Operational Definition |
| --- | --- |
| No Shade | No visible shelter and no vegetation visibly shading the waiting area |
| Limited Natural Shade | Vegetation visibly shades part of the waiting area, but does not visibly cover most of it |
| Significant Natural Shade | Vegetation visibly covers most of the waiting area or seating area |
| Constructed Shade | A purpose-built shelter, awning, canopy, or overhang visibly shades the waiting area |
| Manmade Shade | A nearby building or other non-shelter built feature visibly shades the waiting area |

Classification examples used in the app:

| Visible condition | Shade Source | Shade Coverage |
| --- | --- | --- |
| Bus shelter and trees both visibly shade the waiting area | Natural; Constructed | Limited or Significant, depending on coverage |
| Purpose-built bus shelter visibly shades where riders would wait | Constructed | Limited or Significant, depending on coverage |
| Large building casts shade onto the stop but is not intended as passenger shelter | Manmade | Limited or Significant, depending on coverage |
| Only a small sign or pole shadow reaches the stop | None | None unless it visibly shades the waiting area |
| Trees are nearby but do not visibly shade the waiting area | None | None |
| Hedges or shrubs visibly shade the bench or waiting area | Natural | Limited or Significant, depending on coverage |
| Palms provide partial coverage | Natural | Limited |
| Large oak canopy covers the stop | Natural | Significant |

Research on thermal comfort at bus stops has shown that the waiting environment plays an important role in how riders perceive public transportation. In subtropical climates, exposure to direct sunlight, limited shade, and high temperatures can reduce comfort and satisfaction while waiting for a bus. Together with evidence that tree canopy and shade infrastructure may help mitigate the impacts of extreme heat on transit users, these findings suggest that the quality of the waiting environment is an important component of an accessible, resilient, and rider-friendly transit system. The Tampa Shade Study seeks to make these conditions more visible by documenting shade availability across the region's bus network and providing data that can inform future improvements.

Citation when referencing the GTFS source:
`Hillsborough Area Regional Transit. (Year). General Transit Feed Specification (GTFS) data feed [Data set]. Retrieved June 17, 2026, from the HART GTFS feed.`

Additional reference:
`Briant, S., Cushing, D. F., Washington, T., Pham, K., Pemasiri Hewa Thondilege, A. S., White, K. M., ... & Fookes, C. (2026). Thermal Comfort at Bus Stops in a Subtropical Context: Investigating Perceptions and Satisfaction Levels While Waiting for the Bus. In Human-Building Interaction: The Nexus of Architecture, Building Science and Interaction Design (pp. 119-145). Cham: Springer Nature Switzerland.`

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens to the reusable builder and uses `stops.txt` plus `shading_data.csv` only as the default starter dataset. Uploading a GTFS zip or mapped CSV in the `Data` page replaces the active in-session dataset.

## Verify heat data

Run the dependency-free integrity checks against the local GTFS and heat CSV files:

```bash
python scripts/verify_heat_data.py
```

Before checking, the script fills missing heat values for stops with `Unknown`. It recognizes blank cells and common fillers (`N/A`, `null`, `none`, `nan`, `-`, `missing`, and `Not available`) but does not alter `stop_id` or `shading`. Use `--check-only` to report missing heat values without changing the CSV.

For an accuracy check against the cited Hillsborough County ArcGIS layer, including an independent point-in-polygon match for every stop, run:

```bash
python scripts/verify_heat_data.py --live
```

The script exits with status `0` when all checks pass, `1` when data errors are found, and `2` when inputs or the live source cannot be read. Warnings, such as GTFS stops outside the county layer, do not by themselves fail verification.

## Deploy

This repo is ready for a basic Streamlit deployment using:

- main file: `app.py`
- Python dependencies: `requirements.txt`

The current builder stores edits in Streamlit session state and exposes CSV, GeoJSON, and configuration downloads from the `Preview` page. For shared production deployments, add persistent project storage before treating edits as durable.

```bash
streamlit run app.py
```

Without persistent storage, project edits made in the browser reset when the app session restarts.

## Optional Postgres setup

Postgres is only used by the database initialization script; the Streamlit app currently uses CSV files at runtime.

1. Start Postgres:

```bash
docker-compose up -d
```

2. Install the optional database dependencies:

```bash
pip install -r requirements-db.txt
```

3. Load the stops table:

```bash
python scripts/init_db.py
```

Default connection values are `localhost:5432`, database `tampa_shade`, user `postgres`, and password `postgres`. Override them with `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`.
