import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime, timezone # Added timezone
import pandas as pd
import plotly.express as px # Your version uses this
import plotly.graph_objects as go
import io

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
COL_Z = "z" # For requirements' Z (tank ID)
COL_VEHICLE_TYPE = "vehicle_type" # From your summary tab
COL_STATUS = "status"
COL_COMMANDER_NOTE = "commander_note"
COL_LAST_UPDATED = "last_updated"

# Ammo types from your summary
STANDARDS_AMMO = {
    "hetz": 3, "barzel": 10, "regular_556": 990, "mag": 30,
    "nafetiz60": 21, "teura60": 9, "meducut": 12
}
TRIPLE_AMMO_TYPES = ("calanit", "halul", "hatzav")
TRIPLE_AMMO_STANDARD = 27

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
        # Ensure main tables 'vehicles' and 'ammo' exist with a basic schema if not already present
        # Your original code for history tables relied on these existing.
        # Add more columns as per your actual main table structure.
        cnx.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_VEHICLES} (
            {COL_SIMON} TEXT PRIMARY KEY,
            {COL_PLUGA} TEXT,
            {COL_LOCATION} TEXT,
            {COL_STATUS} TEXT,
            {COL_VEHICLE_TYPE} TEXT,
            category TEXT, -- From your decisions tab
            other_details TEXT
        );
        """)
        cnx.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_AMMO} (
            {COL_VEHICLE_ID} TEXT PRIMARY KEY,
            hetz REAL, barzel REAL, regular_556 REAL, mag REAL,
            nafetiz60 REAL, teura60 REAL, meducut REAL,
            calanit REAL, halul REAL, hatzav REAL
            -- Add other ammo types as needed, ensure types are REAL or INTEGER
        );
        """)

        # History tables - using your original method which is fine if main tables are guaranteed to exist
        # For more robustness if main tables might change schema often, PRAGMA method is better
        cnx.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_VEHICLES_HISTORY} AS
        SELECT *, '' as ts FROM {TABLE_VEHICLES} WHERE 0;
        """)
        cnx.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_AMMO_HISTORY} AS
        SELECT *, '' as ts FROM {TABLE_AMMO} WHERE 0;
        """)

        # Requirements tables
        cnx.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_REQUIREMENTS} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {COL_PLUGA} TEXT,
            {COL_Z} TEXT, -- This will store the vehicle's 'simon' ID
            {COL_COMMANDER_NOTE} TEXT,
            {COL_LAST_UPDATED} TEXT,
            UNIQUE({COL_PLUGA}, {COL_Z})
        )
        """)
        cnx.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_REQUIREMENTS_HISTORY} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {COL_PLUGA} TEXT,
            {COL_Z} TEXT,
            {COL_COMMANDER_NOTE} TEXT,
            update_type TEXT,
            updated_at TEXT,
            ts TEXT
        )
        """)
ensure_all_tables(conn)

def clean_id_column(series):
    """Cleans a pandas Series intended to be string IDs, handling potential floats."""
    def _clean_val(x):
        if pd.isna(x) or str(x).strip() == "":
            return ""
        # Try to convert to float then int to handle "123.0", then to string
        # If it's already a string that looks like an int, int(str(x)) works.
        # If it's a string that is a float "123.0", int(float(str(x))) works.
        # If it's "ABC" or "1.2.3", it should fail and return original.
        try:
            return str(int(float(str(x))))
        except ValueError:
            return str(x).strip()
    return series.apply(_clean_val)

@st.cache_data
def load_data(_cnx): # Pass connection
    """Load from tables, remove NaNs, cast ID columns to strings."""
    df_veh = pd.read_sql(f"SELECT * FROM {TABLE_VEHICLES}", _cnx).fillna("")
    df_ammo = pd.read_sql(f"SELECT * FROM {TABLE_AMMO}", _cnx).fillna("")
    df_req = pd.read_sql(f"SELECT * FROM {TABLE_REQUIREMENTS}", _cnx).fillna("")


    if COL_SIMON in df_veh.columns:
        df_veh[COL_SIMON] = clean_id_column(df_veh[COL_SIMON])
    if COL_VEHICLE_ID in df_ammo.columns:
        df_ammo[COL_VEHICLE_ID] = clean_id_column(df_ammo[COL_VEHICLE_ID])
    # Clean 'Z' in requirements table if it's meant to be like an ID
    if COL_Z in df_req.columns:
        df_req[COL_Z] = clean_id_column(df_req[COL_Z])


    # Ensure all expected ammo columns exist in df_ammo, fill with 0 if not
    all_expected_ammo_cols = list(STANDARDS_AMMO.keys()) + list(TRIPLE_AMMO_TYPES)
    for col in all_expected_ammo_cols:
        if col not in df_ammo.columns:
            df_ammo[col] = 0.0 # Default to float
        else:
            # Convert ammo columns to numeric, coercing errors to NaN, then fill NaN with 0
            df_ammo[col] = pd.to_numeric(df_ammo[col], errors='coerce').fillna(0.0)


    return df_veh, df_ammo, df_req

veh_df, ammo_df, req_df = load_data(conn)


def save_with_history(df, table_name, history_table_name, cnx):
    """Saves DataFrame to table and appends timestamped snapshot to history."""
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S') # Use timezone-aware UTC
    df_copy = df.copy()
    df_copy["ts"] = ts

    try:
        with cnx: # Use context manager for atomic operations
            df.to_sql(table_name, cnx, if_exists="replace", index=False)
            df_copy.to_sql(history_table_name, cnx, if_exists="append", index=False)
        return True, "Data saved successfully and logged in history."
    except sqlite3.Error as e:
        st.error(f"Database error during save: {e}")
        return False, f"Database error during save: {e}"

# ==================== FOOTER ====================
def add_footer():
    st.markdown("---")
    st.write(FOOTER_TEXT_MAIN)
    st.caption(FOOTER_TEXT_CAPTION)

# ==================== STREAMLIT CONFIG & LAYOUT ====================
st.set_page_config(APP_TITLE, layout="wide", initial_sidebar_state="auto")

try:
    st.image(APP_ICON_PATH, width=150)
except Exception:
    st.warning(f"Could not load app icon from: {APP_ICON_PATH}")
st.title(APP_TITLE)

# Added "Requirements" tab
tab_names = ["Vehicles", "Ammunition", "Summary", "Decisions Tool", "History", "Requirements"]
tabs = st.tabs(tab_names)
tab_vehicles, tab_ammo, tab_summary, tab_decisions, tab_history, tab_req = tabs


# ==================== TAB 1: VEHICLES (EDITABLE) ====================
with tab_vehicles:
    st.header("Vehicles (Editable)")
    # Define column_config for specific columns if needed, e.g., status
    column_config_veh = {
        COL_STATUS: st.column_config.SelectboxColumn(
            "Status", options=["Working", "Not Working", "In Repair", "Unknown"], required=False # Make options configurable
        )
    }
    edited_veh = st.data_editor(
        veh_df,
        column_config=column_config_veh,
        use_container_width=True,
        num_rows="dynamic",
        key="veh_data_editor" # Unique key
    )

    if st.button("💾 Save Vehicle Changes", key="save_vehicle_button"): # Unique key
        success, message = save_with_history(edited_veh, TABLE_VEHICLES, TABLE_VEHICLES_HISTORY, conn)
        if success:
            st.success(message)
            st.cache_data.clear() # Clear cache to reload fresh data
            st.rerun() # Rerun to reflect changes
        else:
            st.error(message)
    add_footer()

# ==================== TAB 2: AMMUNITION (EDITABLE) ====================
with tab_ammo:
    st.header("Ammunition (Editable)")
    # For ammo, ensure numeric inputs. data_editor usually handles this if df dtypes are numeric.
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

# ==================== TAB 3: SUMMARY (Based on your stable version) ====================
with tab_summary:
    st.header("Ammunition & 9215 Overview")

    if not req_df.empty:
        with st.expander("Commander Requirements", expanded=False):
            req_preview = req_df[[COL_PLUGA, COL_Z, COL_COMMANDER_NOTE]].head(5)
            st.dataframe(req_preview, use_container_width=True)

    # Using constants for ammo standards
    # standards = STANDARDS_AMMO (already defined as constant)
    # triple = TRIPLE_AMMO_TYPES (already defined as constant)
    # triple_std = TRIPLE_AMMO_STANDARD (already defined as constant)

    st.subheader("Filter for Ammunition Shortage Table")
    c1, c2, c3, c4 = st.columns(4)

    # Robust unique value fetching for filters
    all_plugas = ["All"] + sorted(list(set(str(x) for x in veh_df[COL_PLUGA] if pd.notna(x) and str(x).strip() != ""))) if not veh_df.empty else ["All"]
    all_locs = ["All"] + sorted(list(set(str(x) for x in veh_df[COL_LOCATION] if pd.notna(x) and str(x).strip() != ""))) if not veh_df.empty else ["All"]
    all_z_vehicles = ["All"] + sorted(list(set(str(x) for x in veh_df[COL_SIMON] if pd.notna(x) and str(x).strip() != ""))) if not veh_df.empty else ["All"]
    all_types_filter = ["All"] + list(STANDARDS_AMMO.keys()) + ["Calanit+Halul+Hatzav"]


    pluga_sel = c1.selectbox("Pluga", all_plugas, key="summary_pluga_filter_ammo")
    loc_sel = c2.selectbox("Location", all_locs, key="summary_loc_filter_ammo")
    z_sel = c3.selectbox("Tank (Z)", all_z_vehicles, key="summary_z_filter_ammo")
    type_sel = c4.selectbox("Ammo Type", all_types_filter, key="summary_type_filter_ammo")


    veh_view = veh_df.copy()
    if pluga_sel != "All":
        veh_view = veh_view[veh_view[COL_PLUGA] == pluga_sel]
    if loc_sel != "All":
        veh_view = veh_view[veh_view[COL_LOCATION] == loc_sel]
    if z_sel != "All":
        veh_view = veh_view[veh_view[COL_SIMON] == z_sel]

    tank_ids = veh_view[COL_SIMON].tolist()
    # Ensure ammo_view is created even if tank_ids is empty
    ammo_view = ammo_df[ammo_df[COL_VEHICLE_ID].isin(tank_ids)].copy() if tank_ids else pd.DataFrame(columns=ammo_df.columns)


    if type_sel == "All":
        show_types = list(STANDARDS_AMMO.keys()) + list(TRIPLE_AMMO_TYPES)
    elif type_sel == "Calanit+Halul+Hatzav":
        show_types = list(TRIPLE_AMMO_TYPES)
    else:
        show_types = [type_sel] if type_sel and type_sel in all_types_filter else []

    fleet_tab, ammo_tab = st.tabs(["Fleet Status", "Ammo Status"])

    with ammo_tab:
        st.subheader("Ammunition Shortage Table")
        shortage_rows = []
        shortage_numeric_rows = []
    
        if not ammo_view.empty:
            for _, row in ammo_view.iterrows():
                sid = str(row[COL_VEHICLE_ID]) # Ensure it's a string for matching
                vmatch = veh_df[veh_df[COL_SIMON] == sid] # Match string ID
    
                # Safer fetching of pluga/location
                row_pluga = vmatch.iloc[0][COL_PLUGA] if not vmatch.empty and COL_PLUGA in vmatch.columns else "N/A"
                row_loc = vmatch.iloc[0][COL_LOCATION] if not vmatch.empty and COL_LOCATION in vmatch.columns else "N/A"
    
                disp = {"Pluga": row_pluga, "Location": row_loc, "Z": sid}
                shrt = {"Pluga": row_pluga, "Location": row_loc, "Z": sid}
    
                for c_ammo, std_val in STANDARDS_AMMO.items():
                    have = float(row.get(c_ammo, 0.0)) # .get for safety, default to 0.0
                    short = max(std_val - have, 0.0)
                    disp[c_ammo] = f"{int(have)}({int(short)})" if short > 0 else f"{int(have)}"
                    shrt[c_ammo] = short
    
                triple_val = 0.0
                tvals = {}
                for t_ammo in TRIPLE_AMMO_TYPES:
                    cur = float(row.get(t_ammo, 0.0))
                    triple_val += cur
                    tvals[t_ammo] = cur
                triple_short = max(TRIPLE_AMMO_STANDARD - triple_val, 0.0)
    
                for t_ammo in TRIPLE_AMMO_TYPES:
                    disp[t_ammo] = f"{int(tvals[t_ammo])}({int(triple_short)})" if triple_short > 0 else f"{int(tvals[t_ammo])}"
                    shrt[t_ammo] = triple_short # Shortage applies to the group
    
                combined_triple_name = "Calanit+Halul+Hatzav"
                if combined_triple_name in (show_types + [combined_triple_name]):
                    disp[combined_triple_name] = f"{int(triple_val)}({int(triple_short)})" if triple_short > 0 else f"{int(triple_val)}"
                    shrt[combined_triple_name] = triple_short
    
                shortage_rows.append(disp)
                shortage_numeric_rows.append(shrt)
    
        base_cols_summary = ["Pluga", "Location", "Z"]
        if not shortage_rows:
            shortage_disp_df = pd.DataFrame(columns=base_cols_summary)
            shortage_num_df = pd.DataFrame(columns=base_cols_summary)
        else:
            shortage_disp_df = pd.DataFrame(shortage_rows)
            shortage_num_df = pd.DataFrame(shortage_numeric_rows)
    
    
        # Determine final columns to display more robustly
        final_disp_cols = base_cols_summary[:] # Start with a copy
        unique_show_types = sorted(list(set(col for col in show_types if col in shortage_disp_df.columns)))
        final_disp_cols.extend(unique_show_types)
        if "Calanit+Halul+Hatzav" in shortage_disp_df.columns and \
           ("Calanit+Halul+Hatzav" not in final_disp_cols) and \
           (type_sel == "All" or type_sel == "Calanit+Halul+Hatzav"):
            final_disp_cols.append("Calanit+Halul+Hatzav")
    
        # Ensure columns exist before trying to select them
        final_disp_cols = [col for col in final_disp_cols if col in shortage_disp_df.columns]
        if not final_disp_cols and not shortage_disp_df.empty: # If somehow all dynamic cols are gone, show base
            final_disp_cols = [col for col in base_cols_summary if col in shortage_disp_df.columns]
    
    
        shortage_disp_df = shortage_disp_df[final_disp_cols] if final_disp_cols and not shortage_disp_df.empty else pd.DataFrame(columns=base_cols_summary)
        # Ensure shortage_num_df has same columns as shortage_disp_df for styling
        shortage_num_df = shortage_num_df[final_disp_cols] if final_disp_cols and not shortage_num_df.empty else pd.DataFrame(columns=base_cols_summary)
    
    
        if not shortage_disp_df.empty:
            st.markdown(
                "<span style='display:inline-block; width:18px; height:18px; background:#d4f8d4;border:1px solid #999;'></span> **Meets standard** &nbsp;&nbsp;"
                "<span style='display:inline-block; width:18px; height:18px; background:#ffb3b3;border:1px solid #999;'></span> **Below standard**",
                unsafe_allow_html=True
            )
            def highlight_shortage_summary(data_df_to_style): # Renamed to avoid conflict
                style_df = pd.DataFrame('', index=data_df_to_style.index, columns=data_df_to_style.columns)
                if shortage_num_df.empty or data_df_to_style.empty:
                     return style_df
                for col_name in data_df_to_style.columns:
                    if col_name not in base_cols_summary and col_name in shortage_num_df.columns:
                        for idx in data_df_to_style.index:
                            if idx in shortage_num_df.index:
                                short_val = shortage_num_df.loc[idx, col_name]
                                try:
                                    if float(short_val) > 0:
                                        style_df.loc[idx, col_name] = 'background-color: #ffb3b3'
                                    else:
                                        style_df.loc[idx, col_name] = 'background-color: #d4f8d4'
                                except (ValueError, TypeError): pass
                return style_df
            sty = shortage_disp_df.style.apply(highlight_shortage_summary, axis=None)
            st.dataframe(sty, use_container_width=True)
        else:
            st.info("No shortage data to display for the current filters.")
    
        # ... (Rest of your Summary Tab: Quick shortage %, Totals vs Standards, Vehicles Condition, Download) ...
        # This part of your summary tab is quite extensive. I'll keep it as is from your stable version
        # and just ensure variable names and constants are aligned if needed.
    
        # ============ 4. Quick shortage percentage table ============
        st.markdown("---")
        st.subheader("Quick Overview of Shortage in % by Ammo Type")
    
        n_tanks_summary_view = len(veh_view) # Use veh_view which is filtered for this section
        if n_tanks_summary_view > 0 and not ammo_view.empty:
            summary_data = []
            for c_ammo, std_val in STANDARDS_AMMO.items():
                col_current = ammo_view[c_ammo].sum() # Already numeric due to load_data
                col_need = std_val * n_tanks_summary_view
                col_short = max(col_need - col_current, 0)
                short_percent = 0 if col_need == 0 else (col_short / col_need) * 100
                summary_data.append({
                    "Type": c_ammo, "Current": int(col_current), "Standard": int(col_need),
                    "Shortage": int(col_short), "Shortage%": f"{short_percent:.1f}%"
                })
    
            sum_triple_current = 0
            for t_ammo in TRIPLE_AMMO_TYPES:
                sum_triple_current += ammo_view[t_ammo].sum()
            need_triple = TRIPLE_AMMO_STANDARD * n_tanks_summary_view
            short_triple = max(need_triple - sum_triple_current, 0)
            shortp_triple = 0 if need_triple == 0 else (short_triple / need_triple) * 100
            summary_data.append({
                "Type": "Calanit+Halul+Hatzav", "Current": int(sum_triple_current),
                "Standard": int(need_triple), "Shortage": int(short_triple),
                "Shortage%": f"{shortp_triple:.1f}%"
            })
            short_summary_df = pd.DataFrame(summary_data)
            st.dataframe(short_summary_df.style.format(precision=0, formatter={"Shortage%": "{}"}), use_container_width=True)

            gauge_cols = st.columns(3)
            i = 0
            for ammo_type in STANDARDS_AMMO.keys():
                if ammo_type in ammo_view.columns:
                    current = ammo_view[ammo_type].sum()
                    need = STANDARDS_AMMO[ammo_type] * n_tanks_summary_view
                    pct = 0 if need == 0 else (current / need) * 100
                    fig = go.Figure(go.Indicator(mode="gauge+number", value=pct,
                                 gauge={"axis": {"range": [0, 100]}},
                                 title={"text": ammo_type}))
                    gauge_cols[i % 3].plotly_chart(fig, use_container_width=True)
                    i += 1
        else:
            st.info("No tanks or ammo data in the current filter to compute shortage %.")
    
        # ============ 5. 9215 Totals vs. Standards (bar chart) ============
        st.markdown("---")
        st.subheader("Overall Totals vs. Standards (Based on Filter)")
    
        if n_tanks_summary_view > 0 and not ammo_view.empty:
            cur_map = {}
            for c_ammo in STANDARDS_AMMO:
                cur_map[c_ammo] = ammo_view[c_ammo].sum()
            total_triple_current = sum(ammo_view[t_ammo].sum() for t_ammo in TRIPLE_AMMO_TYPES)
            cur_map["Calanit+Halul+Hatzav"] = total_triple_current
    
            std_map = {c_ammo: val * n_tanks_summary_view for c_ammo, val in STANDARDS_AMMO.items()}
            std_map["Calanit+Halul+Hatzav"] = TRIPLE_AMMO_STANDARD * n_tanks_summary_view
    
            chart_cur, chart_std = {}, {}
            for k_ammo in cur_map:
                if k_ammo == "regular_556":
                    new_k_ammo = "regular_556 (x1000)"
                    chart_cur[new_k_ammo] = cur_map[k_ammo] / 1000.0
                    chart_std[new_k_ammo] = std_map[k_ammo] / 1000.0
                else:
                    chart_cur[k_ammo] = cur_map[k_ammo]
                    chart_std[k_ammo] = std_map[k_ammo]
            chart_df = pd.DataFrame({
                "Ammo Type": list(chart_cur.keys()),
                "Current": list(chart_cur.values()),
                "Standard": [chart_std[x] for x in chart_cur.keys()] # Ensure order
            })
            fig_batt = px.bar(chart_df, x="Ammo Type", y=["Current", "Standard"], barmode="group", title="Totals: Current vs Standard (Based on Filter)")
            st.plotly_chart(fig_batt, use_container_width=True)
        else:
            st.info("No data to aggregate for bar chart (zero tanks or no ammo data match your filters).")

    # ============ 6. Vehicles Condition Table ============
    with fleet_tab:
        st.markdown("---")
        st.subheader("Vehicles Condition Table")
        
        # Robust unique value fetching for vehicle condition filters
        all_veh_types_filter = ["All"] + sorted(list(set(str(x) for x in veh_df[COL_VEHICLE_TYPE] if pd.notna(x) and str(x).strip() != ""))) if not veh_df.empty and COL_VEHICLE_TYPE in veh_df.columns else ["All"]
        
        col_loc_v, col_pluga_v, col_vtype_v = st.columns(3)
        loc_v_sel = col_loc_v.selectbox("Location (Vehicles)", all_locs, key="v_cond_loc_filter") # all_locs from ammo section is fine
        pluga_v_sel = col_pluga_v.selectbox("Pluga (Vehicles)", all_plugas, key="v_cond_pluga_filter") # all_plugas from ammo section
        vtype_v_sel = col_vtype_v.selectbox("Vehicle Type", all_veh_types_filter, key="v_cond_vtype_filter")
        
        vehicle_condition_view_df = veh_df.copy()
        if loc_v_sel != "All":
            vehicle_condition_view_df = vehicle_condition_view_df[vehicle_condition_view_df[COL_LOCATION] == loc_v_sel]
        if pluga_v_sel != "All":
            vehicle_condition_view_df = vehicle_condition_view_df[vehicle_condition_view_df[COL_PLUGA] == pluga_v_sel]
        if vtype_v_sel != "All" and COL_VEHICLE_TYPE in vehicle_condition_view_df.columns:
            vehicle_condition_view_df = vehicle_condition_view_df[vehicle_condition_view_df[COL_VEHICLE_TYPE] == vtype_v_sel]
        
        def highlight_vehicle_status_summary(row_series): # Renamed
            status_val = str(row_series.get(COL_STATUS, "")).strip().lower()
            if status_val == "working": return "background-color: #d4f8d4" # Light Green
            elif status_val == "not working": return "background-color: #ffb3b3" # Light Red
            return ""
        
        if not vehicle_condition_view_df.empty:
            sty_veh_cond = vehicle_condition_view_df.style.apply(
                lambda s_row: [highlight_vehicle_status_summary(s_row) if col_name == COL_STATUS else "" for col_name in s_row.index],
                axis=1
            )
            st.dataframe(sty_veh_cond.format(precision=0), use_container_width=True)
        else:
            st.info("No vehicles match these filters for condition table.")
        
        st.subheader("Quick Overview of Working / Not Working by Vehicle Type (Based on Filter)")
        if COL_VEHICLE_TYPE in veh_df.columns:  # Check if column exists in original df
            if not vehicle_condition_view_df.empty:  # Use the filtered df
                summary_veh_status_rows = []
                for vt_val in vehicle_condition_view_df[COL_VEHICLE_TYPE].unique():
                    sub_df_status = vehicle_condition_view_df[vehicle_condition_view_df[COL_VEHICLE_TYPE] == vt_val]
                    working_count = sub_df_status[COL_STATUS].str.lower().eq("working").sum()
                    not_working_count = sub_df_status[COL_STATUS].str.lower().eq("not working").sum()
                    summary_veh_status_rows.append({
                        "Vehicle Type": vt_val,
                        "Working": working_count,
                        "Not Working": not_working_count,
                        "Total": len(sub_df_status),
                    })
                sum_df_status = pd.DataFrame(summary_veh_status_rows)
                st.dataframe(sum_df_status.style.format(precision=0), use_container_width=True)
            else:
                st.write("No vehicles to summarize status in the current filter.")
        else:
            st.info(f"'{COL_VEHICLE_TYPE}' column not found in vehicles table.")

    # ============ 7. Download shortage ============
    with ammo_tab:
        st.markdown("---")
        st.subheader("Download Ammo Shortage to Excel")
        if not shortage_disp_df.empty:  # Use the main shortage_disp_df from earlier in this tab
            buffer = io.BytesIO()
            # Use try-except for Excel writing
            try:
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    shortage_disp_df.to_excel(writer, sheet_name="ShortageData", index=False)
                st.download_button(
                    label="Download Shortage as Excel", data=buffer.getvalue(),
                    file_name="ammo_shortage_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_shortage_button"
                )
            except Exception as e:
                st.error(f"Could not generate Excel file: {e}")
        else:
            st.info("No shortage data to download based on current filters.")
    add_footer()


# ==================== TAB 4: DECISIONS TOOL (Based on your stable version) ====================
with tab_decisions:
    st.header("Decisions Tool: Scenario Planning & Predictive Analysis")
    st.write("""
        As the manager of 9215, use this tool to forecast both **ammunition usage** and **vehicle availability**
        to make informed decisions about future operations, maintenance schedules, or resource ordering.
    """)

    st.subheader("Ammunition Scenario: Days to Depletion")
    # Using constants for ammo
    # standards_dec = STANDARDS_AMMO (already defined)
    # triple_dec = TRIPLE_AMMO_TYPES (already defined)
    relevant_ammo_types_dec = sorted(list(set(list(STANDARDS_AMMO.keys()) + list(TRIPLE_AMMO_TYPES))))

    usage_data_dec = [{"Ammo Type": ammo_type, "Daily Usage": 0} for ammo_type in relevant_ammo_types_dec]
    usage_df_dec = pd.DataFrame(usage_data_dec)
    usage_edit_dec = st.data_editor(usage_df_dec, num_rows="fixed", use_container_width=True, key="ammo_usage_editor_dec")

    totals_map_dec = {}
    # Use the globally loaded and cleaned ammo_df
    if not ammo_df.empty:
        for ammo_type_dec in relevant_ammo_types_dec:
            if ammo_type_dec in ammo_df.columns:
                totals_map_dec[ammo_type_dec] = ammo_df[ammo_type_dec].sum() # Already numeric
            else:
                totals_map_dec[ammo_type_dec] = 0.0
    else: # Fill with zeros if ammo_df is empty
        for ammo_type_dec in relevant_ammo_types_dec:
            totals_map_dec[ammo_type_dec] = 0.0


    analysis_rows_dec = []
    for _, row_dec in usage_edit_dec.iterrows():
        atype_dec = row_dec["Ammo Type"]
        # Ensure use_rate is float
        use_rate_dec = pd.to_numeric(row_dec["Daily Usage"], errors='coerce')
        if pd.isna(use_rate_dec): use_rate_dec = 0.0

        current_total_dec = totals_map_dec.get(atype_dec, 0.0)
        days_left_dec = (current_total_dec / use_rate_dec) if use_rate_dec > 0 else float('inf')

        analysis_rows_dec.append({
            "Ammo Type": atype_dec, "Current Total": int(current_total_dec),
            "Daily Usage": float(use_rate_dec),
            "Days to Run Out": round(days_left_dec, 1) if days_left_dec != float('inf') else "∞"
        })
    scenario_df_dec = pd.DataFrame(analysis_rows_dec)

    def days_color_dec(val_dec): # Renamed
        if val_dec == "∞": return "background-color: #d4f8d4"
        try: v_dec = float(val_dec)
        except: return ""
        if v_dec < 30: return "background-color: #ff9999"
        elif v_dec < 90: return "background-color: #ffff99"
        else: return "background-color: #d4f8d4"

    sty_scenario_dec = scenario_df_dec.style.format(
        subset=["Daily Usage", "Current Total"], precision=0, na_rep="-"
    ).map(days_color_dec, subset=["Days to Run Out"])
    st.dataframe(sty_scenario_dec, use_container_width=True)
    st.write("""**Interpretation**: Red: <30 days. Yellow: <90 days. Green: Stable.""")
    st.markdown("---")

    st.subheader("Vehicles Scenario: Maintenance/Availability Forecast")
    st.write("""Enter **daily usage hours** and **hours until next maintenance**.""")

    # Prepare scenario dataframe from veh_df, ensure 'category' column exists or handle its absence
    scen_rows_veh = []
    if not veh_df.empty:
        for _, vrow_veh in veh_df.iterrows():
            scen_rows_veh.append({
                "Z": vrow_veh.get(COL_SIMON, ""), "Status": vrow_veh.get(COL_STATUS, ""),
                "Category": vrow_veh.get("category", "N/A"), # Handle missing 'category'
                "Location": vrow_veh.get(COL_LOCATION, ""),
                "Hours to Maintenance": 100, # Default
                "Daily Usage (hrs)": 0 # Default
            })
    scen_veh_df_dec = pd.DataFrame(scen_rows_veh) if scen_rows_veh else pd.DataFrame(columns=["Z", "Status", "Category", "Location", "Hours to Maintenance", "Daily Usage (hrs)"])


    st.write("#### Select Vehicles & Specify Hours to Maintenance / Daily Usage")
    edited_veh_scenario_dec = st.data_editor(
        scen_veh_df_dec, num_rows="dynamic", use_container_width=True, key="veh_scenario_data_dec"
    )

    comp_rows_veh = []
    if not edited_veh_scenario_dec.empty:
        for _, row_veh_scen in edited_veh_scenario_dec.iterrows():
            hours_left_veh = pd.to_numeric(row_veh_scen["Hours to Maintenance"], errors='coerce')
            if pd.isna(hours_left_veh): hours_left_veh = 100.0 # Default if invalid
            daily_use_veh = pd.to_numeric(row_veh_scen["Daily Usage (hrs)"], errors='coerce')
            if pd.isna(daily_use_veh): daily_use_veh = 0.0 # Default if invalid

            days_left_maint = (hours_left_veh / daily_use_veh) if daily_use_veh > 0 else float('inf')
            comp_rows_veh.append({
                "Z": row_veh_scen["Z"], "Status": row_veh_scen["Status"],
                "Category": row_veh_scen["Category"], "Location": row_veh_scen["Location"],
                "Hours to Maintenance": hours_left_veh, "Daily Usage (hrs)": daily_use_veh,
                "Days Until Maintenance": round(days_left_maint, 1) if days_left_maint != float('inf') else "∞"
            })
    comp_veh_df_dec = pd.DataFrame(comp_rows_veh) if comp_rows_veh else pd.DataFrame(columns=["Z", "Status", "Category", "Location", "Hours to Maintenance", "Daily Usage (hrs)", "Days Until Maintenance"])


    def maintenance_color_dec(val_maint): # Renamed
        if val_maint == "∞": return "background-color: #d4f8d4"
        try: v_maint = float(val_maint)
        except: return ""
        if v_maint < 5: return "background-color: #ff9999"
        elif v_maint < 15: return "background-color: #ffff99"
        else: return "background-color: #d4f8d4"

    sty_veh_scenario_dec = comp_veh_df_dec.style.format(
        subset=["Hours to Maintenance", "Daily Usage (hrs)"], precision=0, na_rep="-"
    ).map(maintenance_color_dec, subset=["Days Until Maintenance"])
    st.dataframe(sty_veh_scenario_dec, use_container_width=True)
    st.write("""**Interpretation**: Red: <5 days. Yellow: <15 days. Green: Stable.""")
    add_footer()


# ==================== TAB 5: HISTORY (Enhanced) ====================
with tab_history:
    st.header("History: View Past Snapshots")

    ts_veh_hist = pd.read_sql(f"SELECT DISTINCT ts FROM {TABLE_VEHICLES_HISTORY} ORDER BY ts DESC", conn)["ts"].tolist()
    ts_ammo_hist = pd.read_sql(f"SELECT DISTINCT ts FROM {TABLE_AMMO_HISTORY} ORDER BY ts DESC", conn)["ts"].tolist()
    ts_req_hist_main = pd.read_sql(f"SELECT DISTINCT ts FROM {TABLE_REQUIREMENTS_HISTORY} ORDER BY ts DESC", conn)["ts"].tolist()

    all_hist_ts = sorted(list(set(ts_veh_hist) | set(ts_ammo_hist) | set(ts_req_hist_main)), reverse=True)

    if not all_hist_ts:
        st.info("No history data found. Please save data in other tabs to populate history.")
    else:
        chosen_ts_hist = st.selectbox("Select Snapshot Time (UTC)", all_hist_ts, key="history_ts_selector_main")
        if chosen_ts_hist:
            st.subheader(f"Snapshot at: {chosen_ts_hist} UTC")

            # Vehicles Snapshot
            if chosen_ts_hist in ts_veh_hist:
                df_veh_hist_snap = pd.read_sql(f"SELECT * FROM {TABLE_VEHICLES_HISTORY} WHERE ts=?", conn, params=(chosen_ts_hist,))
                if "ts" in df_veh_hist_snap.columns: df_veh_hist_snap.drop(columns="ts", inplace=True, errors='ignore')
                if COL_SIMON in df_veh_hist_snap.columns:
                    df_veh_hist_snap[COL_SIMON] = clean_id_column(df_veh_hist_snap[COL_SIMON])
                st.markdown("#### Vehicles Snapshot")
                st.dataframe(df_veh_hist_snap.style.format(precision=0), use_container_width=True)
            else:
                st.markdown("#### Vehicles Snapshot")
                st.caption(f"No vehicle data saved at {chosen_ts_hist} UTC.")

            # Ammo Snapshot
            if chosen_ts_hist in ts_ammo_hist:
                df_ammo_hist_snap = pd.read_sql(f"SELECT * FROM {TABLE_AMMO_HISTORY} WHERE ts=?", conn, params=(chosen_ts_hist,))
                if "ts" in df_ammo_hist_snap.columns: df_ammo_hist_snap.drop(columns="ts", inplace=True, errors='ignore')
                if COL_VEHICLE_ID in df_ammo_hist_snap.columns:
                     df_ammo_hist_snap[COL_VEHICLE_ID] = clean_id_column(df_ammo_hist_snap[COL_VEHICLE_ID])
                st.markdown("#### Ammunition Snapshot")
                st.dataframe(df_ammo_hist_snap.style.format(precision=0), use_container_width=True)
            else:
                st.markdown("#### Ammunition Snapshot")
                st.caption(f"No ammunition data saved at {chosen_ts_hist} UTC.")

    st.markdown("---")
    st.subheader("All Requirements Changes History")
    full_req_history_df = pd.read_sql(f"SELECT * FROM {TABLE_REQUIREMENTS_HISTORY} ORDER BY ts DESC, id DESC", conn)
    if full_req_history_df.empty:
        st.caption("No requirements changes have been logged.")
    else:
        # Clean Z in history if needed
        if COL_Z in full_req_history_df.columns:
             full_req_history_df[COL_Z] = clean_id_column(full_req_history_df[COL_Z])
        st.dataframe(full_req_history_df, use_container_width=True)
    add_footer()


# ==================== TAB 6: REQUIREMENTS (New Tab) ====================
with tab_req:
    st.header("Commander Requirements & Notes")

    pluga_unique_req_tab = ["All"] + sorted(req_df[COL_PLUGA].dropna().unique().tolist()) if not req_df.empty and COL_PLUGA in req_df.columns else ["All"]
    # 'Z' in requirements table is the vehicle 'simon'
    z_unique_req_tab = ["All"] + sorted(req_df[COL_Z].dropna().unique().tolist()) if not req_df.empty and COL_Z in req_df.columns else ["All"]


    filter_col_req1, filter_col_req2 = st.columns(2)
    selected_pluga_req_filter_tab = filter_col_req1.selectbox(
        f"Filter by {COL_PLUGA}", pluga_unique_req_tab, key="req_tab_pluga_filter"
    )
    selected_z_req_filter_tab = filter_col_req2.selectbox(
        f"Filter by {COL_Z} (Tank ID)", z_unique_req_tab, key="req_tab_z_filter"
    )

    display_req_df_tab = req_df.copy()
    if selected_pluga_req_filter_tab != "All" and COL_PLUGA in display_req_df_tab.columns:
        display_req_df_tab = display_req_df_tab[display_req_df_tab[COL_PLUGA] == selected_pluga_req_filter_tab]
    if selected_z_req_filter_tab != "All" and COL_Z in display_req_df_tab.columns:
        display_req_df_tab = display_req_df_tab[display_req_df_tab[COL_Z] == selected_z_req_filter_tab]

    # Display specific columns if needed, or all
    cols_to_display_req = [COL_PLUGA, COL_Z, COL_COMMANDER_NOTE, COL_LAST_UPDATED, 'id']
    cols_to_display_req = [col for col in cols_to_display_req if col in display_req_df_tab.columns]
    st.dataframe(display_req_df_tab[cols_to_display_req] if cols_to_display_req else display_req_df_tab, use_container_width=True)


    st.markdown("---")
    st.subheader("Add/Edit Note")

    pluga_options_notes_tab = sorted(veh_df[COL_PLUGA].dropna().unique().tolist()) if not veh_df.empty and COL_PLUGA in veh_df.columns else []
    # For 'Z' (Tank ID), use 'simon' from vehicles table
    z_options_notes_tab = sorted(veh_df[COL_SIMON].dropna().unique().tolist()) if not veh_df.empty and COL_SIMON in veh_df.columns else []


    if not pluga_options_notes_tab or not z_options_notes_tab:
        st.warning("Please ensure vehicle data (with Pluga and Simon/Tank ID) is available to add notes.")
    else:
        selected_pluga_for_note_tab = st.selectbox(
            f"{COL_PLUGA} (for note)", pluga_options_notes_tab, key="req_tab_pluga_select_note"
        )
        selected_z_for_note_tab = st.selectbox( # This 'Z' is the vehicle's 'simon'
            f"{COL_Z} (Tank ID for note)", z_options_notes_tab, key="req_tab_z_select_note"
        )

        current_note_text_tab = ""
        if selected_pluga_for_note_tab and selected_z_for_note_tab and not req_df.empty:
            match_df_tab = req_df[
                (req_df[COL_PLUGA] == selected_pluga_for_note_tab) &
                (req_df[COL_Z] == selected_z_for_note_tab) # Match against 'z' column in requirements
            ]
            if not match_df_tab.empty and COL_COMMANDER_NOTE in match_df_tab.columns:
                current_note_text_tab = match_df_tab.iloc[0][COL_COMMANDER_NOTE]

        note_text_input_tab = st.text_area(
            "Commander Note", value=current_note_text_tab, key="req_tab_note_text_area", height=150
        )

        if st.button("Save Note", key="req_tab_save_note_button"):
            if not selected_pluga_for_note_tab or not selected_z_for_note_tab:
                st.error("Pluga and Z (Tank ID) must be selected to save a note.")
            else:
                now_utc_str_req = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                try:
                    with conn:
                        cursor = conn.execute(
                            f"SELECT id FROM {TABLE_REQUIREMENTS} WHERE {COL_PLUGA}=? AND {COL_Z}=?",
                            (selected_pluga_for_note_tab, selected_z_for_note_tab)
                        )
                        existing_note_req = cursor.fetchone()
                        history_update_type_req = ""

                        if existing_note_req:
                            conn.execute(
                                f"""UPDATE {TABLE_REQUIREMENTS}
                                    SET {COL_COMMANDER_NOTE} = ?, {COL_LAST_UPDATED} = ?
                                    WHERE {COL_PLUGA} = ? AND {COL_Z} = ?""",
                                (note_text_input_tab, now_utc_str_req, selected_pluga_for_note_tab, selected_z_for_note_tab)
                            )
                            history_update_type_req = "Requirement Updated"
                        else:
                            conn.execute(
                                f"""INSERT INTO {TABLE_REQUIREMENTS} ({COL_PLUGA}, {COL_Z}, {COL_COMMANDER_NOTE}, {COL_LAST_UPDATED})
                                    VALUES (?, ?, ?, ?)""",
                                (selected_pluga_for_note_tab, selected_z_for_note_tab, note_text_input_tab, now_utc_str_req)
                            )
                            history_update_type_req = "Requirement Added"

                        conn.execute(
                            f"""INSERT INTO {TABLE_REQUIREMENTS_HISTORY}
                                ({COL_PLUGA}, {COL_Z}, {COL_COMMANDER_NOTE}, update_type, updated_at, ts)
                                VALUES (?, ?, ?, ?, ?, ?)""",
                            (selected_pluga_for_note_tab, selected_z_for_note_tab, note_text_input_tab,
                             history_update_type_req, now_utc_str_req, now_utc_str_req)
                        )
                    st.success("Note saved successfully!")
                    st.cache_data.clear()
                    st.rerun()
                except sqlite3.Error as e:
                    st.error(f"Database error while saving note: {e}")
    add_footer()
