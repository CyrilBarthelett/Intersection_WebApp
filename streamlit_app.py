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
            png_list, meta = generate_png_from_excel(excel_bytes, side_colors, d_NS=d_NS_value, d_WE=d_WE_value)

            # Success message
            st.success("Done!")

            # ------------------------------
            # KFZ | Bicycle by direction (table)
            # ------------------------------
            st.subheader("Traffic by direction (KFZ | Bicycle)")

            df = pd.DataFrame(meta["per_direction"])

            # Make integer columns (nice display)
            num_cols = [
                "full_day_kfz", "full_day_bike",
                "morning_peak_kfz", "morning_peak_bike",
                "afternoon_peak_kfz", "afternoon_peak_bike",
            ]
            for c in num_cols:
                df[c] = df[c].round(0).astype(int)

            # Build the "KFZ | Bicycle" strings
            df_out = pd.DataFrame({
                "Direction": df["direction"],
                "Full day (KFZ | Bicycle)": df["full_day_kfz"].astype(str) + " | " + df["full_day_bike"].astype(str),
                "Morning peak (KFZ | Bicycle)": df["morning_peak_kfz"].astype(str) + " | " + df["morning_peak_bike"].astype(str),
                "Afternoon peak (KFZ | Bicycle)": df["afternoon_peak_kfz"].astype(str) + " | " + df["afternoon_peak_bike"].astype(str),
            })

            st.dataframe(df_out, use_container_width=True, hide_index=True)

            t1, t2, t3 = st.columns(3)

            with t1:
                st.markdown("**Total full day (KFZ | Bicycle)**")
                st.write(f"{int(round(meta['totals']['full_day_kfz']))} | {int(round(meta['totals']['full_day_bike']))}")

            with t2:
                st.markdown("**Total morning peak (KFZ | Bicycle)**")
                st.write(f"{int(round(meta['totals']['morning_peak_kfz']))} | {int(round(meta['totals']['morning_peak_bike']))}")

            with t3:
                st.markdown("**Total afternoon peak (KFZ | Bicycle)**")
                st.write(f"{int(round(meta['totals']['afternoon_peak_kfz']))} | {int(round(meta['totals']['afternoon_peak_bike']))}")
                
            bd = meta["by_side"]["full_day"]
            df_side = pd.DataFrame({
                "Side": ["N", "E", "S", "W"],
                "Departing KFZ": [int(round(bd["dep_kfz"][s])) for s in ["N","E","S","W"]],
                "Arriving KFZ":  [int(round(bd["arr_kfz"][s])) for s in ["N","E","S","W"]],
                "Total KFZ":  [int(round(bd["total_kfz"][s])) for s in ["N","E","S","W"]],
            })
            st.dataframe(df_side, use_container_width=True, hide_index=True)

            # Show time ranges
            st.subheader("Detected time ranges")

            c1, c2, c3 = st.columns(3)

            with c1:
                st.markdown("**Full day**")
                st.write(f"Start: {meta['day']['start']}")
                st.write(f"End:   {meta['day']['end']}")

            with c2:
                st.markdown("**Morning peak**")
                st.write(f"Start: {meta['morning_peak']['start']}")
                st.write(f"End:   {meta['morning_peak']['end']}")

            with c3:
                st.markdown("**Afternoon peak**")
                st.write(f"Start: {meta['afternoon_peak']['start']}")
                st.write(f"End:   {meta['afternoon_peak']['end']}")
            
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