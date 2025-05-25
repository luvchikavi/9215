import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime
import pandas as pd
import plotly.express as px
import io

# ==================== DB & INITIAL SETUP ====================

DB_PATH = Path("tank_battalion.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)

def ensure_history_tables(cnx):
    """
    Create the history tables if they don't exist yet.
    They mirror 'vehicles' and 'ammo' structure + 'ts' for timestamps.
    """
    cnx.execute("""
    CREATE TABLE IF NOT EXISTS vehicles_history AS
    SELECT *, '' as ts FROM vehicles WHERE 0;
    """)
    cnx.execute("""
    CREATE TABLE IF NOT EXISTS ammo_history AS
    SELECT *, '' as ts FROM ammo WHERE 0;
    """)
    cnx.commit()

ensure_history_tables(conn)

@st.cache_data
def load_data():
    """
    Load from vehicles & ammo tables, remove NaNs,
    cast columns like simon/vehicle_id to strings (no .0).
    """
    df_veh = pd.read_sql("SELECT * FROM vehicles", conn).fillna("")
    df_ammo = pd.read_sql("SELECT * FROM ammo", conn).fillna("")

    # Convert certain ID columns from float-like to string (no .0)
    if "simon" in df_veh.columns:
        df_veh["simon"] = df_veh["simon"].apply(
            lambda x: str(int(float(x))) if str(x).replace(".", "").isdigit() else str(x)
        )
    if "vehicle_id" in df_ammo.columns:
        df_ammo["vehicle_id"] = df_ammo["vehicle_id"].apply(
            lambda x: str(int(float(x))) if str(x).replace(".", "").isdigit() else str(x)
        )

    return df_veh, df_ammo

def save_with_history(df, table, hist_table, cnx):
    """
    Save 'df' into 'table' (replace)
    and append timestamped snapshot into 'hist_table'.
    """
    ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    df_copy = df.copy()
    df_copy["ts"] = ts

    with cnx:
        df.to_sql(table, cnx, if_exists="replace", index=False)
        df_copy.to_sql(hist_table, cnx, if_exists="append", index=False)

veh_df, ammo_df = load_data()

# ==================== FOOTER ====================
def add_footer():
    st.markdown("---")
    st.write("**9215 Summary Dashboard | Developed by Dr. Avi Luvchik**")
    st.caption("© 2025 Drishtiy LTD. All Rights Reserved.")

# ==================== STREAMLIT CONFIG & LAYOUT ====================
st.set_page_config("9215 Dashboard", layout="wide")

# Place the logo at the top (before tabs):
st.image("9215.png", width=150)
st.title("9215 Dashboard")

tabs = st.tabs(["Vehicles", "Ammunition", "Summary", "Decisions Tool", "History"])
tab_vehicles, tab_ammo, tab_summary, tab_decisions, tab_history = tabs

# ----------------------------------------------------------------
# TAB 1: VEHICLES (EDITABLE)
# ----------------------------------------------------------------
with tab_vehicles:
    st.header("Vehicles (Editable)")

    edited_veh = st.data_editor(
        veh_df,
        use_container_width=True,
        num_rows="dynamic"
    )

    if st.button("💾 Save vehicle changes"):
        save_with_history(edited_veh, "vehicles", "vehicles_history", conn)
        st.cache_data.clear()
        st.success("Vehicle data saved & logged in history.")

    add_footer()

# ----------------------------------------------------------------
# TAB 2: AMMUNITION (EDITABLE)
# ----------------------------------------------------------------
with tab_ammo:
    st.header("Ammunition (Editable)")

    edited_ammo = st.data_editor(
        ammo_df,
        use_container_width=True,
        num_rows="dynamic"
    )

    if st.button("💾 Save ammo changes"):
        save_with_history(edited_ammo, "ammo", "ammo_history", conn)
        st.cache_data.clear()
        st.success("Ammo data saved & logged in history.")

    add_footer()

# ----------------------------------------------------------------
# TAB 3: SUMMARY
# ----------------------------------------------------------------
with tab_summary:
    st.header("Ammunition & 9215 Overview")

    # ============ 1. Ammo standards ============
    standards = {
        "hetz": 3,
        "barzel": 10,
        "regular_556": 990,
        "mag": 30,
        "nafetiz60": 21,
        "teura60": 9,
        "meducut": 12
    }
    triple = ("calanit", "halul", "hatzav")
    triple_std = 27

    # ============ 2. Filter controls for ammo shortage ============

    st.subheader("Filter for Ammunition Shortage Table")
    c1, c2, c3, c4 = st.columns(4)
    all_plugas = ["All"] + sorted(set(str(x) for x in veh_df["pluga"] if x != ""))
    all_locs = ["All"] + sorted(set(str(x) for x in veh_df["location"] if x != ""))
    all_z = ["All"] + sorted(set(str(x) for x in veh_df["simon"] if x != ""))
    all_types = ["All"] + list(standards.keys()) + ["Calanit+Halul+Hatzav"]

    pluga_sel = c1.selectbox("Pluga", all_plugas)
    loc_sel = c2.selectbox("Location", all_locs)
    z_sel = c3.selectbox("Tank (Z)", all_z)
    type_sel = c4.selectbox("Ammo Type", all_types)

    # Filter vehicles for ammo
    veh_view = veh_df.copy()
    if pluga_sel != "All":
        veh_view = veh_view[veh_view["pluga"] == pluga_sel]
    if loc_sel != "All":
        veh_view = veh_view[veh_view["location"] == loc_sel]
    if z_sel != "All":
        veh_view = veh_view[veh_view["simon"] == z_sel]

    # Filter ammo
    tank_ids = veh_view["simon"].tolist()
    ammo_view = ammo_df[ammo_df["vehicle_id"].isin(tank_ids)].copy()

    # Decide which ammo columns to show
    if type_sel == "All":
        show_types = list(standards.keys()) + list(triple)
    elif type_sel == "Calanit+Halul+Hatzav":
        show_types = list(triple)
    else:
        show_types = [type_sel] if type_sel else []

    # ============ 3. Ammunition Shortage Table (with current & shortage) ============

    st.subheader("Ammunition Shortage Table")

    shortage_rows = []
    shortage_numeric_rows = []

    for _, row in ammo_view.iterrows():
        sid = row["vehicle_id"]
        vmatch = veh_df[veh_df["simon"] == sid]
        row_pluga = row.get("pluga", "")
        row_loc = row.get("location", "")
        if row_pluga == "" and not vmatch.empty:
            row_pluga = vmatch.iloc[0]["pluga"]
        if row_loc == "" and not vmatch.empty:
            row_loc = vmatch.iloc[0]["location"]

        # For display
        disp = {"Pluga": row_pluga, "Location": row_loc, "Z": sid}
        shrt = {"Pluga": row_pluga, "Location": row_loc, "Z": sid}

        # Single-type
        for c in standards:
            have = float(row[c]) if c in row and row[c] not in ["", None] else 0
            need = standards[c]
            short = max(need - have, 0)
            if short > 0:
                disp[c] = f"{int(have)}({int(short)})"
            else:
                disp[c] = f"{int(have)}"
            shrt[c] = short

        # Triple
        triple_val = 0
        tvals = {}
        for t in triple:
            cur = float(row[t]) if t in row and row[t] not in ["", None] else 0
            triple_val += cur
            tvals[t] = cur
        triple_short = max(triple_std - triple_val, 0)
        for t in triple:
            if triple_short > 0:
                disp[t] = f"{int(tvals[t])}({int(triple_short)})"
            else:
                disp[t] = f"{int(tvals[t])}"
            shrt[t] = triple_short

        # Combined column if relevant
        if "Calanit+Halul+Hatzav" in (show_types + ["Calanit+Halul+Hatzav"]):
            if triple_short > 0:
                disp["Calanit+Halul+Hatzav"] = f"{int(triple_val)}({int(triple_short)})"
            else:
                disp["Calanit+Halul+Hatzav"] = f"{int(triple_val)}"
            shrt["Calanit+Halul+Hatzav"] = triple_short

        shortage_rows.append(disp)
        shortage_numeric_rows.append(shrt)

    shortage_disp_df = pd.DataFrame(shortage_rows)
    shortage_num_df = pd.DataFrame(shortage_numeric_rows)

    base_cols = ["Pluga", "Location", "Z"]
    disp_cols = base_cols + sorted(set(show_types))
    if (
        "Calanit+Halul+Hatzav" in shortage_disp_df.columns
        and (type_sel == "All" or type_sel == "Calanit+Halul+Hatzav")
    ):
        disp_cols.append("Calanit+Halul+Hatzav")
    disp_cols = [c for c in disp_cols if c in shortage_disp_df.columns]

    shortage_disp_df = shortage_disp_df[disp_cols] if not shortage_disp_df.empty else pd.DataFrame()
    shortage_num_df = shortage_num_df[disp_cols] if not shortage_num_df.empty else pd.DataFrame()

    if not shortage_disp_df.empty:
        st.markdown(
            "<span style='display:inline-block; width:18px; height:18px; background:#d4f8d4;"
            "border:1px solid #999;'></span> **Meets standard** &nbsp;&nbsp;"
            "<span style='display:inline-block; width:18px; height:18px; background:#ffb3b3;"
            "border:1px solid #999;'></span> **Below standard**",
            unsafe_allow_html=True
        )

        def highlight_shortage(data):
            color_map = pd.DataFrame("", index=data.index, columns=data.columns)
            for col in disp_cols:
                if col not in base_cols:
                    for i in data.index:
                        short_val = shortage_num_df.loc[i, col]
                        try:
                            valf = float(short_val)
                            if valf > 0:
                                color_map.loc[i, col] = "background-color: #ffb3b3"
                            else:
                                color_map.loc[i, col] = "background-color: #d4f8d4"
                        except:
                            pass
            return color_map

        sty = shortage_disp_df.style.apply(highlight_shortage, axis=None)
        st.dataframe(sty, use_container_width=True)
    else:
        st.info("No shortage data under these filters.")

    # ============ 4. Quick shortage percentage table ============
    st.markdown("---")
    st.subheader("Quick Overview of Shortage in % by Ammo Type")

    n_tanks = len(veh_view)
    if n_tanks > 0:
        summary_data = []
        for c in standards:
            col_current = ammo_view[c].replace("", 0).astype(float).sum() if c in ammo_view.columns else 0
            col_need = standards[c] * n_tanks
            col_short = max(col_need - col_current, 0)
            short_percent = 0 if col_need == 0 else (col_short / col_need) * 100
            summary_data.append({
                "Type": c,
                "Current": int(col_current),
                "Standard": int(col_need),
                "Shortage": int(col_short),
                "Shortage%": f"{short_percent:.1f}%"
            })
        # triple
        sum_triple = 0
        for _, row in ammo_view.iterrows():
            tv = 0.0
            for t in triple:
                if t in row and row[t] not in ["", None]:
                    tv += float(row[t])
            sum_triple += tv
        need_triple = triple_std * n_tanks
        short_triple = max(need_triple - sum_triple, 0)
        shortp_triple = 0 if need_triple == 0 else (short_triple / need_triple) * 100
        summary_data.append({
            "Type": "Calanit+Halul+Hatzav",
            "Current": int(sum_triple),
            "Standard": int(need_triple),
            "Shortage": int(short_triple),
            "Shortage%": f"{shortp_triple:.1f}%"
        })

        short_summary_df = pd.DataFrame(summary_data)
        st.dataframe(short_summary_df.style.format(precision=0), use_container_width=True)
    else:
        st.info("No tanks in the filter to compute shortage%.")

    # ============ 5. 9215 Totals vs. Standards (bar chart), scale regular_556 ============
    st.markdown("---")
    st.subheader("9215 Totals vs. Standards")

    if n_tanks > 0:
        # compute current totals
        cur_map = {}
        for c in standards:
            if c in ammo_view.columns:
                total_val = ammo_view[c].replace("", 0).astype(float).sum()
                cur_map[c] = total_val
        # triple
        total_triple = 0
        for _, row in ammo_view.iterrows():
            val_sum = 0
            for t in triple:
                if t in row and row[t] not in ["", None]:
                    val_sum += float(row[t])
            total_triple += val_sum
        cur_map["Calanit+Halul+Hatzav"] = total_triple

        # standards
        std_map = {}
        for c in standards:
            std_map[c] = standards[c] * n_tanks
        std_map["Calanit+Halul+Hatzav"] = triple_std * n_tanks

        # scale regular_556
        chart_keys = list(cur_map.keys())
        chart_cur = {}
        chart_std = {}
        for k in chart_keys:
            if k == "regular_556":
                newk = "regular_556 (x1000)"
                chart_cur[newk] = cur_map[k] / 1000
                chart_std[newk] = std_map[k] / 1000
            else:
                chart_cur[k] = cur_map[k]
                chart_std[k] = std_map[k]

        chart_df = pd.DataFrame({
            "Ammo Type": list(chart_cur.keys()),
            "Current": list(chart_cur.values()),
            "Standard": [chart_std[x] for x in chart_cur.keys()]
        })
        fig_batt = px.bar(
            chart_df, x="Ammo Type", y=["Current","Standard"],
            barmode="group", title="9215: Current vs Standard"
        )
        st.plotly_chart(fig_batt, use_container_width=True)
    else:
        st.info("No data to aggregate (zero tanks match your filters).")

    # ============ 6. Vehicles Condition Table (like ammo) ============

    st.markdown("---")
    st.subheader("Vehicles Condition Table")

    # Filters for vehicles
    # If your table has 'category' col, we filter by it:
    all_types = ["All"] + sorted(set(str(x) for x in veh_df["vehicle_type"] if x != ""))
    col_loc, col_pluga, col_vtype = st.columns(3)
    loc_v = col_loc.selectbox("Location (Veh)", all_locs, key="v_loc")
    pluga_v = col_pluga.selectbox("Pluga (Veh)", all_plugas, key="v_pluga")
    vtype_v = col_vtype.selectbox("Vehicle Type", all_types, key="v_vehicle_type")

    vehicle_view_df = veh_df.copy()
    if loc_v != "All":
        vehicle_view_df = vehicle_view_df[vehicle_view_df["location"] == loc_v]
    if pluga_v != "All":
        vehicle_view_df = vehicle_view_df[vehicle_view_df["pluga"] == pluga_v]
    if vtype_v != "All":
        vehicle_view_df = vehicle_view_df[vehicle_view_df["vehicle_type"] == vtype_v]

    # Then we color-code the 'status' column green/red as before:
    def highlight_vehicle_status(row):
        status_val = row.get("status", "").strip().lower()
        if status_val == "working":
            return "background-color: #d4f8d4"
        elif status_val == "not working":
            return "background-color: #ffb3b3"
        return ""

    if not vehicle_view_df.empty:
        sty_veh = vehicle_view_df.style.apply(
            lambda s: [highlight_vehicle_status(s) if col=="status" else "" for col in s.index],
            axis=1
        )
        st.dataframe(sty_veh.format(precision=0), use_container_width=True)
    else:
        st.info("No vehicles match these filters.")

    # Quick overview by vehicle_type
    st.subheader("Quick Overview of Working / Not Working by Vehicle Type")
    if "vehicle_type" in veh_df.columns:
        if not vehicle_view_df.empty:
            group_df = vehicle_view_df.copy()
            summaries = []
            for vt in group_df["vehicle_type"].unique():
                sub = group_df[group_df["vehicle_type"] == vt]
                working_count = sub["status"].str.lower().eq("working").sum()
                not_working_count = sub["status"].str.lower().eq("not working").sum()
                summaries.append({
                    "Vehicle Type": vt,
                    "Working": working_count,
                    "Not Working": not_working_count,
                    "Total": len(sub)
                })
            sum_df = pd.DataFrame(summaries)
            st.dataframe(sum_df.style.format(precision=0), use_container_width=True)
        else:
            st.write("No vehicles to summarize in this filter.")
    else:
        st.info("No 'vehicle_type' column found in vehicles. Please adjust the code if needed.")

    # ============ 7. Download shortage & maybe vehicles? ============

    st.markdown("---")
    st.subheader("Download Ammo Shortage to Excel")
    if not shortage_disp_df.empty:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            shortage_disp_df.to_excel(writer, sheet_name="Shortage", index=False)
            writer.close()
        st.download_button(
            label="Download Shortage as Excel",
            data=buffer.getvalue(),
            file_name="shortage.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("No shortage data to download.")

    add_footer()

# ----------------------------------------------------------------
# TAB 4: DECISIONS TOOL
# ----------------------------------------------------------------
with tab_decisions:
    st.header("Decisions Tool: Scenario Planning & Predictive Analysis")

    st.write("""
        As the manager of 9215, use this tool to forecast both **ammunition usage** and **vehicle availability** 
        to make informed decisions about future operations, maintenance schedules, or resource ordering.
    """)

    # -------------------------------------------------------------
    # 1. Ammunition Scenario - same as before
    # -------------------------------------------------------------
    st.subheader("Ammunition Scenario: Days to Depletion")

    standards = {
        "hetz": 3,
        "barzel": 10,
        "regular_556": 990,
        "mag": 30,
        "nafetiz60": 21,
        "teura60": 9,
        "meducut": 12
    }
    triple = ("calanit", "halul", "hatzav")

    relevant_ammo_types = sorted(set(list(standards.keys()) + list(triple)))

    # Daily usage table
    usage_data = []
    for ammo_type in relevant_ammo_types:
        usage_data.append({"Ammo Type": ammo_type, "Daily Usage": 0})
    usage_df = pd.DataFrame(usage_data)
    usage_edit = st.data_editor(usage_df, num_rows="fixed", use_container_width=True, key="ammo_usage_editor")

    # Summation of current ammo across *all* vehicles
    totals_map = {}
    for ammo_type in relevant_ammo_types:
        if ammo_type in ammo_df.columns:
            sum_val = ammo_df[ammo_type].replace("",0).astype(float).sum()
        else:
            sum_val = 0
        totals_map[ammo_type] = sum_val

    analysis_rows = []
    for _, row in usage_edit.iterrows():
        atype = row["Ammo Type"]
        use_rate = row["Daily Usage"]
        current_total = totals_map.get(atype, 0)
        # if daily usage=0 => infinite
        if use_rate > 0:
            days_left = current_total / use_rate
        else:
            days_left = 9999999
        analysis_rows.append({
            "Ammo Type": atype,
            "Current Total": int(current_total),
            "Daily Usage": float(use_rate),
            "Days to Run Out": round(days_left, 1) if days_left < 9999999 else "∞"
        })
    scenario_df = pd.DataFrame(analysis_rows)

    def days_color(val):
        if val == "∞":
            return "background-color: #d4f8d4"  # green
        try:
            v = float(val)
        except:
            return ""
        if v < 30:
            return "background-color: #ff9999"  # red
        elif v < 90:
            return "background-color: #ffff99"  # yellow
        else:
            return "background-color: #d4f8d4"   # green

    sty_scenario = scenario_df.style.format(
        subset=["Daily Usage", "Current Total"], precision=0
    ).map(days_color, subset=["Days to Run Out"])

    st.dataframe(sty_scenario, use_container_width=True)
    st.write("""
        **Interpretation**: 
        - Red: ammo type will run out within 30 days at given usage.
        - Yellow: runs out within 3 months.
        - Green: stable or no usage.
    """)

    st.markdown("---")

    # -------------------------------------------------------------
    # 2. Vehicles Scenario - e.g. usage hours, next maintenance
    # -------------------------------------------------------------
    st.subheader("Vehicles Scenario: Maintenance/Availability Forecast")

    st.write("""
        Enter the expected **daily usage hours** for each vehicle or a subset, 
        and an estimate of **hours until next maintenance**. 
        The tool will highlight vehicles close to a required maintenance threshold.
    """)

    # We can store "hours_left" or "maintenance_threshold" in the vehicles DB, or just do a scenario here.
    # For demonstration, let's let the user pick a subset of vehicles, 
    # then manually input "hours_to_maintenance" and "daily_usage" for each, 
    # and compute "days_until_maintenance".
    vcols = ["simon","status","category","location","hours_to_maintenance","daily_usage"]
    # We'll build a small scenario df from the vehicles table
    # Each vehicle might have an integer hours_to_maintenance. If not, we'll set 100 as default.
    # daily_usage default = 0

    scen_rows = []
    for _, vrow in veh_df.iterrows():
        scen_rows.append({
            "Z": vrow["simon"],
            "Status": vrow.get("status",""),
            "Category": vrow.get("category",""),
            "Location": vrow.get("location",""),
            # We'll assume hours_to_maintenance not in DB, so default to 100
            "Hours to Maintenance": 100,
            # daily usage default 0
            "Daily Usage (hrs)": 0
        })
    scen_veh_df = pd.DataFrame(scen_rows)

    st.write("#### Select Vehicles & Specify Hours to Maintenance / Daily Usage")
    edited_veh_scenario = st.data_editor(
        scen_veh_df,
        num_rows="dynamic",
        use_container_width=True,
        key="veh_scenario_data"
    )

    # Next, compute "days until maintenance" = Hours to Maintenance / Daily Usage(hrs).
    # If usage=0 => infinite. We'll color code.
    comp_rows = []
    for _, row in edited_veh_scenario.iterrows():
        z = row["Z"]
        hours_left = row["Hours to Maintenance"]
        daily_use = row["Daily Usage (hrs)"]
        if isinstance(hours_left, str) and hours_left.isdigit():
            hours_left = float(hours_left)
        elif not isinstance(hours_left, (int,float)):
            hours_left = 100.0
        if isinstance(daily_use, str) and daily_use.isdigit():
            daily_use = float(daily_use)
        elif not isinstance(daily_use, (int,float)):
            daily_use = 0.0

        if daily_use > 0:
            days_left = round(hours_left / daily_use, 1)
        else:
            days_left = "∞"

        comp_rows.append({
            "Z": z,
            "Status": row["Status"],
            "Category": row["Category"],
            "Location": row["Location"],
            "Hours to Maintenance": hours_left,
            "Daily Usage (hrs)": daily_use,
            "Days Until Maintenance": days_left
        })
    comp_veh_df = pd.DataFrame(comp_rows)

    # Color code if "days until maintenance" < 5 => red, < 15 => yellow, else green
    def maintenance_color(val):
        if val == "∞":
            return "background-color: #d4f8d4"
        try:
            v = float(val)
        except:
            return ""
        if v < 5:
            return "background-color: #ff9999"
        elif v < 15:
            return "background-color: #ffff99"
        else:
            return "background-color: #d4f8d4"

    sty_veh_scenario = comp_veh_df.style.format(
        subset=["Hours to Maintenance","Daily Usage (hrs)"], precision=0
    ).map(maintenance_color, subset=["Days Until Maintenance"])

    st.dataframe(sty_veh_scenario, use_container_width=True)

    st.write("""
        **Interpretation**:
        - Red: Vehicle due for maintenance within 5 days at the current usage rate.
        - Yellow: Due within 15 days.
        - Green: Safe for more than 15 days or infinite usage if 0 daily usage.
    """)

    add_footer()

# ----------------------------------------------------------------
# TAB 5: HISTORY
# ----------------------------------------------------------------
with tab_history:
    st.header("History: View Past Snapshots")

    hist_veh = pd.read_sql("SELECT DISTINCT ts FROM vehicles_history ORDER BY ts DESC", conn)["ts"].tolist()
    hist_ammo = pd.read_sql("SELECT DISTINCT ts FROM ammo_history ORDER BY ts DESC", conn)["ts"].tolist()
    hist_ts = sorted(list(set(hist_veh) & set(hist_ammo)), reverse=True)

    if not hist_ts:
        st.info("No history data found. Please save Vehicles/Ammo at least once.")
    else:
        chosen_ts = st.selectbox("Select snapshot time", hist_ts)
        df_veh_hist = pd.read_sql("SELECT * FROM vehicles_history WHERE ts=?", conn, params=[chosen_ts])
        df_ammo_hist = pd.read_sql("SELECT * FROM ammo_history WHERE ts=?", conn, params=[chosen_ts])

        for df_h in [df_veh_hist, df_ammo_hist]:
            if "ts" in df_h.columns:
                df_h.drop(columns="ts", inplace=True, errors="ignore")
            for col in ["simon", "vehicle_id"]:
                if col in df_h.columns:
                    df_h[col] = df_h[col].apply(
                        lambda x: str(int(float(x))) if str(x).replace(".","").isdigit() else str(x)
                    )

        st.subheader("Vehicles Snapshot")
        st.dataframe(df_veh_hist.style.format(precision=0), use_container_width=True)

        st.subheader("Ammo Snapshot")
        st.dataframe(df_ammo_hist.style.format(precision=0), use_container_width=True)

    add_footer()