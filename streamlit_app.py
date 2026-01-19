import streamlit as st
import pandas as pd
from main import generate_png_from_excel

#Run using the command: python -m streamlit run streamlit_app.py

# --------------------------------------------------
# Page configuration (must be first Streamlit call)
# --------------------------------------------------
st.set_page_config(page_title="Traffic Flow Plot",page_icon="🛣️",layout="wide")


st.sidebar.header("🌐 Language")
lang = st.sidebar.radio("Choose language", ["English", "Deutsch"])
lang_key = "Deutsch" if "Deutsch" in lang else "English"

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
        "Norht-South": "Nord-Süd: Abstand zwischen ankommenden und abfahrenden Strömen",
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
        "Norht-South": "North-South: Distance between arriving and departing flows",
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
    }
}
T = TEXT[lang_key]

# --------------------------------------------------
# Page title and instructions
# --------------------------------------------------
st.title(T["title"])
st.write(T["upload"])

# --------------------------------------------------
# Color settings in sidebar
# --------------------------------------------------

st.sidebar.header(T["units"])
mode = st.sidebar.radio(
    T["show_flows"],
    options=["KFZ", "PKW-E"],
    help=T["unit_explanation"]
)

st.sidebar.header(T["colors"])
n_color = st.sidebar.color_picker(T["Nord"], "#1f77b4")
e_color = st.sidebar.color_picker(T["Ost"], "#ff7f0e")
s_color = st.sidebar.color_picker(T["Süd"], "#2ca02c")
w_color = st.sidebar.color_picker(T["West"], "#d62728")

side_colors = {"N": n_color, "E": e_color, "S": s_color, "W": w_color}

st.sidebar.header(T["layout"], help = T["d-helper"])
d_NS_value = st.sidebar.slider(
    T["Norht-South"],
    min_value=0.5,
    max_value=3.0,
    value=1.5,
    step=0.05,
)
d_WE_value = st.sidebar.slider(
    T["East-West"],
    min_value=0.5,
    max_value=3.0,
    value=1.5,
    step=0.05,
)

# --------------------------------------------------
# File uploader widget
# --------------------------------------------------
uploaded = st.file_uploader(T["excel"],type=["xlsx"])

# --------------------------------------------------
# Run only after a file has been uploaded
# --------------------------------------------------
if uploaded:
    # Show spinner while processing
    with st.spinner(T["generating"]):
        try:
            # Read uploaded Excel file as bytes
            excel_bytes = uploaded.read()

            # Generate PNG images and filenames
            png_list, meta = generate_png_from_excel(excel_bytes, side_colors, d_NS=d_NS_value, d_WE=d_WE_value, mode = mode)

            # Success message
            st.success(T["done"])
            
            time_windows = [
            f"{meta['day']['start']} – {meta['day']['end']}",
            f"{meta['morning_peak']['start']} – {meta['morning_peak']['end']}",
            f"{meta['afternoon_peak']['start']} – {meta['afternoon_peak']['end']}",
            ]
            
            st.subheader(T.get("peak_info", T["Time window"]))

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

            st.divider()
                    
            # ------------------------------
            # KFZ | Bicycle by direction (table)
            # ------------------------------

            st.subheader(f"{T['dir_table']} ({mode} | {T['Bicycle']})")

            df = pd.DataFrame(meta["per_direction"])

            flow_col = "kfz" if mode == "KFZ" else "pkw"

            # round and int for the columns we will actually use
            cols_to_int = [
                f"full_day_{flow_col}", f"morning_peak_{flow_col}", f"afternoon_peak_{flow_col}",
                "full_day_bike", "morning_peak_bike", "afternoon_peak_bike"
            ]
            for c in cols_to_int:
                df[c] = df[c].round(0).astype(int)

            df_out = pd.DataFrame({
                T["Direction"]: df["direction"],
                f"{T['Full day']} ({mode} | {T['Bicycle']})":
                    df[f"full_day_{flow_col}"].astype(str) + " | " + df["full_day_bike"].astype(str),
                f"{T['Morning peak']} ({mode} | {T['Bicycle']})":
                    df[f"morning_peak_{flow_col}"].astype(str) + " | " + df["morning_peak_bike"].astype(str),
                f"{T['Afternoon peak']} ({mode} | {T['Bicycle']})":
                    df[f"afternoon_peak_{flow_col}"].astype(str) + " | " + df["afternoon_peak_bike"].astype(str),
            })
            st.dataframe(df_out, use_container_width=True, hide_index=True)

            # Totals (mode-dependent)
            t1, t2, t3 = st.columns(3)

            with t1:
                st.markdown(f"**{T['Total full day']} ({mode} | {T['Bicycle']})**")
                st.write(f"{int(round(meta['totals'][f'full_day_{flow_col}']))} | {int(round(meta['totals']['full_day_bike']))}")

            with t2:
                st.markdown(f"**{T['Total morning peak']} ({mode} | {T['Bicycle']})**")
                st.write(f"{int(round(meta['totals'][f'morning_peak_{flow_col}']))} | {int(round(meta['totals']['morning_peak_bike']))}")

            with t3:
                st.markdown(f"**{T['Total afternoon peak']} ({mode} | {T['Bicycle']})**")
                st.write(f"{int(round(meta['totals'][f'afternoon_peak_{flow_col}']))} | {int(round(meta['totals']['afternoon_peak_bike']))}")

            # Side table (mode-dependent labels)

            st.subheader(f"{T['cardinal_table']} ({mode})")

            bd = meta["by_side"]["full_day"]
            df_side = pd.DataFrame({
                T["Side"]: ["N", "E", "S", "W"],
                f"{T['Departing']} {mode}": [int(round(bd["dep_kfz"][s])) for s in ["N","E","S","W"]],
                f"{T['Arriving']} {mode}":  [int(round(bd["arr_kfz"][s])) for s in ["N","E","S","W"]],
                f"{T['Total']} {mode}":     [int(round(bd["total_kfz"][s])) for s in ["N","E","S","W"]],
            })
            st.dataframe(df_side, use_container_width=True, hide_index=True)

            st.subheader(f"{T['Totals & SV share']}")

            mode_key = "kfz" if mode == "KFZ" else "pkw"
            sv_block = meta["sv"][mode_key]

            def pct(x):
                return f"{x:.2f}%"

            df_sv = pd.DataFrame([
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
            ])

            st.dataframe(df_sv, use_container_width=True, hide_index=True)
            
            # Display each generated image with download button
            plot_titles = [
                T["Plot general day"],
                T["Plot morning peak"],
                T["Plot afternoon peak"]
            ]

            for i, (png_bytes, out_name) in enumerate(png_list):
                title_col, button_col = st.columns([1, 0.2], vertical_alignment="center")

                with title_col:
                    st.markdown(f"### {plot_titles[i]} ({time_windows[i]})")

                with button_col:
                    st.download_button(
                        label=f"{T['download']}",
                        data=png_bytes,
                        file_name=out_name,
                        mime="image/png",
                        key=f"dl_{out_name}",
                        use_container_width=True
                    )

                st.image(png_bytes, use_container_width=True)
                st.divider()

        except Exception as e:
            # Display error if anything goes wrong
            st.error(f"Error: {e}")