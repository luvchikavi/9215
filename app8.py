import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime, timezone # Added timezone
import pandas as pd
# import plotly.express as px # Not used in the provided snippet, can be removed if not needed later
# import io # Not used

# ==================== CONSTANTS ====================
DB_FILENAME = "tank_battalion.db"
DB_PATH = Path(DB_FILENAME)

TABLE_VEHICLES = "vehicles"
TABLE_VEHICLES_HISTORY = "vehicles_history"
TABLE_AMMO = "ammo"
TABLE_AMMO_HISTORY = "ammo_history"
TABLE_REQUIREMENTS = "requirements"
TABLE_REQUIREMENTS_HISTORY = "requirements_history"

COL_SIMON = "simon"
COL_VEHICLE_ID = "vehicle_id"
COL_PLUGA = "pluga"
COL_LOCATION = "location"
COL_Z = "z" # For requirements

STATUS_OPTIONS = ["Working", "Not Working"]
APP_TITLE = "9215 Dashboard"
FOOTER_TEXT_MAIN = "**9215 Summary Dashboard | Developed by Dr. Avi Luvchik**"
FOOTER_TEXT_CAPTION = "© 2025 Drishtiy LTD. All Rights Reserved."
APP_ICON_PATH = "9215.png"


# ==================== DB & INITIAL SETUP ====================

@st.cache_resource # Cache the connection resource
def init_connection(db_path):
    """Initializes and returns a SQLite database connection."""
    return sqlite3.connect(db_path, check_same_thread=False)

conn = init_connection(DB_PATH)

def ensure_all_tables(cnx):
    """Ensures all necessary tables exist in the database."""
    with cnx: # Use context manager for commits
        # Create vehicles_history if not exists, based on vehicles schema + ts
        # This assumes 'vehicles' table is created elsewhere or manually.
        # If 'vehicles' might not exist, you'd need to define its schema explicitly here.
        # For robustness, let's define an example schema if 'vehicles' might be missing
        # For a real scenario, ensure 'vehicles' and 'ammo' tables are pre-populated or created.
        cnx.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_VEHICLES} (
            simon TEXT PRIMARY KEY,
            pluga TEXT,
            location TEXT,
            status TEXT,
            other_details TEXT
        );
        """)
        cnx.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_AMMO} (
            vehicle_id TEXT PRIMARY KEY,
            hetz INTEGER,
            barzel INTEGER,
            regular_556 INTEGER,
            mag INTEGER,
            nafetiz60 INTEGER,
            teura60 INTEGER,
            meducut INTEGER,
            calanit INTEGER,
            halul INTEGER,
            hatzav INTEGER
            -- Add other ammo types as needed
        );
        """)

        # History tables
        # Get columns from main tables to create history tables dynamically (safer if main table changes)
        # Vehicles History
        cursor = cnx.execute(f"PRAGMA table_info({TABLE_VEHICLES})")
        vehicle_cols_defs = ", ".join([f"{row[1]} {row[2]}" for row in cursor.fetchall()])
        if vehicle_cols_defs: # Only if main table exists and has columns
            cnx.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_VEHICLES_HISTORY} ({vehicle_cols_defs}, ts TEXT);
            """)
        else: # Fallback if vehicles table is empty or doesn't exist (shouldn't happen if above CREATE works)
             cnx.execute(f"""
             CREATE TABLE IF NOT EXISTS {TABLE_VEHICLES_HISTORY} (
                simon TEXT, pluga TEXT, location TEXT, status TEXT, other_details TEXT, ts TEXT
            );
            """)


        # Ammo History
        cursor = cnx.execute(f"PRAGMA table_info({TABLE_AMMO})")
        ammo_cols_defs = ", ".join([f"{row[1]} {row[2]}" for row in cursor.fetchall()])
        if ammo_cols_defs:
            cnx.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_AMMO_HISTORY} ({ammo_cols_defs}, ts TEXT);
            """)
        else: # Fallback
            cnx.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_AMMO_HISTORY} (
                vehicle_id TEXT, hetz INTEGER, barzel INTEGER, regular_556 INTEGER, mag INTEGER,
                nafetiz60 INTEGER, teura60 INTEGER, meducut INTEGER,
                calanit INTEGER, halul INTEGER, hatzav INTEGER, ts TEXT
            );
            """)

        # Requirements tables
        cnx.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_REQUIREMENTS} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {COL_PLUGA} TEXT,
            {COL_Z} TEXT,
            commander_note TEXT,
            last_updated TEXT,
            UNIQUE({COL_PLUGA}, {COL_Z}) -- Ensure one note per Pluga/Z
        )
        """)
        cnx.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_REQUIREMENTS_HISTORY} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {COL_PLUGA} TEXT,
            {COL_Z} TEXT,
            commander_note TEXT,
            update_type TEXT,
            updated_at TEXT,
            ts TEXT
        )
        """)
    # cnx.commit() # commit is handled by 'with cnx:'

ensure_all_tables(conn)

def clean_id_column(series):
    """Cleans a pandas Series intended to be string IDs, handling potential floats."""
    def _clean_val(x):
        if pd.isna(x) or str(x).strip() == "":
            return ""
        try:
            return str(int(float(str(x)))) # Convert to float then int to handle "123.0"
        except ValueError:
            return str(x).strip() # Return original (stripped) if not a number
    return series.apply(_clean_val)

@st.cache_data # Add underscore to connection parameter to indicate it's managed by Streamlit's caching
def load_data(_cnx):
    """Loads data from the database into pandas DataFrames."""
    df_veh = pd.read_sql(f"SELECT * FROM {TABLE_VEHICLES}", _cnx).fillna("")
    df_ammo = pd.read_sql(f"SELECT * FROM {TABLE_AMMO}", _cnx).fillna("")
    df_req = pd.read_sql(f"SELECT * FROM {TABLE_REQUIREMENTS}", _cnx).fillna("")

    if COL_SIMON in df_veh.columns:
        df_veh[COL_SIMON] = clean_id_column(df_veh[COL_SIMON])
    if COL_VEHICLE_ID in df_ammo.columns:
        df_ammo[COL_VEHICLE_ID] = clean_id_column(df_ammo[COL_VEHICLE_ID])
    if COL_Z in df_req.columns: # Assuming 'z' in requirements might also be an ID-like field
        df_req[COL_Z] = clean_id_column(df_req[COL_Z])

    return df_veh, df_ammo, df_req

veh_df, ammo_df, req_df = load_data(conn)

def save_with_history(df, table_name, history_table_name, cnx):
    """Saves a DataFrame to a table and appends a copy with a timestamp to a history table."""
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    df_copy = df.copy()
    df_copy["ts"] = ts
    try:
        with cnx: # Use context manager for atomic operations
            df.to_sql(table_name, cnx, if_exists="replace", index=False)
            df_copy.to_sql(history_table_name, cnx, if_exists="append", index=False)
        return True, "Data saved successfully and logged in history."
    except sqlite3.Error as e:
        return False, f"Database error during save: {e}"

def add_footer():
    """Adds a common footer to the page."""
    st.markdown("---")
    st.write(FOOTER_TEXT_MAIN)
    st.caption(FOOTER_TEXT_CAPTION)

# ==================== APP LAYOUT ====================
st.set_page_config(APP_TITLE, layout="wide", initial_sidebar_state="auto")
try:
    st.image(APP_ICON_PATH, width=150)
except Exception:
    st.warning(f"Could not load app icon from: {APP_ICON_PATH}") # Non-critical error
st.title(APP_TITLE)

tab_names = ["Vehicles", "Ammunition", "Summary", "Decisions Tool", "History", "Requirements"]
tabs = st.tabs(tab_names)
tab_vehicles, tab_ammo, tab_summary, tab_decisions, tab_history, tab_req = tabs

# ==================== TAB 1: VEHICLES (EDITABLE) ====================
with tab_vehicles:
    st.header("Vehicles (Editable)")
    edited_veh = st.data_editor(
        veh_df,
        column_config={
            "status": st.column_config.SelectboxColumn(
                "Status", options=STATUS_OPTIONS, required=True
            )
        },
        use_container_width=True,
        num_rows="dynamic",
        key="veh_data_editor" # Unique key
    )
    if st.button("💾 Save Vehicle Changes", key="save_vehicle_button"): # Unique key
        success, message = save_with_history(edited_veh, TABLE_VEHICLES, TABLE_VEHICLES_HISTORY, conn)
        if success:
            st.success(message)
            st.cache_data.clear() # Clear cache to reload fresh data
            st.rerun() # Rerun to reflect changes and stay on tab
        else:
            st.error(message)
    add_footer()

# ==================== TAB 2: AMMUNITION (EDITABLE) ====================
with tab_ammo:
    st.header("Ammunition (Editable)")
    edited_ammo = st.data_editor(
        ammo_df,
        use_container_width=True,
        num_rows="dynamic",
        key="ammo_data_editor" # Unique key
    )
    if st.button("💾 Save Ammo Changes", key="save_ammo_button"): # Unique key
        success, message = save_with_history(edited_ammo, TABLE_AMMO, TABLE_AMMO_HISTORY, conn)
        if success:
            st.success(message)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(message)
    add_footer()

# ==================== TAB 3: SUMMARY ====================
with tab_summary:
    st.header("Ammunition & Vehicle Overview")
    # Define standards (these could be configurable or loaded from DB in a more complex app)
    standards = {
        "hetz": 3, "barzel": 10, "regular_556": 990, "mag": 30,
        "nafetiz60": 21, "teura60": 9, "meducut": 12
    }
    triple_ammo_types = ("calanit", "halul", "hatzav")
    triple_ammo_standard = 27 # Combined standard for the triple types

    st.subheader("Filter for Ammunition Shortage Table")
    col1, col2, col3, col4 = st.columns(4)

    # Ensure veh_df is not empty before trying to get unique values
    all_plugas = ["All"] + sorted(list(set(str(x) for x in veh_df[COL_PLUGA] if pd.notna(x) and str(x).strip() != ""))) if not veh_df.empty else ["All"]
    all_locs = ["All"] + sorted(list(set(str(x) for x in veh_df[COL_LOCATION] if pd.notna(x) and str(x).strip() != ""))) if not veh_df.empty else ["All"]
    all_z_vehicles = ["All"] + sorted(list(set(str(x) for x in veh_df[COL_SIMON] if pd.notna(x) and str(x).strip() != ""))) if not veh_df.empty else ["All"]

    all_ammo_types_filter = ["All"] + list(standards.keys()) + ["Calanit+Halul+Hatzav"]

    selected_pluga = col1.selectbox("Pluga", all_plugas, key="summary_pluga_filter")
    selected_loc = col2.selectbox("Location", all_locs, key="summary_loc_filter")
    selected_z_vehicle = col3.selectbox("Tank (Z)", all_z_vehicles, key="summary_z_filter")
    selected_ammo_type_filter = col4.selectbox("Ammo Type", all_ammo_types_filter, key="summary_ammo_type_filter")

    # Filter vehicles based on selections
    veh_view_summary = veh_df.copy()
    if selected_pluga != "All":
        veh_view_summary = veh_view_summary[veh_view_summary[COL_PLUGA] == selected_pluga]
    if selected_loc != "All":
        veh_view_summary = veh_view_summary[veh_view_summary[COL_LOCATION] == selected_loc]
    if selected_z_vehicle != "All":
        veh_view_summary = veh_view_summary[veh_view_summary[COL_SIMON] == selected_z_vehicle]

    tank_ids_for_ammo_view = veh_view_summary[COL_SIMON].tolist()
    ammo_view_summary = ammo_df[ammo_df[COL_VEHICLE_ID].isin(tank_ids_for_ammo_view)].copy()

    # Determine which ammo types to display columns for
    ammo_types_to_show_cols = []
    if selected_ammo_type_filter == "All":
        ammo_types_to_show_cols.extend(standards.keys())
        ammo_types_to_show_cols.extend(triple_ammo_types)
        ammo_types_to_show_cols.append("Calanit+Halul+Hatzav") # Combined display column
    elif selected_ammo_type_filter == "Calanit+Halul+Hatzav":
        ammo_types_to_show_cols.extend(triple_ammo_types)
        ammo_types_to_show_cols.append("Calanit+Halul+Hatzav")
    elif selected_ammo_type_filter: # Specific type selected
        ammo_types_to_show_cols.append(selected_ammo_type_filter)

    shortage_display_rows = []
    shortage_numeric_values = [] # For styling

    base_cols_display = ["Pluga", "Location", "Z"]

    if not ammo_view_summary.empty:
        for _, ammo_row in ammo_view_summary.iterrows():
            vehicle_id = ammo_row[COL_VEHICLE_ID]
            vehicle_match = veh_df[veh_df[COL_SIMON] == vehicle_id]

            # Get Pluga and Location from vehicle_match if available
            row_pluga = vehicle_match.iloc[0][COL_PLUGA] if not vehicle_match.empty else "N/A"
            row_loc = vehicle_match.iloc[0][COL_LOCATION] if not vehicle_match.empty else "N/A"

            display_data_for_row = {"Pluga": row_pluga, "Location": row_loc, "Z": vehicle_id}
            numeric_shortage_for_row = {"Pluga": row_pluga, "Location": row_loc, "Z": vehicle_id}

            # Standard ammo types
            for ammo_col, std_val in standards.items():
                current_ammo_val = float(ammo_row.get(ammo_col, 0)) if str(ammo_row.get(ammo_col, "")).strip() != "" else 0
                shortage = max(std_val - current_ammo_val, 0)
                display_data_for_row[ammo_col] = f"{int(current_ammo_val)}({int(shortage)})" if shortage > 0 else f"{int(current_ammo_val)}"
                numeric_shortage_for_row[ammo_col] = shortage

            # Triple ammo types (Calanit, Halul, Hatzav)
            current_triple_total = 0
            individual_triple_values = {}
            for t_type in triple_ammo_types:
                val = float(ammo_row.get(t_type, 0)) if str(ammo_row.get(t_type, "")).strip() != "" else 0
                current_triple_total += val
                individual_triple_values[t_type] = val

            triple_shortage = max(triple_ammo_standard - current_triple_total, 0)
            for t_type in triple_ammo_types: # Display individual triple types
                display_data_for_row[t_type] = f"{int(individual_triple_values[t_type])}({int(triple_shortage)})" if triple_shortage > 0 else f"{int(individual_triple_values[t_type])}"
                numeric_shortage_for_row[t_type] = triple_shortage # Shortage is for the group

            # Combined display for triple types
            combined_triple_display_name = "Calanit+Halul+Hatzav"
            display_data_for_row[combined_triple_display_name] = f"{int(current_triple_total)}({int(triple_shortage)})" if triple_shortage > 0 else f"{int(current_triple_total)}"
            numeric_shortage_for_row[combined_triple_display_name] = triple_shortage

            shortage_display_rows.append(display_data_for_row)
            shortage_numeric_values.append(numeric_shortage_for_row)

    if not shortage_display_rows:
        shortage_display_df = pd.DataFrame(columns=base_cols_display + [col for col in ammo_types_to_show_cols if col in standards or col in triple_ammo_types or col == "Calanit+Halul+Hatzav"])
        shortage_numeric_df_for_style = pd.DataFrame(columns=shortage_display_df.columns)
    else:
        shortage_display_df = pd.DataFrame(shortage_display_rows)
        shortage_numeric_df_for_style = pd.DataFrame(shortage_numeric_values)

    # Filter columns to display based on selection and availability
    final_display_cols = base_cols_display + [col for col in ammo_types_to_show_cols if col in shortage_display_df.columns]
    final_display_cols = sorted(list(set(final_display_cols)), key=lambda x: (x not in base_cols_display, x)) # Keep base cols first

    shortage_display_df = shortage_display_df[final_display_cols] if not shortage_display_df.empty and final_display_cols else pd.DataFrame(columns=base_cols_display)


    if not shortage_display_df.empty:
        st.markdown(
            "<span style='display:inline-block; width:18px; height:18px; background:#d4f8d4;"
            "border:1px solid #999;'></span> **Meets standard** &nbsp;&nbsp;"
            "<span style='display:inline-block; width:18px; height:18px; background:#ffb3b3;"
            "border:1px solid #999;'></span> **Below standard**",
            unsafe_allow_html=True
        )

        def highlight_shortage_style(data_df_to_style):
            style_df = pd.DataFrame('', index=data_df_to_style.index, columns=data_df_to_style.columns)
            if shortage_numeric_df_for_style.empty or data_df_to_style.empty: # or not same index
                 return style_df
            # Ensure indices match if they are not already (can happen if filtering changes things)
            # This part might need adjustment if data_df_to_style has a different index than shortage_numeric_df_for_style
            # For simplicity, assuming they align based on prior logic.

            for col_name in data_df_to_style.columns:
                if col_name not in base_cols_display and col_name in shortage_numeric_df_for_style.columns:
                    for idx in data_df_to_style.index:
                        if idx in shortage_numeric_df_for_style.index: # Check if index exists in numeric df
                            short_val = shortage_numeric_df_for_style.loc[idx, col_name]
                            try:
                                if float(short_val) > 0:
                                    style_df.loc[idx, col_name] = 'background-color: #ffb3b3' # Light Red
                                else:
                                    style_df.loc[idx, col_name] = 'background-color: #d4f8d4' # Light Green
                            except (ValueError, TypeError):
                                pass # Non-numeric shortage value, no style
            return style_df

        styled_shortage_df = shortage_display_df.style.apply(highlight_shortage_style, axis=None)
        st.dataframe(styled_shortage_df, use_container_width=True)
    else:
        st.info("No ammunition data to display based on current filters, or all vehicles meet standards for selected ammo.")

    add_footer()

# ==================== TAB 4: DECISIONS TOOL ====================
with tab_decisions:
    st.header("Decisions Tool - Concept")
    st.info("This section is planned for future development. It could include features like:"
            "\n- Simulating ammo redistribution."
            "\n- Prioritizing vehicle repairs based on mission needs."
            "\n- Scenario planning for different operational requirements.")
    # Add any interactive elements with unique keys if developed
    add_footer()

# ==================== TAB 5: HISTORY ====================
with tab_history:
    st.header("History: View Past Snapshots")

    # Fetch distinct timestamps from all relevant history tables
    ts_veh_hist = pd.read_sql(f"SELECT DISTINCT ts FROM {TABLE_VEHICLES_HISTORY} ORDER BY ts DESC", conn)["ts"].tolist()
    ts_ammo_hist = pd.read_sql(f"SELECT DISTINCT ts FROM {TABLE_AMMO_HISTORY} ORDER BY ts DESC", conn)["ts"].tolist()
    ts_req_hist_main = pd.read_sql(f"SELECT DISTINCT ts FROM {TABLE_REQUIREMENTS_HISTORY} ORDER BY ts DESC", conn)["ts"].tolist()

    # Combine and sort all unique timestamps
    all_hist_ts = sorted(list(set(ts_veh_hist) | set(ts_ammo_hist) | set(ts_req_hist_main)), reverse=True)

    if not all_hist_ts:
        st.info("No history data found. Please save data in other tabs to populate history.")
    else:
        chosen_ts = st.selectbox("Select Snapshot Time (UTC)", all_hist_ts, key="history_ts_selector")

        if chosen_ts:
            st.subheader(f"Snapshot at: {chosen_ts} UTC")

            # Vehicles Snapshot
            if chosen_ts in ts_veh_hist:
                df_veh_hist_snap = pd.read_sql(f"SELECT * FROM {TABLE_VEHICLES_HISTORY} WHERE ts=?", conn, params=(chosen_ts,))
                if "ts" in df_veh_hist_snap.columns: df_veh_hist_snap.drop(columns="ts", inplace=True)
                if COL_SIMON in df_veh_hist_snap.columns:
                    df_veh_hist_snap[COL_SIMON] = clean_id_column(df_veh_hist_snap[COL_SIMON])
                st.markdown("#### Vehicles Snapshot")
                st.dataframe(df_veh_hist_snap.style.format(precision=0), use_container_width=True)
            else:
                st.markdown("#### Vehicles Snapshot")
                st.caption(f"No vehicle data saved at {chosen_ts} UTC.")


            # Ammo Snapshot
            if chosen_ts in ts_ammo_hist:
                df_ammo_hist_snap = pd.read_sql(f"SELECT * FROM {TABLE_AMMO_HISTORY} WHERE ts=?", conn, params=(chosen_ts,))
                if "ts" in df_ammo_hist_snap.columns: df_ammo_hist_snap.drop(columns="ts", inplace=True)
                if COL_VEHICLE_ID in df_ammo_hist_snap.columns:
                     df_ammo_hist_snap[COL_VEHICLE_ID] = clean_id_column(df_ammo_hist_snap[COL_VEHICLE_ID])
                st.markdown("#### Ammunition Snapshot")
                st.dataframe(df_ammo_hist_snap.style.format(precision=0), use_container_width=True)
            else:
                st.markdown("#### Ammunition Snapshot")
                st.caption(f"No ammunition data saved at {chosen_ts} UTC.")


    # Full Requirements History (not tied to specific snapshot time necessarily, shows all changes)
    st.markdown("---")
    st.subheader("All Requirements Changes History")
    full_req_history_df = pd.read_sql(f"SELECT * FROM {TABLE_REQUIREMENTS_HISTORY} ORDER BY ts DESC, id DESC", conn)
    if full_req_history_df.empty:
        st.caption("No requirements changes have been logged.")
    else:
        st.dataframe(full_req_history_df, use_container_width=True)

    add_footer()

# ==================== TAB 6: REQUIREMENTS ====================
with tab_req:
    st.header("Commander Requirements & Notes")

    # Display current requirements with filters
    # Ensure req_df is not empty before filtering
    pluga_unique_req = ["All"] + sorted(req_df[COL_PLUGA].dropna().unique().tolist()) if not req_df.empty else ["All"]
    z_unique_req = ["All"] + sorted(req_df[COL_Z].dropna().unique().tolist()) if not req_df.empty else ["All"]

    filter_col1, filter_col2 = st.columns(2)
    selected_pluga_req_filter = filter_col1.selectbox(
        f"Filter by {COL_PLUGA}", pluga_unique_req, key="req_pluga_filter"
    )
    selected_z_req_filter = filter_col2.selectbox(
        f"Filter by {COL_Z}", z_unique_req, key="req_z_filter"
    )

    display_req_df = req_df.copy()
    if selected_pluga_req_filter != "All":
        display_req_df = display_req_df[display_req_df[COL_PLUGA] == selected_pluga_req_filter]
    if selected_z_req_filter != "All":
        display_req_df = display_req_df[display_req_df[COL_Z] == selected_z_req_filter]
    st.dataframe(display_req_df, use_container_width=True)

    st.markdown("---")
    st.subheader("Add/Edit Note")

    # Ensure veh_df is not empty for selectbox options
    pluga_options_notes = sorted(veh_df[COL_PLUGA].dropna().unique().tolist()) if not veh_df.empty else []
    z_options_notes = sorted(veh_df[COL_SIMON].dropna().unique().tolist()) if not veh_df.empty else []

    if not pluga_options_notes or not z_options_notes:
        st.warning("Please add vehicle data first to define Pluga and Z options for notes.")
    else:
        selected_pluga_for_note = st.selectbox(
            f"{COL_PLUGA} (for note)", pluga_options_notes, key="req_pluga_select_note"
        )
        selected_z_for_note = st.selectbox(
            f"{COL_Z} (Tank for note)", z_options_notes, key="req_z_select_note"
        )

        current_note_text = ""
        # Pre-fill note if it exists for the selected Pluga/Z combination
        if selected_pluga_for_note and selected_z_for_note and not req_df.empty:
            match_df = req_df[
                (req_df[COL_PLUGA] == selected_pluga_for_note) &
                (req_df[COL_Z] == selected_z_for_note)
            ]
            if not match_df.empty:
                current_note_text = match_df.iloc[0]['commander_note']

        note_text_input = st.text_area(
            "Commander Note", value=current_note_text, key="req_note_text_area"
        )

        if st.button("Save Note", key="req_save_note_button"):
            if not selected_pluga_for_note or not selected_z_for_note:
                st.error("Pluga and Z must be selected to save a note.")
            else:
                now_utc_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                try:
                    with conn: # Use context manager for atomic operations
                        cursor = conn.execute(
                            f"SELECT id FROM {TABLE_REQUIREMENTS} WHERE {COL_PLUGA}=? AND {COL_Z}=?",
                            (selected_pluga_for_note, selected_z_for_note)
                        )
                        existing_note = cursor.fetchone()
                        history_update_type = ""

                        if existing_note:
                            conn.execute(
                                f"""UPDATE {TABLE_REQUIREMENTS}
                                    SET commander_note = ?, last_updated = ?
                                    WHERE {COL_PLUGA} = ? AND {COL_Z} = ?""",
                                (note_text_input, now_utc_str, selected_pluga_for_note, selected_z_for_note)
                            )
                            history_update_type = "Requirement Updated"
                        else:
                            conn.execute(
                                f"""INSERT INTO {TABLE_REQUIREMENTS} ({COL_PLUGA}, {COL_Z}, commander_note, last_updated)
                                    VALUES (?, ?, ?, ?)""",
                                (selected_pluga_for_note, selected_z_for_note, note_text_input, now_utc_str)
                            )
                            history_update_type = "Requirement Added"

                        conn.execute(
                            f"""INSERT INTO {TABLE_REQUIREMENTS_HISTORY}
                                ({COL_PLUGA}, {COL_Z}, commander_note, update_type, updated_at, ts)
                                VALUES (?, ?, ?, ?, ?, ?)""",
                            (selected_pluga_for_note, selected_z_for_note, note_text_input,
                             history_update_type, now_utc_str, now_utc_str)
                        )
                    st.success("Note saved successfully!")
                    st.cache_data.clear() # Clear cache to reload requirements
                    st.rerun() # Rerun to reflect changes
                except sqlite3.Error as e:
                    st.error(f"Database error: {e}")
    add_footer()
