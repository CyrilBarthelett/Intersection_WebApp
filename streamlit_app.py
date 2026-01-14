import streamlit as st
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
            png_list = generate_png_from_excel(excel_bytes, side_colors)

            # Success message
            st.success("Done!")

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