import streamlit as st
import pandas as pd
from fpdf import FPDF
import io

# --- Configuration ---
st.set_page_config(layout="wide", page_title="Survey Data Analysis")

# --- Data Loading ---
# Replace with your actual Google Sheet CSV link
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQPm63U2trERuMHq9KqyY2yHXB5TzIKb5kzASsKmNobBAq9f1rEu8_OEyhY8gY6mXjuwvQf90Sr0Q7I/pub?gid=0&single=true&output=csv" # Replace this

@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_data(url):
    try:
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        for col in df.select_dtypes(include=['object']):
            df[col] = df[col].str.strip()
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

df_survey_original = load_data(GOOGLE_SHEET_CSV_URL)


def _generate_table_df(df_ac, selected_question, demo_display_name, demo_actual_col, response_columns_ordered):
    """Create the cross tabulation table dataframe for one AC and demographic."""
    df_for_crosstab = df_ac.copy()
    df_for_crosstab[selected_question] = df_for_crosstab[selected_question].fillna("Not Answered").astype(str)
    df_for_crosstab[demo_actual_col] = df_for_crosstab[demo_actual_col].fillna("Not Specified").astype(str)
    if df_for_crosstab.empty:
        return pd.DataFrame()

    crosstab_df = pd.crosstab(df_for_crosstab[demo_actual_col], df_for_crosstab[selected_question])
    for resp in response_columns_ordered:
        if resp not in crosstab_df.columns:
            crosstab_df[resp] = 0
    crosstab_df = crosstab_df[response_columns_ordered]
    crosstab_df["Total Number"] = crosstab_df.sum(axis=1)

    for resp in response_columns_ordered:
        perc_col = f"{resp} %"
        crosstab_df[perc_col] = (crosstab_df[resp] / crosstab_df["Total Number"].replace(0, pd.NA) * 100)

    crosstab_df = crosstab_df.reset_index()
    crosstab_df.rename(columns={demo_actual_col: demo_display_name}, inplace=True)

    display_cols_final_order = [demo_display_name, "Total Number"] + [f"{resp} %" for resp in response_columns_ordered]
    table_df_final = crosstab_df[display_cols_final_order].copy()

    grand_total_base_count = len(df_ac)
    grand_total_row = {demo_display_name: "Grand Total", "Total Number": grand_total_base_count}
    counts = df_ac[selected_question].fillna("Not Answered").astype(str).value_counts()
    for resp in response_columns_ordered:
        count = counts.get(resp, 0)
        perc = (count / grand_total_base_count * 100) if grand_total_base_count > 0 else 0
        grand_total_row[f"{resp} %"] = perc

    for col in table_df_final.columns:
        if col not in grand_total_row:
            grand_total_row[col] = pd.NA
    grand_total_df = pd.DataFrame([grand_total_row])[table_df_final.columns]
    table_df_final = pd.concat([table_df_final, grand_total_df], ignore_index=True)

    for resp in response_columns_ordered:
        perc_col = f"{resp} %"
        table_df_final[perc_col] = table_df_final[perc_col].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else x)
    return table_df_final


def create_combined_ac_pdf(df, selected_question, demographics):
    """Generate a PDF with tables for each AC in the DataFrame."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    if selected_question == "Do you know who the KPCC President is?":
        response_columns_ordered = ["No", "Yes"]
        unique_responses = df[selected_question].fillna("Not Answered").astype(str).unique()
        if "Not Answered" in unique_responses and "Not Answered" not in response_columns_ordered:
            response_columns_ordered.append("Not Answered")
    else:
        response_columns_ordered = sorted(df[selected_question].fillna("Not Answered").astype(str).unique())

    for ac in sorted(df["AC Name"].dropna().unique()):
        ac_df = df[df["AC Name"] == ac]
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, f"Constituency: {ac}", ln=True)

        for demo_display, demo_actual_col in demographics.items():
            if demo_actual_col not in ac_df.columns:
                continue
            table_df = _generate_table_df(ac_df, selected_question, demo_display, demo_actual_col, response_columns_ordered)
            if table_df.empty:
                continue
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, demo_display, ln=True)
            pdf.set_font("Courier", size=8)
            table_text = table_df.to_string(index=False)
            pdf.multi_cell(0, 4, table_text)
            pdf.ln(2)

    return pdf.output(dest="S").encode("latin-1")

# --- Dashboard UI ---
st.title("Survey Data Analysis")

if df_survey_original.empty:
    st.warning("Could not load survey data. Please check the Google Sheet URL and ensure it's published correctly.")
else:
    # --- Define Columns for Selections ---
    survey_question_columns = [
        "Do you know who the KPCC President is?",
        "Can you name the person?",
        "Who is your favorite candidate for Chief Minister?",
        "Who do you think will win in your constituency?",
        "Who do you think will win the overall State Assembly Elections?",
        "Whom will you vote for?"
    ]
    survey_question_columns = [col for col in survey_question_columns if col in df_survey_original.columns]

    demographic_cols_for_tables = {
        "What is your gender?": "What is your gender?",
        "What is your age?": "What is your age?",
        "What is your religion?": "What is your religion?",
        "What is your community?": "What is your community?"
    }
    # Filter out demographic columns not present in the DataFrame
    demographic_cols_for_tables = {
        display: actual for display, actual in demographic_cols_for_tables.items()
        if actual in df_survey_original.columns
    }

    # --- Main Selectors ---
    col_q, col_ac = st.columns(2)

    with col_q:
        selected_question = st.selectbox(
            "Select Survey Question",
            options=survey_question_columns,
            index=0 if survey_question_columns else None,
            key="survey_question_selector"
        )

    ac_options = ["All"] + sorted(df_survey_original["AC Name"].unique().tolist()) if "AC Name" in df_survey_original.columns else ["All"]
    with col_ac:
        selected_acs = st.multiselect(
            "Select Assembly Constituency (select 'All' for overall, or multiple individual ACs)",
            options=ac_options,
            default=["All"],
            key="ac_multiselect"
        )
    
    st.markdown("---")

    # --- Filtering Data based on AC ---
    current_df = df_survey_original.copy()
    ac_header_display = "All Constituencies"

    if selected_acs:
        if "All" in selected_acs and len(selected_acs) > 1:
            # If "All" is selected with others, prioritize "All"
            selected_acs = ["All"]
            st.info("Showing data for 'All' constituencies as 'All' was selected.")
            ac_header_display = "All Constituencies"
        elif "All" in selected_acs:
            ac_header_display = "All Constituencies"
            # No AC filtering needed if "All" is the only selection
        elif selected_acs: # Specific ACs are selected
            current_df = current_df[current_df["AC Name"].isin(selected_acs)]
            ac_header_display = ", ".join(selected_acs)
    else: # No ACs selected (multiselect is empty)
        st.warning("No Assembly Constituency selected. Showing data for ALL constituencies by default.")
        ac_header_display = "All Constituencies (Default - None Selected)"
        # current_df remains df_survey_original.copy()

    # --- Display Header ---
    if selected_question:
        st.markdown(f"## {selected_question}")
        st.markdown(f"#### Constituency: {ac_header_display}")
        st.markdown("---")
    else:
        st.info("Please select a survey question.")
        st.stop()

    # --- Determine Response Columns for the selected question ---
    # For the specific KPCC question, we prioritize "No" and "Yes" as per the image
    if selected_question == "Do you know who the KPCC President is?":
        response_columns_ordered = ['No', 'Yes']
        # Add 'Not Answered' if it exists in the data for this question after filtering
        unique_responses_in_data = current_df[selected_question].fillna("Not Answered").astype(str).unique()
        if "Not Answered" in unique_responses_in_data and "Not Answered" not in response_columns_ordered:
             response_columns_ordered.append("Not Answered")
    else:
        # For other questions, take all unique responses, sort them for consistency
        # (or you could take top N, etc.)
        response_columns_ordered = sorted(current_df[selected_question].fillna("Not Answered").astype(str).unique().tolist())


    # --- Pre-calculate Grand Total row data (based on current_df and selected_question) ---
    grand_total_row_data = {}
    if not current_df.empty:
        grand_total_base_count = len(current_df) # Total respondents in filtered ACs
        grand_total_row_data["Total Number"] = grand_total_base_count
        
        # Counts and percentages for the specific `response_columns_ordered`
        question_responses_series = current_df[selected_question].fillna("Not Answered").astype(str)
        counts_for_grand_total = question_responses_series.value_counts()

        for resp in response_columns_ordered:
            count = counts_for_grand_total.get(resp, 0)
            percentage = (count / grand_total_base_count * 100) if grand_total_base_count > 0 else 0
            grand_total_row_data[f"{resp} %"] = f"{percentage:.2f}%"
    else: # If current_df is empty after filtering
        grand_total_row_data["Total Number"] = 0
        for resp in response_columns_ordered:
            grand_total_row_data[f"{resp} %"] = "0.00%"


    # --- Generate and Display Cross-Tabulation Tables ---
    for demo_display_name, demo_actual_col in demographic_cols_for_tables.items():
        if demo_actual_col not in current_df.columns:
            st.warning(f"Demographic column '{demo_display_name}' not found in the data for the selected ACs.")
            continue

        st.subheader(f"{demo_display_name}")

        # Handle NaN values for crosstab creation
        df_for_crosstab = current_df.copy()
        df_for_crosstab[selected_question] = df_for_crosstab[selected_question].fillna("Not Answered").astype(str)
        df_for_crosstab[demo_actual_col] = df_for_crosstab[demo_actual_col].fillna("Not Specified").astype(str)

        if df_for_crosstab.empty:
            st.write("No data for this demographic group with current filters.")
            continue

        try:
            # Create the cross-tabulation for counts
            crosstab_df = pd.crosstab(df_for_crosstab[demo_actual_col], df_for_crosstab[selected_question])

            # Ensure all expected response_columns_ordered are present, add if missing
            for resp in response_columns_ordered:
                if resp not in crosstab_df.columns:
                    crosstab_df[resp] = 0
            
            # Reorder columns to ensure consistency (e.g., 'No' then 'Yes')
            crosstab_df = crosstab_df[response_columns_ordered]

            # Calculate "Total Number" for each category in the demographic column
            crosstab_df["Total Number"] = crosstab_df[response_columns_ordered].sum(axis=1)
            
            # Calculate percentages for each response within each demographic category
            percentage_cols_display_order = []
            for resp_col in response_columns_ordered:
                perc_col_name = f"{resp_col} %"
                percentage_cols_display_order.append(perc_col_name)
                crosstab_df[perc_col_name] = (crosstab_df[resp_col] / crosstab_df["Total Number"].replace(0, pd.NA) * 100)
            
            # Prepare the final display DataFrame
            crosstab_df = crosstab_df.reset_index()
            crosstab_df.rename(columns={demo_actual_col: demo_display_name}, inplace=True)
            
            display_cols_final_order = [demo_display_name, "Total Number"] + percentage_cols_display_order
            
            table_df_final = crosstab_df[display_cols_final_order].copy() # Use .copy() to avoid SettingWithCopyWarning

            # Add the pre-calculated Grand Total row
            grand_total_row_to_append = grand_total_row_data.copy()
            grand_total_row_to_append[demo_display_name] = "Grand Total" # Set the first column name
            
            # Ensure all columns exist in grand_total_row_to_append, fill with NA if not
            for col in table_df_final.columns:
                if col not in grand_total_row_to_append:
                    grand_total_row_to_append[col] = pd.NA 
            
            grand_total_df_for_table = pd.DataFrame([grand_total_row_to_append])[table_df_final.columns] # Ensure order and columns match
            
            table_df_final = pd.concat([table_df_final, grand_total_df_for_table], ignore_index=True)

            # Format percentages for display
            for p_col in percentage_cols_display_order:
                if p_col in table_df_final.columns:
                     table_df_final[p_col] = table_df_final[p_col].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) and isinstance(x, (int, float)) else x)
            
            st.dataframe(table_df_final, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Could not generate table for {demo_display_name}: {e}")
        st.markdown("---") # Separator between tables

    # --- Download Combined PDF Button ---
    if st.button("Download Combined AC PDF"):
        with st.spinner("Generating PDF..."):
            pdf_bytes = create_combined_ac_pdf(current_df, selected_question, demographic_cols_for_tables)
        st.download_button(
            label="Click to Download",
            data=pdf_bytes,
            file_name="ac_tables.pdf",
            mime="application/pdf",
        )

