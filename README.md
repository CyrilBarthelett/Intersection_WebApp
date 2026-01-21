🛣️ Traffic Flow Plot Generator

You can access the web app with this link: https://intersection-app.streamlit.app/

This Streamlit-based web app was developped at komobile GmbH to turn traffic count data into Sankey-style intersection flow diagrams (PNG & SVG) for up to 4 different directions.

This tool supports:
- Excel-based traffic counts
- Automatic peak-hour detection
- Custom 1-hour time windows
- Manual data entry
- KFZ and PKW-Einheiten modes
- Downloadable vector graphics

🚀 What it does

From a single Excel file with traffic counts, the app automatically generates:

Diagram	Description
Full day	Total traffic across the full measurement period
Morning peak	Highest 1-hour traffic volume in the first half of the day
Afternoon peak	Highest 1-hour traffic volume in the second half of the day
Custom window	Any user-defined 1-hour period
Manual mode	User-entered flows for R1–R12

Each diagram shows:

- Directional flows
- Traffic volume (KFZ or PKW-E)
- Bicycle volumes
- Departing vs arriving traffic per side
- Heavy vehicle (SV) share
- North/East/South/West totals

All plots are exportable as PNG and SVG.

📦 Installation
Install dependencies
pip install -r requirements.txt

Run the app in your web browser
python -m streamlit run streamlit_app.py

📊 Excel format (important)

Your Excel file must contain:
Sheet names:
- Deckbl. – contains metadata
- R1 … R12 – one sheet per traffic direction (only the relevant ones should be included)

In Deckbl.:
- Cell C8: Location name shown in plots
	
In every R* sheet:
- Col A:    Time interval (07:00-07:15, etc.), 15 min windows
- Col B:	Bicycle
- Col C:    Einspur
- Col D:	PKW
- Col E:	Linienbus
- Col F:    Reisebus
- Col G:	LKW
- Col H:	LKW mit Anhänger
- Col I:	Sonstige

There must be a row labeled SUMME in column A at the end of the time series.

The app automatically:

- Detects the measurement period
- Finds the morning & afternoon peak hours
- Calculates PKW-Einheiten using weighted vehicle factors

🧮 KFZ vs PKW-Einheiten

You can switch between KFZ	(Raw vehicle counts) and PKW-E	(Passenger-car equivalents: buses, trucks weighted higher, bikes lower)
PKW-E makes mixed traffic flows comparable.

✏ Manual Mode

If you don’t have an Excel file:

Enable “User direction inputs”
Enter KFZ + Bicycle values directly
Or upload a simple Excel file with 12 rows (first column = R1–R12 values)
The app will generate a diagram from those numbers.

📁 Outputs

Each plot is downloadable as:
- PNG (high-resolution, transparent background)
- SVG (vector format for reports & CAD)

🛠 Customization

You can change via the UI:
- Flow colors (N/E/S/W)
- Layout spacing
- Ribbon thickness scale
- Vehicle weighting factors
- Direction mapping
