import streamlit as st
import pdfplumber
import pandas as pd
from pathlib import Path
from fuzzywuzzy import fuzz

st.set_page_config(page_title="TAL TravisMathew Costing Portal", layout="wide")
st.title("🧥 TAL TravisMathew Costing Portal")

@st.cache_data
def load_master():
    df = pd.read_excel("TravisMathew Master Trim List.xlsx")
    st.write("**Master Columns:**", df.columns.tolist())   # for debug
    # Force Unit Cost to be numeric
    if 'Unit Cost' in df.columns:
        df['Unit Cost'] = pd.to_numeric(df['Unit Cost'], errors='coerce')
    st.success(f"✅ Master Trim List loaded! ({len(df)} items)")
    return df

master = load_master()

def clean_and_extract_bom(pdf_path):
    all_rows = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            
            if any(x in text for x in ["Material (", "Materials"]):
                current_section = "Materials"
            else:
                current_section = "Trims, Packaging & Artwork"
            
            tables = page.extract_tables()
            for table in tables:
                if table and len(table) > 1:
                    headers = [str(h).strip() if h else f"Col_{i}" for i, h in enumerate(table[0])]
                    for row in table[1:]:
                        row_str = " ".join(str(cell).strip() for cell in row if cell)
                        if not row_str or "Displaying" in row_str or "results" in row_str.lower() or "" in row_str:
                            continue
                        if any(x in row_str for x in ["Materials (", "Trim (", "Artwork (", "Packaging ("]):
                            continue
                        
                        row_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row))) if row[i] is not None}
                        row_dict['Source_Page'] = page_num
                        row_dict['Section'] = current_section
                        all_rows.append(row_dict)
    
    df = pd.DataFrame(all_rows)
    return df if not df.empty else None

# ================== MAIN APP ==================
st.sidebar.warning("⚠️ Please **close the PDF file** before uploading it")

uploaded_file = st.sidebar.file_uploader("Upload Tech Pack PDF", type="pdf")

if uploaded_file and master is not None:
    with st.spinner("Processing tech pack..."):
        temp_path = Path(f"temp_{uploaded_file.name}")
        try:
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            bom_df = clean_and_extract_bom(temp_path)
            
            if bom_df is not None:
                dedup_cols = ['Material Name', 'Product']
                dedup_cols = [col for col in dedup_cols if col in bom_df.columns]
                if dedup_cols:
                    bom_df = bom_df.drop_duplicates(subset=dedup_cols, keep='first')
                
                bom_df['Unit Cost'] = None
                bom_df['Match_Score'] = 0
                bom_df['Match_Note'] = ""
                
                for idx, row in bom_df.iterrows():
                    material = str(row.get('Material Name', '') or row.get('Material', '')).strip()
                    prod_code = str(row.get('Product', '')).strip()
                    
                    # 1. Exact Product Code
                    match = master[master['Product'] == prod_code]
                    if not match.empty:
                        bom_df.at[idx, 'Unit Cost'] = match.iloc[0].get('Unit Cost')
                        bom_df.at[idx, 'Match_Score'] = 100
                        bom_df.at[idx, 'Match_Note'] = "Exact Product Code"
                    # 2. Fuzzy on Material Name
                    elif material:
                        best_score = 0
                        best_cost = None
                        for _, m_row in master.iterrows():
                            score = fuzz.token_sort_ratio(material.upper(), str(m_row.get('Material Name', '')).upper())
                            if score > best_score:
                                best_score = score
                                best_cost = m_row.get('Unit Cost')
                        if best_score > 55:   # lowered threshold
                            bom_df.at[idx, 'Unit Cost'] = best_cost
                            bom_df.at[idx, 'Match_Score'] = best_score
                            bom_df.at[idx, 'Match_Note'] = f"Fuzzy ({best_score}%)"
                
                st.subheader(f"✅ Processed: {uploaded_file.name} ({len(bom_df)} items)")
                
                for section in ["Materials", "Trims, Packaging & Artwork"]:
                    section_df = bom_df[bom_df['Section'] == section]
                    if not section_df.empty:
                        st.markdown(f"### {section}")
                        display_cols = [col for col in ['Product', 'Material Name', 'Material', 'Supplier', 'Unit Cost', 'Match_Score', 'Match_Note'] if col in section_df.columns]
                        st.dataframe(section_df[display_cols], use_container_width=True)
                
                csv = bom_df.to_csv(index=False).encode('utf-8')
                st.download_button("Download Full CSV", csv, f"{uploaded_file.name}_costing.csv", "text/csv")
        
        finally:
            temp_path.unlink(missing_ok=True)

st.caption("Portal v1.9 - Aggressive Matching")