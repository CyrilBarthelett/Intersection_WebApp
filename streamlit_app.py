import streamlit as st
import pandas as pd
from main import generate_png_from_excel

#Run using the command: python -m streamlit run streamlit_app.py

# --------------------------------------------------
# Page configuration (must be first Streamlit call)
# --------------------------------------------------
st.set_page_config(page_title="Traffic Flow Plot",page_icon="🛣️",layout="wide")

# --------------------------------------------------
# Page title and instructions
# --------------------------------------------------
st.title("Traffic Flow Plot Generator")
st.write("Upload an Excel traffic count file (`.xlsx`) ""and download the generated PNG. Choose colors for the flows.")

# --------------------------------------------------
# Color settings in sidebar
# --------------------------------------------------

st.sidebar.header("Units")
mode = st.sidebar.radio(
    "Show flows as",
    options=["KFZ", "PKW"],
    help="KFZ = normal motor vehicles. PKW = passenger car equivalents (PKW-Einheiten)."
)

st.sidebar.header("Flow Colors")
n_color = st.sidebar.color_picker("North", "#1f77b4")
e_color = st.sidebar.color_picker("East", "#ff7f0e")
s_color = st.sidebar.color_picker("South", "#2ca02c")
w_color = st.sidebar.color_picker("West", "#d62728")

side_colors = {"N": n_color, "E": e_color, "S": s_color, "W": w_color}

st.sidebar.header("Layout")
d_NS_value = st.sidebar.slider(
    "North-South: Distance between arriving and departing flows",
    min_value=0.5,
    max_value=3.0,
    value=1.5,
    step=0.05,
    help="Distance from center line to the middle of each flow group"
)
d_WE_value = st.sidebar.slider(
    "East-West: Distance between arriving and departing flows",
    min_value=0.5,
    max_value=3.0,
    value=1.5,
    step=0.05,
    help="Distance from center line to the middle of each flow group"
)

# --------------------------------------------------
# File uploader widget
# --------------------------------------------------
uploaded = st.file_uploader("Upload Excel (.xlsx)",type=["xlsx"])

# --------------------------------------------------
# Run only after a file has been uploaded
# --------------------------------------------------
if uploaded:
    # Show spinner while processing
    with st.spinner("Generating plot..."):
        try:
            # Read uploaded Excel file as bytes
            excel_bytes = uploaded.read()

            # Generate PNG images and filenames
            png_list, meta = generate_png_from_excel(excel_bytes, side_colors, d_NS=d_NS_value, d_WE=d_WE_value, mode = mode)

            # Success message
            st.success("Done!")

            # ------------------------------
            # KFZ | Bicycle by direction (table)
            # ------------------------------

            st.subheader(f"Traffic by intersection direction ({mode} | Bicycle)")

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
                "Direction": df["direction"],
                f"Full day ({mode} | Bicycle)": df[f"full_day_{flow_col}"].astype(str) + " | " + df["full_day_bike"].astype(str),
                f"Morning peak ({mode} | Bicycle)": df[f"morning_peak_{flow_col}"].astype(str) + " | " + df["morning_peak_bike"].astype(str),
                f"Afternoon peak ({mode} | Bicycle)": df[f"afternoon_peak_{flow_col}"].astype(str) + " | " + df["afternoon_peak_bike"].astype(str),
            })
            st.dataframe(df_out, use_container_width=True, hide_index=True)

            # Totals (mode-dependent)
            t1, t2, t3 = st.columns(3)

            with t1:
                st.markdown(f"**Total full day ({mode} | Bicycle)**")
                st.write(f"{int(round(meta['totals'][f'full_day_{flow_col}']))} | {int(round(meta['totals']['full_day_bike']))}")

            with t2:
                st.markdown(f"**Total morning peak ({mode} | Bicycle)**")
                st.write(f"{int(round(meta['totals'][f'morning_peak_{flow_col}']))} | {int(round(meta['totals']['morning_peak_bike']))}")

            with t3:
                st.markdown(f"**Total afternoon peak ({mode} | Bicycle)**")
                st.write(f"{int(round(meta['totals'][f'afternoon_peak_{flow_col}']))} | {int(round(meta['totals']['afternoon_peak_bike']))}")

            # Side table (mode-dependent labels)

            st.subheader(f"Traffic by cardinal direction ({mode})")

            bd = meta["by_side"]["full_day"]
            df_side = pd.DataFrame({
                "Side": ["N", "E", "S", "W"],
                f"Departing {mode}": [int(round(bd["dep_kfz"][s])) for s in ["N","E","S","W"]],
                f"Arriving {mode}":  [int(round(bd["arr_kfz"][s])) for s in ["N","E","S","W"]],
                f"Total {mode}":     [int(round(bd["total_kfz"][s])) for s in ["N","E","S","W"]],
            })
            st.dataframe(df_side, use_container_width=True, hide_index=True)
            
            st.subheader(f"Totals & SV share ({mode})")

            mode_key = "kfz" if mode == "KFZ" else "pkw"
            sv_block = meta["sv"][mode_key]

            def pct(x):
                return f"{x:.2f}%"

            df_sv = pd.DataFrame([
                {
                    "Time window": "Full day",
                    f"Total {mode}": int(round(sv_block["full_day"]["total"])),
                    f"SV {mode}": int(round(sv_block["full_day"]["sv"])),
                    "SV share (%)": pct(sv_block["full_day"]["sv_share_pct"]),
                },
                {
                    "Time window": "Morning peak",
                    f"Total {mode}": int(round(sv_block["morning_peak"]["total"])),
                    f"SV {mode}": int(round(sv_block["morning_peak"]["sv"])),
                    "SV share (%)": pct(sv_block["morning_peak"]["sv_share_pct"]),
                },
                {
                    "Time window": "Afternoon peak",
                    f"Total {mode}": int(round(sv_block["afternoon_peak"]["total"])),
                    f"SV {mode}": int(round(sv_block["afternoon_peak"]["sv"])),
                    "SV share (%)": pct(sv_block["afternoon_peak"]["sv_share_pct"]),
                },
            ])

            st.dataframe(df_sv, use_container_width=True, hide_index=True)
            
            # Display each generated image with download button
            for png_bytes, out_name in png_list:
                st.image(
                    png_bytes,
                    caption=out_name,
                    use_container_width=True
                )

                st.download_button(
                    label=f"Download {out_name}",
                    data=png_bytes,
                    file_name=out_name,
                    mime="image/png",
                )

        except Exception as e:
            # Display error if anything goes wrong
            st.error(f"Error: {e}")