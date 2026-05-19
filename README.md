# Tampa Bus Shade Web App

This app visualizes Tampa bus stops from the GTFS `stops.txt` file and prepares the project for future shading data collection.

## Files
- `app.py`: Streamlit web app that loads `stops.txt`, displays the stops on a map, and saves shading annotations locally.
- `requirements.txt`: Python dependencies for the app.
- `shading_data.csv`: generated local file with shading states once you save updates.

## How to run

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run the app:

```bash
streamlit run app.py
```

3. Open the local URL printed by Streamlit in your browser.

## Data source
The app reads from the GTFS stops file at:

`C:\Users\jack3\OneDrive\Documents\Data_Sci\tampa_bus\stops.txt`

If you move the file, update the `DATA_PATH` constant in `app.py`.

## Shading tracking
- The map color codes: green = natural shade, blue = manmade shade, red = no shade, gray = unknown.
- You can update individual stops in the sidebar.
- You can upload a CSV file with `stop_id, shading` to bulk import shading statuses. Valid shading values are `Unknown`, `Natural Shade`, `Manmade Shade`, and `No Shade`.

## Login and voting (crowdsourced)

- Register a simple account in the sidebar and log in to cast votes for stops.
- Users can submit shading votes, while admin accounts can also manually set stop shading and upload shading CSV files.
- Admin registration requires the admin code from `ADMIN_REGISTRATION_CODE` in your environment (default: `adminpass`).
- Each logged-in user may cast one vote per stop (`Natural Shade`, `Manmade Shade`, or `No Shade`).
- Votes are saved to `shading_votes.csv` in the app folder.
- If a stop accumulates 100 or more total votes, the majority vote will automatically set the stop's shading in `shading_data.csv` unless the votes are an exact tie (50/50), in which case the shading remains `Unknown`.

Note: This is a minimal local authentication system for prototyping and is not secure for production. For deployment, replace with a proper auth backend.

## Postgres (optional): local database for stops, users, votes

The project includes a `docker-compose.yml` and SQL schema to run Postgres locally and populate the `stops` table.

1. Start Postgres with Docker Compose:

```bash
docker-compose up -d
```

2. Install database Python deps and run the init script to load `stops.txt`:

```bash
pip install -r requirements.txt
python scripts/init_db.py
```

3. The Postgres database defaults are:

- host: `localhost`
- port: `5432`
- db: `tampa_shade`
- user: `postgres`
- password: `postgres`

You can change these via environment variables `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` before running the init script.

Integration note: `app.py` currently uses local CSV files by default. I can update it to use Postgres for users/votes/shading if you'd like — tell me and I'll wire it up.
