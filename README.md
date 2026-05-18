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
- The map color codes: green = shaded, red = no shade, gray = unknown.
- You can update individual stops in the sidebar.
- You can upload a CSV file with `stop_id, shading` to bulk import shading statuses.
