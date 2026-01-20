import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from main import generate_png_from_excel, generate_plots_from_direction_values

# Run with:
#   python -m streamlit run streamlit_app.py


# ==================================================
# 1) Page config (MUST be first Streamlit call)
# ==================================================
st.set_page_config(page_title="Traffic Flow Plot", page_icon="🛣️", layout="wide")


# ==================================================
# 2) Translations / UI text
# ==================================================
TEXT = {
    "Deutsch": {
        "title": "Verkehrsfluss-Diagramm Generator",
        "excel": "Excel-Datei hochladen (.xlsx)",
        "upload": "Lade eine Excel-Datei mit Verkehrszählungen (.xlsx) hoch und lade das erzeugte PNG herunter.",
        "done": "Fertig!",
        "units": "Einheiten",
        "show_flows": "Flüsse anzeigen als",
        "unit_explanation": "KFZ = Kraftfahrzeuge. PKW = Pkw-Einheiten.",
        "colors": "Strömfarben",
        "Nord": "Norden",
        "Ost": "Osten",
        "Süd": "Süden",
        "West": "Westen",
        "layout": "Layout",
        "North-South": "Nord-Süd: Abstand zwischen ankommenden und abfahrenden Strömen",
        "d-helper": "Abstand von der Mittellinie bis zur Mitte jeder Stromgruppe",
        "East-West": "Ost-West: Abstand zwischen ankommenden und abfahrenden Strömen",
        "dir_table": "Verkehr nach Kreuzungsrichtung",
        "cardinal_table": "Verkehr nach Himmelsrichtung",
        "sv_table": "Gesamtverkehr & Schwerverkehr-Anteil",
        "download": "Herunterladen",
        "generating": "Diagramm wird erstellt...",
        "Bicycle": "Fahrrad",
        "Direction": "Richtung",
        "Full day": "Ganzer Tag",
        "Morning peak": "Morgensspitzenstunde",
        "Afternoon peak": "Nachmittagsspitzenstunde",
        "Total full day": "Summe ganzer Tag",
        "Total morning peak": "Summe Morgenspitzenstunde",
        "Total afternoon peak": "Summe Nachmittagsspitzenstunde",
        "Departing": "Abfahrend",
        "Arriving": "Ankommend",
        "Total": "Summe",
        "Side": "Himmelsrichtung",
        "Totals & SV share": "Gesamtverkehr & Sonderverkehrssanteil (SV)",
        "Plot general day": "Diagramm ganzer Tag",
        "Plot morning peak": "Diagramm Morgenspitzenstunde",
        "Plot afternoon peak": "Diagramm Nachmittagsspitzenstunde",
        "Time window": "Zeitfenster",
        "Define own 1h time window": "Definiere eigenes einstündiges Zeitfenster",
        "Selected window": "Ausgewähltes Zeitfenster",
        "Start time": "Zeitbeginn",
        "User direction inputs (R1–R12)": "Benutzerdefinierte Richtungs-Inputs (R1–R12)",
        "Generate": "Generieren",
        "Clear": "Tabelle leeren",
        "manual_warning": "Geben Sie mindestens eine von null verschiedene Richtung ein, um ein Diagramm zu erzeugen.",
        "Manual result": "Ergebnis (Manueller Modus)",
        "Generated plot": "Erzeugtes Diagramm",
        "Plot custom": "Diagramm ausgewählte Zeit",
        "Custom window": "Eigenes Zeitfenster",
        "Width" : "Strombreiten-Skala",
        "Wmin" : "Minimale Strombreite",
        "Wmax" : "Maximale Strombreite"
    },
    "English": {
        "title": "Traffic Flow Plot Generator",
        "excel": "Upload Excel file (.xlsx)",
        "upload": "Upload an Excel traffic count file (`.xlsx`) and download the generated PNG.",
        "done": "Done!",
        "units": "Units",
        "show_flows": "Show flows as",
        "unit_explanation": "KFZ = All types of motor vehicles. PKW = Passenger car equivalents.",
        "colors": "Flow Colors",
        "Nord": "North",
        "Ost": "East",
        "Süd": "South",
        "West": "West",
        "layout": "Layout",
        "North-South": "North-South: Distance between arriving and departing flows",
        "d-helper": "Distance from centerline to middle of each flow group",
        "East-West": "East-West: Distance between arriving and departing flows",
        "dir_table": "Traffic by intersection direction",
        "cardinal_table": "Traffic by cardinal direction",
        "sv_table": "Totals & Heavy Vehicle Share",
        "download": "Download",
        "generating": "Generating plot...",
        "Bicycle": "Bicycle",
        "Direction": "Direction",
        "Full day": "Full day",
        "Morning peak": "Morning peak",
        "Afternoon peak": "Afternoon peak",
        "Total full day": "Total full day",
        "Total morning peak": "Total morning peak",
        "Total afternoon peak": "Total afternoon peak",
        "Departing": "Departing",
        "Arriving": "Arriving",
        "Total": "Total",
        "Side": "Side",
        "Totals & SV share": "Totals & Special Vehicle (SV) Share",
        "Plot general day": "Plot full day",
        "Plot morning peak": "Plot morning peak",
        "Plot afternoon peak": "Plot afternoon peak",
        "Time window": "Time window",
        "Define own 1h time window": "Define own 1h time window",
        "Selected window": "Selected window",
        "Start time": "Start time",
        "User direction inputs (R1–R12)": "User direction inputs (R1–R12)",
        "Generate": "Generate",
        "Clear": "Clear",
        "manual_warning": "Enter at least one non-zero direction to generate a plot.",
        "Manual result": "Manual mode result",
        "Generated plot": "Generated plot",
        "Plot custom": "Plot custom window",
        "Custom window": "Custom window",
        "Width" : "Flow width range",
        "Wmin" : "Minimum flow width",
        "Wmax" : "Maximum flow width"
    },
}

# --- Language selection (sidebar) ---
st.sidebar.header("🌐 Language")
lang = st.sidebar.radio("Choose language", ["English", "Deutsch"])
T = TEXT["Deutsch"] if lang == "Deutsch" else TEXT["English"]


# ==================================================
# 3) Helper functions
# ==================================================
def time_list(start_hm: str, end_hm: str, step_min: int = 15) -> list[str]:
    """
    Create a list of time strings 'HH:MM' between start_hm and end_hm (inclusive),
    stepping by step_min minutes.
    """
    t0 = datetime.strptime(start_hm, "%H:%M")
    t1 = datetime.strptime(end_hm, "%H:%M")
    out = []
    t = t0
    while t <= t1:
        out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=step_min)
    return out


def init_manual_state():
    """
    Initialize manual-mode state variables once.
    Streamlit reruns the script often, so we only create defaults if missing.
    """
    if "manual_df" not in st.session_state:
        st.session_state["manual_df"] = pd.DataFrame({
            "Direction": [f"R{i}" for i in range(1, 13)],
            "KFZ": [0] * 12,
            "Bicycle": [0] * 12,
        })

    if "manual_generate_clicked" not in st.session_state:
        st.session_state["manual_generate_clicked"] = False


def build_direction_values_from_df(df: pd.DataFrame) -> dict:
    """
    Convert the manual input table into the expected 'direction_values' dict:
        {
          "R1": {"kfz": 10.0, "rad": 2.0},
          ...
        }
    Only keep directions where at least one value is > 0.
    """
    out = {}
    for _, row in df.iterrows():
        kfz = float(row["KFZ"])
        rad = float(row["Bicycle"])
        if kfz > 0 or rad > 0:
            out[row["Direction"]] = {"kfz": kfz, "rad": rad}
    return out


def show_download_and_preview_block(png_list, svg_list, titles, time_windows, T):
    """
    Display a repeated block:
      - title
      - download PNG button
      - download SVG button
      - PNG preview
    """
    for (png_bytes, png_name), (svg_bytes, svg_name), title, tw in zip(
        png_list, svg_list, titles, time_windows
    ):
        title_col, btn_png_col, btn_svg_col = st.columns([1, 0.2, 0.2], vertical_alignment="center")

        with title_col:
            st.markdown(f"### {title} ({tw})")

        with btn_png_col:
            st.download_button(
                label=f"{T['download']} PNG",
                data=png_bytes,
                file_name=png_name,
                mime="image/png",
                key=f"dl_png_{png_name}",
                use_container_width=True,
            )

        with btn_svg_col:
            st.download_button(
                label=f"{T['download']} SVG",
                data=svg_bytes,
                file_name=svg_name,
                mime="image/svg+xml",
                key=f"dl_svg_{svg_name}",
                use_container_width=True,
            )

        st.image(png_bytes, use_container_width=True)
        st.divider()


# ==================================================
# 4) Main page title
# ==================================================
st.title(T["title"])


# ==================================================
# 5) Sidebar controls (common)
# ==================================================
st.sidebar.header("Manual mode")
manual_mode = st.sidebar.checkbox(T["User direction inputs (R1–R12)"], value=False)

# Units mode: KFZ vs PKW-E
st.sidebar.header(T["units"])
mode = st.sidebar.radio(
    T["show_flows"],
    options=["KFZ", "PKW-E"],
    help=T["unit_explanation"],
)

# Color pickers for flows
st.sidebar.header(T["colors"])
n_color = st.sidebar.color_picker(T["Nord"], "#1f77b4")
e_color = st.sidebar.color_picker(T["Ost"], "#ff7f0e")
s_color = st.sidebar.color_picker(T["Süd"], "#2ca02c")
w_color = st.sidebar.color_picker(T["West"], "#d62728")
side_colors = {"N": n_color, "E": e_color, "S": s_color, "W": w_color}

# Layout spacing controls
st.sidebar.header(T["layout"], help=T["d-helper"])
d_NS_value = st.sidebar.slider(T["North-South"], 0.5, 3.0, 1.5, 0.05)
d_WE_value = st.sidebar.slider(T["East-West"], 0.5, 3.0, 1.5, 0.05)

# Flow width selection
st.sidebar.header(T["Width"])
w_min_value = st.sidebar.slider(T["Wmin"], 0.0, 2.0, 0.1, 0.1)
w_max_value = st.sidebar.slider(T["Wmax"], 0.0, 2.0, 1.1, 0.1)

# ==================================================
# 6) Time window controls (Excel mode only)
# ==================================================
use_custom = False
custom_start_time = None

if not manual_mode:
    st.sidebar.header(T["Time window"])
    use_custom = st.sidebar.checkbox(T["Define own 1h time window"], value=False)

    start_options = time_list("05:00", "21:00", 15)

    if use_custom:
        custom_start_time = st.sidebar.selectbox(
            T["Start time"],
            start_options,
            index=None,
            placeholder="Select a start time",
            key="start_time_1h",
        )

        # If a time is chosen, show its 1-hour window
        if custom_start_time is not None:
            start_dt = datetime.strptime(custom_start_time, "%H:%M")
            custom_end_time = (start_dt + timedelta(hours=1)).strftime("%H:%M")
            st.sidebar.markdown(f"{T['Selected window']}: {custom_start_time} – {custom_end_time}")
    else:
        # show disabled dropdown to keep layout stable
        st.sidebar.selectbox(T["Start time"], start_options, disabled=True, key="start_time_disabled")


# ==================================================
# 7) Manual mode UI + state
# ==================================================
init_manual_state()

if manual_mode:
    st.subheader(T["User direction inputs (R1–R12)"])

    # Editable table (persists via session_state["manual_df"])
    edited_df = st.data_editor(
        st.session_state["manual_df"],
        hide_index=True,
        use_container_width=True,
        column_config={
            "KFZ": st.column_config.NumberColumn("KFZ", min_value=0, step=1),
            "Bicycle": st.column_config.NumberColumn(T["Bicycle"], min_value=0, step=1),
        },
        disabled=["Direction"],
        key="manual_editor",
    )

    # Persist edits
    st.session_state["manual_df"] = edited_df

    # Build direction_values from current table content
    manual_direction_values = build_direction_values_from_df(edited_df)

    # Buttons side by side
    col_clear, col_gen = st.columns([1, 1])

    with col_gen:
        generate_manual = st.button(
            T["Generate"],
            type="primary",
            use_container_width=True,
            key="btn_generate_manual",
        )

    with col_clear:
        clear_manual = st.button(
            T["Clear"],
            use_container_width=True,
            key="btn_clear_manual",
        )

    # Clear: reset table + hide results + rerun to refresh editor
    if clear_manual:
        st.session_state["manual_df"] = pd.DataFrame({
            "Direction": [f"R{i}" for i in range(1, 13)],
            "KFZ": [0] * 12,
            "Bicycle": [0] * 12,
        })
        st.session_state["manual_generate_clicked"] = False

        # Optional robustness: clear widget's internal state if it ever “sticks”
        if "manual_editor" in st.session_state:
            del st.session_state["manual_editor"]

        st.rerun()

    # Generate: validate at least one non-zero flow
    if generate_manual:
        if not manual_direction_values:
            st.warning(T["manual_warning"])
        else:
            st.session_state["manual_generate_clicked"] = True

else:
    # Leaving manual mode should not keep manual result visible
    st.session_state["manual_generate_clicked"] = False


# ==================================================
# 8) Excel upload UI (Excel mode only)
# ==================================================
uploaded = None
if not manual_mode:
    st.write(T["upload"])
    uploaded = st.file_uploader(T["excel"], type=["xlsx"])


# ==================================================
# 9) Plot generation (Excel OR manual)
# ==================================================
png_list = svg_list = meta = None

# --- A) Generate from Excel upload ---
if (not manual_mode) and uploaded:
    try:
        with st.spinner(T["generating"]):
            excel_bytes = uploaded.read()
            png_list, svg_list, meta = generate_png_from_excel(
                excel_bytes,
                side_colors,
                d_NS=d_NS_value,
                d_WE=d_WE_value,
                w_min = w_min_value,
                w_max = w_max_value,
                mode=mode,
                use_custom_window=use_custom and (custom_start_time is not None),
                custom_start_time=custom_start_time,
            )
        st.success(T["done"])
    except Exception as e:
        st.error(f"Error: {e}")

# --- B) Generate from manual inputs ---
if manual_mode and st.session_state.get("manual_generate_clicked", False):
    try:
        with st.spinner(T["generating"]):
            direction_values = build_direction_values_from_df(st.session_state["manual_df"])

            png_list, svg_list, meta = generate_plots_from_direction_values(
                direction_values=direction_values,
                location="Manual input",
                side_colors=side_colors,
                d_NS=d_NS_value,
                d_WE=d_WE_value,
                w_min = w_min_value,
                w_max = w_max_value,
                mode=mode,
            )
        st.success(T["done"])
    except Exception as e:
        st.error(f"Error: {e}")


# ==================================================
# 10) Results rendering (common)
# ==================================================
if png_list is None or svg_list is None or meta is None:
    st.stop()  # Nothing to display yet


# --------------------------------------------------
# 10A) Manual mode results
# --------------------------------------------------
if manual_mode:

    # In manual mode you typically have a single plot (but we keep it generic)
    for idx, ((png_bytes, png_name), (svg_bytes, svg_name)) in enumerate(zip(png_list, svg_list)):
        c1, c2, c3 = st.columns([1, 0.2, 0.2], vertical_alignment="center")

        with c1:
            st.markdown(f"### {T['Generated plot']}")

        with c2:
            st.download_button(
                label=f"{T['download']} PNG",
                data=png_bytes,
                file_name=png_name,
                mime="image/png",
                key=f"dl_png_manual_{idx}",
                use_container_width=True,
            )

        with c3:
            st.download_button(
                label=f"{T['download']} SVG",
                data=svg_bytes,
                file_name=svg_name,
                mime="image/svg+xml",
                key=f"dl_svg_manual_{idx}",
                use_container_width=True,
            )

        st.image(png_bytes, use_container_width=True)
        st.divider()

    st.stop()


# --------------------------------------------------
# 10B) Excel mode results (tables + plots)
# --------------------------------------------------
# ---- Time windows summary cards (top) ----
st.subheader(T["Time window"])

has_custom = meta.get("custom") is not None

if not has_custom:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"**{T['Full day']}**")
        st.write(f"{meta['day']['start']} – {meta['day']['end']}")
    with c2:
        st.markdown(f"**{T['Morning peak']}**")
        st.write(f"{meta['morning_peak']['start']} – {meta['morning_peak']['end']}")
    with c3:
        st.markdown(f"**{T['Afternoon peak']}**")
        st.write(f"{meta['afternoon_peak']['start']} – {meta['afternoon_peak']['end']}")
else:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"**{T['Full day']}**")
        st.write(f"{meta['day']['start']} – {meta['day']['end']}")
    with c2:
        st.markdown(f"**{T['Morning peak']}**")
        st.write(f"{meta['morning_peak']['start']} – {meta['morning_peak']['end']}")
    with c3:
        st.markdown(f"**{T['Afternoon peak']}**")
        st.write(f"{meta['afternoon_peak']['start']} – {meta['afternoon_peak']['end']}")
    with c4:
        st.markdown(f"**{T['Selected window']}**")
        st.write(f"{meta['custom']['start']} – {meta['custom']['end']}")

st.divider()

# ---- Table: per direction (KFZ/PKW + Bicycle) ----
st.subheader(f"{T['dir_table']} ({mode} | {T['Bicycle']})")

df = pd.DataFrame(meta["per_direction"])

# The flow column depends on chosen unit mode
flow_col = "kfz" if mode == "KFZ" else "pkw"

# Columns to show, and rounding/int conversion for clean display
cols_to_int = [
    f"full_day_{flow_col}", f"morning_peak_{flow_col}", f"afternoon_peak_{flow_col}",
    "full_day_bike", "morning_peak_bike", "afternoon_peak_bike",
]
if has_custom:
    cols_to_int += [f"custom_{flow_col}", "custom_bike"]

for c in cols_to_int:
    df[c] = df[c].round(0).astype(int)

# Build a user-facing dataframe with "flow | bike" formatting
df_out = pd.DataFrame({
    T["Direction"]: df["direction"],
    f"{T['Full day']} ({mode} | {T['Bicycle']})":
        df[f"full_day_{flow_col}"].astype(str) + " | " + df["full_day_bike"].astype(str),
    f"{T['Morning peak']} ({mode} | {T['Bicycle']})":
        df[f"morning_peak_{flow_col}"].astype(str) + " | " + df["morning_peak_bike"].astype(str),
    f"{T['Afternoon peak']} ({mode} | {T['Bicycle']})":
        df[f"afternoon_peak_{flow_col}"].astype(str) + " | " + df["afternoon_peak_bike"].astype(str),
})
if has_custom:
    df_out[f"{T['Custom window']} ({mode} | {T['Bicycle']})"] = \
        df[f"custom_{flow_col}"].astype(str) + " | " + df["custom_bike"].astype(str)

st.dataframe(df_out, use_container_width=True, hide_index=True)

# ---- Totals cards ----
tot = meta["totals"]

if not has_custom:
    t1, t2, t3 = st.columns(3)
    with t1:
        st.markdown(f"**{T['Total full day']} ({mode} | {T['Bicycle']})**")
        st.write(f"{int(round(tot[f'full_day_{flow_col}']))} | {int(round(tot['full_day_bike']))}")
    with t2:
        st.markdown(f"**{T['Total morning peak']} ({mode} | {T['Bicycle']})**")
        st.write(f"{int(round(tot[f'morning_peak_{flow_col}']))} | {int(round(tot['morning_peak_bike']))}")
    with t3:
        st.markdown(f"**{T['Total afternoon peak']} ({mode} | {T['Bicycle']})**")
        st.write(f"{int(round(tot[f'afternoon_peak_{flow_col}']))} | {int(round(tot['afternoon_peak_bike']))}")
else:
    t1, t2, t3, t4 = st.columns(4)
    with t1:
        st.markdown(f"**{T['Total full day']} ({mode} | {T['Bicycle']})**")
        st.write(f"{int(round(tot[f'full_day_{flow_col}']))} | {int(round(tot['full_day_bike']))}")
    with t2:
        st.markdown(f"**{T['Total morning peak']} ({mode} | {T['Bicycle']})**")
        st.write(f"{int(round(tot[f'morning_peak_{flow_col}']))} | {int(round(tot['morning_peak_bike']))}")
    with t3:
        st.markdown(f"**{T['Total afternoon peak']} ({mode} | {T['Bicycle']})**")
        st.write(f"{int(round(tot[f'afternoon_peak_{flow_col}']))} | {int(round(tot['afternoon_peak_bike']))}")
    with t4:
        st.markdown(f"**{T['Selected window']} ({mode} | {T['Bicycle']})**")
        st.write(f"{int(round(tot[f'custom_{flow_col}']))} | {int(round(tot['custom_bike']))}")

st.divider()

# ---- Side table (departing/arriving totals by N/E/S/W) ----
st.subheader(f"{T['cardinal_table']} ({mode})")

bd = meta["by_side"]["full_day"]
df_side = pd.DataFrame({
    T["Side"]: ["N", "E", "S", "W"],
    f"{T['Departing']} {mode}": [int(round(bd["dep_kfz"][s])) for s in ["N", "E", "S", "W"]],
    f"{T['Arriving']} {mode}":  [int(round(bd["arr_kfz"][s])) for s in ["N", "E", "S", "W"]],
    f"{T['Total']} {mode}":     [int(round(bd["total_kfz"][s])) for s in ["N", "E", "S", "W"]],
})
st.dataframe(df_side, use_container_width=True, hide_index=True)

# ---- Totals & SV share table ----
st.subheader(T["Totals & SV share"])

mode_key = "kfz" if mode == "KFZ" else "pkw"
sv_block = meta["sv"][mode_key]

def pct(x: float) -> str:
    return f"{x:.2f}%"

rows = [
    {
        "Time window": T["Full day"],
        f"Total {mode}": int(round(sv_block["full_day"]["total"])),
        f"SV {mode}": int(round(sv_block["full_day"]["sv"])),
        "SV share (%)": pct(sv_block["full_day"]["sv_share_pct"]),
    },
    {
        "Time window": T["Morning peak"],
        f"Total {mode}": int(round(sv_block["morning_peak"]["total"])),
        f"SV {mode}": int(round(sv_block["morning_peak"]["sv"])),
        "SV share (%)": pct(sv_block["morning_peak"]["sv_share_pct"]),
    },
    {
        "Time window": T["Afternoon peak"],
        f"Total {mode}": int(round(sv_block["afternoon_peak"]["total"])),
        f"SV {mode}": int(round(sv_block["afternoon_peak"]["sv"])),
        "SV share (%)": pct(sv_block["afternoon_peak"]["sv_share_pct"]),
    },
]
if has_custom:
    rows.append({
        "Time window": T["Selected window"],
        f"Total {mode}": int(round(sv_block["custom"]["total"])),
        f"SV {mode}": int(round(sv_block["custom"]["sv"])),
        "SV share (%)": pct(sv_block["custom"]["sv_share_pct"]),
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()

# ---- Plots download + preview ----
time_windows = [
    f"{meta['day']['start']} – {meta['day']['end']}",
    f"{meta['morning_peak']['start']} – {meta['morning_peak']['end']}",
    f"{meta['afternoon_peak']['start']} – {meta['afternoon_peak']['end']}",
]
plot_titles = [
    T["Plot general day"],
    T["Plot morning peak"],
    T["Plot afternoon peak"],
]

if has_custom:
    time_windows.append(f"{meta['custom']['start']} – {meta['custom']['end']}")
    plot_titles.append(T["Plot custom"])

show_download_and_preview_block(png_list, svg_list, plot_titles, time_windows, T)
