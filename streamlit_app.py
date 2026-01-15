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
            png_list, meta = generate_png_from_excel(excel_bytes, side_colors)

            # Success message
            st.success("Done!")

                        # ------------------------------
            # KFZ by direction (table)
            # ------------------------------
            st.subheader("KFZ traffic by direction")

            df_kfz = pd.DataFrame(meta["per_direction"])
            df_kfz = df_kfz.rename(columns={
                "direction": "Direction",
                "full_day_kfz": "Full day (KFZ)",
                "morning_peak_kfz": "Morning peak (KFZ)",
                "afternoon_peak_kfz": "Afternoon peak (KFZ)",
            })

            # optional: make numbers nicer
            for col in ["Full day (KFZ)", "Morning peak (KFZ)", "Afternoon peak (KFZ)"]:
                df_kfz[col] = df_kfz[col].round(0).astype(int)

            st.dataframe(df_kfz, use_container_width=True, hide_index=True)

            # Optional: show totals similar to your time cards
            t1, t2, t3 = st.columns(3)
            with t1:
                st.markdown("**Total full day (KFZ)**")
                st.write(int(round(meta["totals"]["full_day_kfz"])))
            with t2:
                st.markdown("**Total morning peak (KFZ)**")
                st.write(int(round(meta["totals"]["morning_peak_kfz"])))
            with t3:
                st.markdown("**Total afternoon peak (KFZ)**")
                st.write(int(round(meta["totals"]["afternoon_peak_kfz"])))

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