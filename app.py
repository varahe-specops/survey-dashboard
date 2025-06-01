import streamlit as st
import pandas as pd

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
        print(df.columns.tolist()) # Print column names
        for col in df.select_dtypes(include=['object']):
            df[col] = df[col].str.strip()
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

df_survey_original = load_data(GOOGLE_SHEET_CSV_URL)

# --- Dashboard UI ---
st.title("Survey Data Analysis")

if df_survey_original.empty:
    st.warning("Could not load survey data. Please check the Google Sheet URL and ensure it's published correctly.")
    st.stop() # Stop execution if data is not loaded
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

    # --- Early definition of selected_question for State Level Overview ---
    # This selector will also be used for the AC-level view later
    selected_question = st.selectbox(
        "Select Survey Question (for all analyses below)",
        options=survey_question_columns,
        index=0 if survey_question_columns else None,
        key="survey_question_selector"
    )

    # --- Determine Response Columns for the selected question (using df_survey_original) ---
    # This needs to be defined early for the state-level summary
    response_columns_ordered = []
    if selected_question and selected_question in df_survey_original.columns:
        if selected_question == "Do you know who the KPCC President is?":
            response_columns_ordered = ['No', 'Yes']
            unique_responses_in_data = df_survey_original[selected_question].fillna("Not Answered").astype(str).unique()
            if "Not Answered" in unique_responses_in_data and "Not Answered" not in response_columns_ordered:
                response_columns_ordered.append("Not Answered")
        else:
            response_columns_ordered = sorted(df_survey_original[selected_question].fillna("Not Answered").astype(str).unique().tolist())
    elif not selected_question:
        st.info("Please select a survey question to see the analysis.")
        st.stop()
    else: # selected_question is not in df_survey_original.columns (should not happen with current logic)
        st.error(f"Selected question '{selected_question}' not found in the data. Please check column names.")
        st.stop()


    # --- State Level Overview ---
    st.header("State Level Overview")
    if not df_survey_original.empty and selected_question:
        st.subheader(f"Summary for: {selected_question}")
        total_respondents_state = len(df_survey_original)

        state_summary_data = []
        if total_respondents_state > 0:
            question_responses_state = df_survey_original[selected_question].fillna("Not Answered").astype(str)
            counts_state = question_responses_state.value_counts()

            for resp_option in response_columns_ordered:
                count = counts_state.get(resp_option, 0)
                percentage = (count / total_respondents_state * 100) if total_respondents_state > 0 else 0
                state_summary_data.append({
                    "Response": resp_option,
                    "Count": count,
                    "Percentage": f"{percentage:.2f}%"
                })

        if state_summary_data:
            state_summary_df = pd.DataFrame(state_summary_data)
            st.dataframe(state_summary_df, use_container_width=True, hide_index=True)
        else:
            st.write("No response data to display for the selected question at the state level.")

    else:
        st.write("No data available for state overview or no question selected.")
    st.markdown("---") # Separator after state-level overview

    # --- Placeholder for Navigation Path Selection ---
    st.markdown("##### Intended Data Navigation Path")
    st.radio(
        "Select your preferred drill-down path (will be enabled when data is available):",
        options=[
            "State ➔ Zone ➔ District ➔ AC",
            "State ➔ District ➔ AC",
            "State ➔ AC Name"
        ],
        index=2,  # Default to "State -> AC Name" as it's the current de facto path
        disabled=True,
        help="Full navigation options will be enabled when Zone and District data columns are provided in the Google Sheet."
    )
    # Adding a little space before the next set of placeholders
    st.markdown("<br>", unsafe_allow_html=True)

    # --- Placeholder Filters for Zone and District ---
    st.info("Zone and District level filtering will be enabled when corresponding columns are available in the Google Sheet.")

    col_zone_district_placeholder1, col_zone_district_placeholder2 = st.columns(2)
    with col_zone_district_placeholder1:
        st.selectbox(
            "Select Zone",
            ["N/A - Zone data not available in source"],
            disabled=True,
            help="Zone-level filtering will be enabled when 'Zone' data is provided in the Google Sheet."
        )
    with col_zone_district_placeholder2:
        st.selectbox(
            "Select District",
            ["N/A - District data not available in source"],
            disabled=True,
            help="District-level filtering will be enabled when 'District' data is provided in the Google Sheet."
        )
    # st.markdown("---") # Optional: Add a separator if more distinct visual separation is needed before AC selection

    # --- AC Selection ---
    # Note: selected_question is already defined above
    st.subheader("Filtered Analysis by Assembly Constituency") # Added a subheader for clarity

    ac_options = ["All"] + sorted(df_survey_original["AC Name"].unique().tolist()) if "AC Name" in df_survey_original.columns else ["All"]
    # AC selector is not in columns anymore, as selected_question was moved up.
    selected_acs = st.multiselect(
        "Select Assembly Constituency (select 'All' for overall, or multiple individual ACs)",
        options=ac_options,
        default=["All"],
        key="ac_multiselect"
    )
    
    # st.markdown("---") # Removed this extra separator, one above is enough

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

    # --- Display Header for AC-Specific Analysis ---
    if selected_question: # selected_question is already guaranteed to be defined here
        # The overall question is displayed in the state summary,
        # here we just need to specify the AC context.
        st.markdown(f"#### Constituency Filter: {ac_header_display}")
        # st.markdown("---") # Removed this separator, as tables will follow directly
    # No need for an else here to stop, as selected_question is handled earlier.

    # Note: response_columns_ordered is already defined globally using df_survey_original.
    # It will be used for consistency in tables below.

    # --- Pre-calculate Grand Total row data (based on current_df and selected_question) ---
    # This grand_total_row_data is for the *potentially filtered* current_df (AC specific)
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