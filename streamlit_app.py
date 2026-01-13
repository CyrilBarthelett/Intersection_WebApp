import streamlit as st
from main import generate_png_from_excel

# --------------------------------------------------
# Page configuration (must be first Streamlit call)
# --------------------------------------------------
st.set_page_config(page_title="Traffic Flow Plot",page_icon="🛣️",layout="centered")

# --------------------------------------------------
# Page title and instructions
# --------------------------------------------------
st.title("Traffic Flow Plot Generator")
st.write("Upload an Excel traffic count file (`.xlsx`) ""and download the generated PNG.")

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

            # Generate PNG image and filename
            png_bytes, out_name = generate_png_from_excel(excel_bytes)

            # Success message
            st.success("Done!")

            # Display the generated image
            st.image(
                png_bytes,
                caption=out_name,
                use_container_width=True
            )

            # Download button for the PNG
            st.download_button(
                label="Download PNG",
                data=png_bytes,
                file_name=out_name,
                mime="image/png",
            )

        except Exception as e:
            # Display error if anything goes wrong
            st.error(f"Failed to generate plot: {e}")