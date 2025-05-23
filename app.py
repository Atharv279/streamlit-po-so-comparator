import streamlit as st
from dotenv import load_dotenv
import os
import PyPDF2
import requests
import re
from fpdf import FPDF
import io

# Load API Key
load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    st.error("❌ GROQ_API_KEY missing in .env file.")
    st.stop()

st.set_page_config(page_title="Smart Document Comparator", layout="centered")
st.title("AI Comparator")
st.caption("AI-powered PO/SO comparison with automatic field detection")

col1, col2 = st.columns(2)
with col1:
    so_file = st.file_uploader("Upload Sales Order (PDF)", type=["pdf"])
with col2:
    po_file = st.file_uploader("Upload Purchase Order (PDF)", type=["pdf"])

def text_to_pdf(text):
    from fpdf import FPDF
    import io

    class PDF(FPDF):
        def __init__(self):
            super().__init__()
            self.set_auto_page_break(auto=True, margin=15)
            self.add_page()
            self.set_font("Arial", size=10)

        def draw_table_row(self, cells, col_widths, line_height):
            max_lines = 0
            # First calculate the max number of lines required
            for i, cell in enumerate(cells):
                num_lines = self.get_string_width(cell) / (col_widths[i] - 2)
                max_lines = max(max_lines, int(num_lines) + 1)

            total_height = line_height * max_lines

            y_start = self.get_y()
            x_start = self.get_x()

            for i, cell in enumerate(cells):
                x = x_start + sum(col_widths[:i])
                self.set_xy(x, y_start)
                self.multi_cell(col_widths[i], line_height, cell, border=1)

            self.set_y(y_start + total_height)

    pdf = PDF()

    lines = text.split('\n')
    is_table = False
    col_widths = []
    for line in lines:
        if re.match(r"^\s*\|.*\|\s*$", line):  # It's a table line
            cells = [c.strip() for c in line.strip('|').split('|')]
            if not col_widths:
                col_count = len(cells)
                page_width = pdf.w - 20  # Account for margins
                col_widths = [page_width / col_count] * col_count
            pdf.draw_table_row(cells, col_widths, 6)
            is_table = True
        elif re.match(r"^[-| ]+$", line):  # Skip Markdown separators
            continue
        else:
            col_widths = []  # Reset column widths when out of table
            pdf.multi_cell(0, 8, line)
            is_table = False

    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output = io.BytesIO(pdf_bytes)
    pdf_output.seek(0)
    return pdf_output


def safe_extract_text(pdf_file, max_pages=10):
    if not pdf_file:
        return ""
    try:
        reader = PyPDF2.PdfReader(pdf_file)
        return "\n".join([page.extract_text() or "" for i, page in enumerate(reader.pages) if i < max_pages])
    except Exception as e:
        st.error(f"⚠️ Error reading PDF: {str(e)}")
        return ""

def call_groq_api(prompt, model="llama3-70b-8192"):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {groq_api_key}", "Content-Type": "application/json"}
    data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a senior procurement analyst. Create comparison tables for document alignment."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    return response.json()

def remove_duplicates(text):
    seen = set()
    output = []
    for block in re.split(r'\n(?=🧠|✅|❌|📌|MATCHING|DISCREPANCIES|SUMMARY)', text):
        if block.strip() not in seen:
            seen.add(block.strip())
            output.append(block)
    return "\n".join(output)

if so_file and po_file:
    if st.button("🔍 Generate Comparison Report", type="primary"):
        with st.spinner("Analyzing documents..."):
            try:
                so_text = safe_extract_text(so_file)
                po_text = safe_extract_text(po_file)

                if not so_text or not po_text:
                    st.error("Could not extract text from one or both files")
                    st.stop()

                prompt = f"""
You are a procurement analyst. Compare a Purchase Order (PO) and a Sales Order (SO) and produce a structured report with:

✅ MATCHING INFORMATION  
Tabulate fields that are present and identical in both documents:
| Field | PO-1 | SO - 1 |

❌ DISCREPANCIES IDENTIFIED  
Tabulate fields that differ or are missing:
| Category | PO-1 | SO-1 | Discrepancy Explanation |
|----------|------|------|--------------------------|

📌 SUMMARY  
Provide a concise summary (no more than 150 words) in paragraph format. Summarize key risks, actionable suggestions, and any important confirmations required between the buyer and vendor. Do not use bullet points or headings.

PO TEXT:
{po_text[:10000]}

SO TEXT:
{so_text[:10000]}
"""

                result = call_groq_api(prompt)
                raw_report = result["choices"][0]["message"]["content"]
                cleaned_report = remove_duplicates(raw_report)

                st.markdown(cleaned_report)

                pdf_report = text_to_pdf(cleaned_report)
                st.download_button(
                        label="📥 Download Full Report (PDF)",
                        data=pdf_report,
                        file_name="po_so_comparison.pdf",
                        mime="application/pdf"
)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 413:
                    st.error("Document too large. Try splitting into smaller sections.")
                else:
                    st.error(f"API Error: {e.response.text}")
            except Exception as e:
                st.error(f"Comparison failed: {str(e)}")
else:
    st.info("👆 Upload both PO and SO documents to begin")

# Blue-White UI Theme
st.markdown("""
<style>
body, .main, .block-container {
    background-color: #ffffff !important;
    color: #2c3e50;
    font-family: 'Segoe UI', sans-serif;
}
h1 {
    color: #1e3a8a;
    font-weight: 700;
}
.caption, .stCaption {
    color: #6b7280;
}
button[kind="primary"] {
    background-color: #1e40af !important;
    color: white !important;
    border-radius: 8px;
    padding: 0.6em 1.2em;
    font-weight: 600;
}
button[kind="primary"]:hover {
    background-color: #1d4ed8 !important;
}
section[data-testid="stFileUploader"] > div {
    border: 2px dashed #60a5fa;
    border-radius: 10px;
    background-color: #f0f9ff;
}
table {
    width: 100%;
    border-collapse: collapse;
}
th, td {
    border: 1px solid #e2e8f0;
    padding: 10px;
    text-align: left;
}
tr:nth-child(even) {
    background-color: #f8fafc;
}
button[title="Download"] {
    background-color: #2563eb !important;
    color: white !important;
    border-radius: 6px;
}
</style>
""", unsafe_allow_html=True)
