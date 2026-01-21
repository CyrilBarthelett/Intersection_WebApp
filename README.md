🛣️ Traffic Flow Plot Generator

A Streamlit-based web app to turn traffic count data into Sankey-style intersection flow diagrams (PNG & SVG).
Designed for traffic engineers, planners, and researchers who need fast, reproducible visualizations of intersection flows.

This tool supports:

Excel-based traffic counts

Automatic peak-hour detection

Custom 1-hour time windows

Manual data entry

KFZ and PKW-Einheiten modes

Downloadable vector graphics

🚀 What it does

From a single Excel file with traffic counts, the app automatically generates:

Diagram	Description
Full day	Total traffic across the full measurement period
Morning peak	Highest 1-hour traffic volume in the first half of the day
Afternoon peak	Highest 1-hour traffic volume in the second half of the day
Custom window	Any user-defined 1-hour period
Manual mode	User-entered flows for R1–R12

Each diagram shows:

Directional flows

Traffic volume (KFZ or PKW-E)

Bicycle volumes

Departing vs arriving traffic per side

Heavy vehicle (SV) share

North/East/South/West totals

All plots are exportable as PNG and SVG.

📦 Installation
1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# or
.venv\Scripts\activate      # Windows

2. Install dependencies
pip install -r requirements.txt

▶ Run the app
python -m streamlit run streamlit_app.py


Open the URL shown in the terminal (usually http://localhost:8501).

📊 Excel format (important)

Your Excel file must contain:

Sheet names

Deckbl. – contains metadata

R1 … R12 – one sheet per traffic direction

In Deckbl.
Cell	Meaning
C8	Location name shown in plots
In every R* sheet
Column	Meaning
A	Time interval (07:00-07:15, etc.)
B	Bicycle
C	Einspur
D	PKW
E	Linienbus
F	Reisebus
G	LKW
H	LKW mit Anhänger
I	Sonstige

There must be a row labeled SUMME in column A at the end of the time series.

The app automatically:

Detects the measurement period

Finds the morning & afternoon peak hours

Calculates PKW-Einheiten using weighted vehicle factors

🧮 KFZ vs PKW-Einheiten

You can switch between:

Mode	Meaning
KFZ	Raw vehicle counts
PKW-E	Passenger-car equivalents (buses, trucks weighted higher, bikes lower)

PKW-E makes mixed traffic flows comparable.

✏ Manual Mode

If you don’t have an Excel file:

Enable “User direction inputs (R1–R12)”

Enter KFZ + Bicycle values directly

Or upload a simple Excel file with 12 rows (first column = R1–R12 values)

The app will generate a diagram from those numbers.

📁 Outputs

Each plot is downloadable as:

PNG (high-resolution, transparent background)

SVG (vector format for reports & CAD)

File names include:

Location + time window + mode


Example:

VZ_MainStreet_morning_peak_07-00_08-00.svg

🧭 What R1–R12 mean

Each Rk corresponds to one fixed connection between two sides of the intersection.
These are defined in main.py in:

DIR_TO_FLOW = {
    1: (1, 24),
    2: (2, 17),
    ...
}


This allows the same Excel format to be reused across different intersections.

🛠 Customization

You can change:

Flow colors (N/E/S/W)

Layout spacing

Ribbon thickness scale

Vehicle weighting factors

Direction mapping

All via the UI or by editing main.py.

🎯 Typical use cases

Traffic engineering reports

Intersection design studies

Peak hour analysis

Bicycle vs car flow comparison

Public consultation graphics

Research and teaching
