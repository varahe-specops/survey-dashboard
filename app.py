import streamlit as st
import pandas as pd
from fpdf import FPDF
from fpdf.fonts import FontFace
from contextlib import contextmanager # For table cell width calculation
import io # For st.download_button

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

def create_pdf_section_for_ac(pdf, ac_name, selected_question_text, tables_data):
    """
    Adds a section to the PDF for a given AC, including its tables.

    Args:
        pdf (FPDF): The FPDF object to add content to.
        ac_name (str): The name of the Assembly Constituency.
        selected_question_text (str): The survey question text.
        tables_data (list): A list of tuples, where each tuple is
                            (demographic_display_name, table_df).
    """
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Assembly Constituency: {ac_name}", ln=True, align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, f"Survey Question: {selected_question_text}", ln=True, align="C")
    pdf.ln(5) # Add a little space

    for demo_title, table_df in tables_data:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 10, demo_title, ln=True, align="L")

        if table_df.empty:
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 10, "No data available for this section.", ln=True)
            pdf.ln(5)
            continue

        pdf.set_font("Helvetica", "", 8) # Smaller font for table content

        # Headers
        header_height = 7
        col_widths = []

        # Dynamically calculate column widths based on content (simplified approach)
        # A more robust approach might involve pre-calculating max content width per column
        # For now, let's try to distribute width, giving more to the first column (demographic name)
        num_cols = len(table_df.columns)
        available_width = pdf.w - 2 * pdf.l_margin

        if num_cols > 0:
            # Give the first column (demographic category) a bit more space
            first_col_width_share = 0.30 # 30% for the first column
            other_cols_width_share = (1.0 - first_col_width_share) / (num_cols -1) if num_cols > 1 else 0

            col_widths.append(available_width * first_col_width_share)
            for _ in range(num_cols - 1):
                col_widths.append(available_width * other_cols_width_share)

        # Fallback if something went wrong with width calculation or no columns
        if not col_widths or num_cols == 0:
             col_widths = [available_width / num_cols if num_cols > 0 else available_width] * num_cols


        pdf.set_fill_color(200, 220, 255) # Light blue for header
        is_first_col = True
        for idx, col_name in enumerate(table_df.columns):
            current_col_width = col_widths[idx] if idx < len(col_widths) else (available_width / num_cols)
            pdf.cell(current_col_width, header_height, str(col_name), border=1, fill=True, align='C')
        pdf.ln(header_height)

        # Data rows
        row_height = 6
        pdf.set_fill_color(240, 240, 240) # Light grey for alternating rows
        fill_row = False
        for _, row in table_df.iterrows():
            for idx, item in enumerate(row):
                current_col_width = col_widths[idx] if idx < len(col_widths) else (available_width / num_cols)
                # Check if item is numeric (int or float) to align right, else left
                align = 'R' if isinstance(item, (int, float)) and not isinstance(item, bool) else 'L'
                # If it's a percentage string, also align right
                if isinstance(item, str) and '%' in item:
                    align = 'R'
        
                # For the "Grand Total" row, make text bold
                if str(row.iloc[0]) == "Grand Total": # Using iloc[0] instead of row[0]
                    pdf.set_font("Arial", "B", 8)  # Use Arial instead of Helvetica
                else:
                    pdf.set_font("Arial", "", 8)   # Use Arial instead of Helvetica
        
                # Use regular cell instead of multi_cell for table consistency
                pdf.cell(current_col_width, row_height, str(item), border=1, fill=fill_row, align=align)
            
            pdf.ln(row_height) # Move to next row
            fill_row = not fill_row # Alternate row fill
        pdf.ln(5) # Space after table
    pdf.set_font("Helvetica", "", 10) # Reset font

def generate_combined_ac_pdf(df_full_data, list_of_acs_to_process, selected_question,
                                 demographic_cols_config, ui_response_columns_ordered,
                                 original_grand_total_row_data_template, original_ac_display_name_for_grand_total):
    """
    Generates a combined PDF report for multiple ACs.

    Args:
        df_full_data (pd.DataFrame): The complete survey dataset.
        list_of_acs_to_process (list): List of AC names to include in the PDF.
        selected_question (str): The survey question being reported on.
        demographic_cols_config (dict): Config for demographic columns (display_name: actual_col).
        ui_response_columns_ordered (list): Ordered list of response columns for tables.
        original_grand_total_row_data_template (dict): The grand total data calculated for the UI based on selected ACs.
                                                         This will be RECALCULATED per AC for the PDF.
        original_ac_display_name_for_grand_total (str): The AC display name used for the UI's grand total.
                                                        This will be overridden per AC for the PDF.

    Returns:
        bytes: The generated PDF content.
    """
    pdf = FPDF(orientation="L", unit="mm", format="A4") # Landscape, A4
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=10)

    if not list_of_acs_to_process:
        # Handle case with no ACs to process (e.g., if 'All' is chosen but no ACs exist)
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 10, "No Assembly Constituencies selected or available for the report.", ln=True, align="C")
        return pdf.output(dest='S').encode('latin-1')

    for ac_name in list_of_acs_to_process:
        # 1. Filter data for the current AC
        ac_specific_df = df_full_data[df_full_data["AC Name"] == ac_name].copy()

        if ac_specific_df.empty:
            # Add a page indicating no data for this AC for this question
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, f"Assembly Constituency: {ac_name}", ln=True, align="C")
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, f"Survey Question: {selected_question}", ln=True, align="C")
            pdf.ln(10)
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(0, 10, "No survey data found for this constituency for the selected question.", ln=True, align="L")
            continue

        # 2. Recalculate response_columns_ordered for THIS AC's data (important!)
        #    This mirrors the logic in the Streamlit display part.
        if selected_question == "Do you know who the KPCC President is?":
            current_ac_response_columns_ordered = ['No', 'Yes']
            unique_responses_in_ac_data = ac_specific_df[selected_question].fillna("Not Answered").astype(str).unique()
            if "Not Answered" in unique_responses_in_ac_data and "Not Answered" not in current_ac_response_columns_ordered:
                current_ac_response_columns_ordered.append("Not Answered")
        else:
            current_ac_response_columns_ordered = sorted(ac_specific_df[selected_question].fillna("Not Answered").astype(str).unique().tolist())

        if not current_ac_response_columns_ordered: # If question has no responses in this AC
             current_ac_response_columns_ordered = ui_response_columns_ordered # Fallback

        # 3. Recalculate Grand Total row for THIS AC
        ac_grand_total_row_data = {}
        ac_grand_total_base_count = len(ac_specific_df)
        ac_grand_total_row_data["Total Number"] = ac_grand_total_base_count

        ac_question_responses_series = ac_specific_df[selected_question].fillna("Not Answered").astype(str)
        ac_counts_for_grand_total = ac_question_responses_series.value_counts()

        for resp in current_ac_response_columns_ordered:
            count = ac_counts_for_grand_total.get(resp, 0)
            percentage = (count / ac_grand_total_base_count * 100) if ac_grand_total_base_count > 0 else 0
            ac_grand_total_row_data[f"{resp} %"] = f"{percentage:.2f}%"


        # 4. Generate table DataFrames for this AC (adapting UI logic)
        tables_for_this_ac_pdf = [] # List of (title, df)
        for demo_display_name, demo_actual_col in demographic_cols_config.items():
            if demo_actual_col not in ac_specific_df.columns:
                # Add info that this demographic column is missing for this AC
                missing_df = pd.DataFrame({'Status': [f"Demographic column '{demo_display_name}' not found for AC: {ac_name}."]})
                tables_for_this_ac_pdf.append((f"{demo_display_name} - Data Missing", missing_df))
                continue

            df_for_crosstab = ac_specific_df.copy()
            df_for_crosstab[selected_question] = df_for_crosstab[selected_question].fillna("Not Answered").astype(str)
            df_for_crosstab[demo_actual_col] = df_for_crosstab[demo_actual_col].fillna("Not Specified").astype(str)

            if df_for_crosstab.empty:
                empty_df = pd.DataFrame({'Status': ["No data for this demographic group."]})
                tables_for_this_ac_pdf.append((demo_display_name, empty_df))
                continue

            try:
                crosstab_df = pd.crosstab(df_for_crosstab[demo_actual_col], df_for_crosstab[selected_question])
                for resp in current_ac_response_columns_ordered: # Use AC-specific response order
                    if resp not in crosstab_df.columns:
                        crosstab_df[resp] = 0
                crosstab_df = crosstab_df[current_ac_response_columns_ordered]

                crosstab_df["Total Number"] = crosstab_df[current_ac_response_columns_ordered].sum(axis=1)

                percentage_cols_display_order = []
                for resp_col in current_ac_response_columns_ordered:
                    perc_col_name = f"{resp_col} %"
                    percentage_cols_display_order.append(perc_col_name)
                    crosstab_df[perc_col_name] = (crosstab_df[resp_col] / crosstab_df["Total Number"].replace(0, pd.NA) * 100)

                crosstab_df = crosstab_df.reset_index()
                crosstab_df.rename(columns={demo_actual_col: demo_display_name}, inplace=True)

                display_cols_final_order = [demo_display_name, "Total Number"] + percentage_cols_display_order
                table_df_final = crosstab_df[display_cols_final_order].copy()

                # Add AC-specific Grand Total row
                grand_total_row_to_append = ac_grand_total_row_data.copy() # Use AC specific grand total
                grand_total_row_to_append[demo_display_name] = "Grand Total"

                for col in table_df_final.columns:
                    if col not in grand_total_row_to_append:
                        grand_total_row_to_append[col] = pd.NA

                grand_total_df_for_table = pd.DataFrame([grand_total_row_to_append])[table_df_final.columns]
                table_df_final = pd.concat([table_df_final, grand_total_df_for_table], ignore_index=True)

                for p_col in percentage_cols_display_order:
                    if p_col in table_df_final.columns:
                        table_df_final[p_col] = table_df_final[p_col].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) and isinstance(x, (int, float)) else x)

                tables_for_this_ac_pdf.append((demo_display_name, table_df_final))
            except Exception as e:
                error_df = pd.DataFrame({'Error': [f"Could not generate table for {demo_display_name}: {e}"]})
                tables_for_this_ac_pdf.append((f"{demo_display_name} - Error", error_df))

        # 5. Call the core PDF function to add this AC's section
        if tables_for_this_ac_pdf:
            create_pdf_section_for_ac(pdf, ac_name, selected_question, tables_for_this_ac_pdf)
        else: # Should not happen if demographic_cols_config is not empty, but as a safe guard
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, f"Assembly Constituency: {ac_name}", ln=True, align="C")
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, f"Survey Question: {selected_question}", ln=True, align="C")
            pdf.ln(10)
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(0, 10, "No tables could be generated for this AC.", ln=True, align="L")

    return pdf.output(dest='B') # Return PDF as bytes

df_survey_original = load_data(GOOGLE_SHEET_CSV_URL)

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

    # --- PDF Download Button ---
    if selected_question and not df_survey_original.empty:
        acs_for_pdf_report = []
        if "AC Name" in df_survey_original.columns:
            all_unique_acs = sorted(df_survey_original["AC Name"].unique().tolist())
            # If multiselect is empty (which means 'All' effectively based on UI behavior)
            # OR 'All' is explicitly selected (possibly with others, where 'All' takes precedence in UI)
            if not selected_acs or "All" in selected_acs:
                acs_for_pdf_report = all_unique_acs
            else: # Specific ACs are selected (and "All" is not among them)
                acs_for_pdf_report = [ac for ac in selected_acs if ac in all_unique_acs and ac != "All"]

        if not acs_for_pdf_report:
            st.warning("No specific ACs available/selected for the PDF report based on current data. The generated PDF will indicate this if it's empty.")
            # PDF generation will still proceed; `generate_combined_ac_pdf` handles an empty list.

        # Use the already calculated response_columns_ordered and grand_total_row_data from the UI's current context.
        # These are based on `current_df` and provide a template/fallback for the PDF generation function,
        # which will then recalculate these accurately for each individual AC from `df_survey_original`.
        ui_main_response_columns_ordered = response_columns_ordered
        ui_main_grand_total_data = grand_total_row_data

        pdf_bytes = generate_combined_ac_pdf(
            df_full_data=df_survey_original, # Use the full dataset for PDF processing
            list_of_acs_to_process=acs_for_pdf_report,
            selected_question=selected_question,
            demographic_cols_config=demographic_cols_for_tables,
            ui_response_columns_ordered=ui_main_response_columns_ordered,
            original_grand_total_row_data_template=ui_main_grand_total_data,
            original_ac_display_name_for_grand_total=ac_header_display # UI's current AC display name
        )

        # Sanitize question for filename (max 30 chars for question part)
        safe_question_part = "".join(c if c.isalnum() or c in [' '] else '_' for c in selected_question).replace(' ', '_')
        pdf_file_name = f"combined_ac_report_{safe_question_part[:30]}.pdf"

        st.download_button(
            label="Download Combined AC Report (PDF)",
            data=pdf_bytes,
            file_name=pdf_file_name,
            mime="application/pdf",
            key="pdf_download_button"
        )
    # Add a separator after the button section, before the tables are displayed
    st.markdown("---")

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
