# Tampa Bus Shade Web App

Streamlit app for visualizing bus stop shading to provide better insights on Tampa's transport, using Tampa-area GTFS stop data and lightweight anonymous shade votes.

## What it does

- Displays Tampa bus stops on an interactive PyDeck map.
- Colors stops by current shade status: natural shade, manmade shade, no shade, or unknown.
- Adds four heat-context fields for each stop: weighted HVI, vulnerability category, tree canopy percentage, and median land surface temperature.
- Lets each browser session submit one anonymous vote per stop.
- Applies a stop's shade status automatically once it reaches 5 valid votes.
- Uses the majority vote as the status; if top statuses are tied, the tied status with the oldest vote wins.
- Saves runtime votes to `shading_votes.csv` and saved shade status to `shading_data.csv`.

## About the study

This study focuses on visualizing bus stop shading to provide better insights on Tampa's transport. The app uses GTFS stop locations together with community shading votes to support exploratory analysis, fieldwork planning, and transit-focused discussion.

Map tooltips now focus on four heat-exposure variables that best support the project story: the county's weighted heat vulnerability index, the vulnerability category label, tree canopy percentage, and median land surface temperature. The app also summarizes these fields by shading category and highlights high-priority stops where low shade and high heat exposure overlap.

Main dataset fields used in the app:
- `shading`: observed or voted shade condition at the stop itself, which is the most direct rider-experience measure.
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

The app reads `stops.txt` from this project directory. The committed `shading_data.csv` is used as seed shade data.

## Deploy

This repo is ready for a basic Streamlit deployment using:

- main file: `app.py`
- Python dependencies: `requirements.txt`

The app writes votes and updated shade status to local CSV files. On hosts with ephemeral or read-only source directories, set `APP_DATA_DIR` to a writable directory or mounted volume:

```bash
APP_DATA_DIR=/tmp/tampa-shade streamlit run app.py
```

Without persistent storage, votes recorded after deployment may be lost when the app restarts.

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
