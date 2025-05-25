import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime
import pandas as pd
import plotly.express as px
import numpy as np

DB_PATH = Path("tank_battalion.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)

# --- Ensure history tables exist (robust even after a new DB) ---
def ensure_history_tables(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS vehicles_history AS
    SELECT *, '' as ts FROM vehicles WHERE 0;
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS ammo_history AS
    SELECT *, '' as ts FROM ammo WHERE 0;
    """)
ensure_history_tables(conn)

# -- Data loading and caching
@st.cache_data
def load_data():
    veh = pd.read_sql("SELECT * FROM vehicles", conn)
    ammo = pd.read_sql("SELECT * FROM ammo", conn)
    return veh.fillna(""), ammo.fillna("")

def save_with_history(df, table, hist_table, conn):
    ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    df_copy = df.copy()
    df_copy['ts'] = ts
    with conn:
        df.to_sql(table, conn, if_exists="replace", index=False)
        df_copy.to_sql(hist_table, conn, if_exists="append", index=False)

veh_df, ammo_df = load_data()

# =============== Footer Function ===============
def add_footer():
    st.markdown("---")
    st.write("**9215 Summary Dashboard | Developed by Dr. Avi Luvchik**")
    st.caption("© 2025 Drishtiy LTD. All Rights Reserved.")

# =============== PAGE LAYOUT ===============
st.set_page_config("Tank Battalion Dashboard", layout="wide")
tab1, tab2, tab3, tab4 = st.tabs(["📊 Summary", "🛠️ Vehicles", "📦 Ammunition", "📜 History"])

# ==== SUMMARY TAB ====
with tab1:
    st.title("Battalion Fleet & Ammunition Status")

    # --- Vehicle status KPIs ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Total", len(veh_df))
    col2.metric("Working", veh_df["status"].str.strip().str.lower().eq("working").sum())
    col3.metric("Not Working", veh_df["status"].str.strip().str.lower().eq("not working").sum())

    # --- Filters (live for everything below) ---
    f1, f2, f3, f4 = st.columns(4)
    all_plugas = ["All"] + sorted(veh_df["pluga"].dropna().astype(str).unique().tolist())
    all_locs   = ["All"] + sorted(veh_df["location"].dropna().astype(str).unique().tolist())
    all_z      = ["All"] + sorted(veh_df["simon"].dropna().astype(str).unique().tolist())
    all_types  = ["All"] + [c for c in ["hetz","barzel","calanit","halul","hatzav","regular_556","mag","nafetiz60","teura60","meducut"] if c in ammo_df.columns]
    pluga_filt = f1.selectbox("Filter by Pluga", all_plugas)
    loc_filt   = f2.selectbox("Filter by Location", all_locs)
    z_filt     = f3.selectbox("Filter by Tank (Z)", all_z)
    type_filt  = f4.selectbox("Show only this ammo type", all_types)

    # --------- Standards ---------
    standards = {
        "hetz":3, "barzel":10,
        "regular_556":990, "mag":30, "nafetiz60":21, "teura60":9, "meducut":12
    }
    triple = ("calanit","halul","hatzav")
    triple_std = 27

    # --------- Apply vehicle filter ---------
    veh_view = veh_df.copy()
    if pluga_filt != "All":
        veh_view = veh_view[veh_view["pluga"] == pluga_filt]
    if loc_filt != "All":
        veh_view = veh_view[veh_view["location"] == loc_filt]
    if z_filt != "All":
        veh_view = veh_view[veh_view["simon"].astype(str) == z_filt]
    if not veh_view.empty:
        st.write(f"**Vehicles filtered:** {len(veh_view)}")
    else:
        st.info("No vehicles after filters.")

    # --- Pie/bar breakdowns
    if not veh_view.empty:
        grp = veh_view.groupby(["vehicle_type", "status"], dropna=False).size().unstack(fill_value=0)
        st.dataframe(grp, use_container_width=True, hide_index=False)
        pie_data = veh_view.groupby("vehicle_type").size().reset_index(name="count")
        st.plotly_chart(px.pie(pie_data, names="vehicle_type", values="count", title="Fleet Composition"), use_container_width=True)
        bar_kpi = veh_view.groupby(["vehicle_type", "status"]).size().reset_index(name="count")
        st.plotly_chart(px.bar(bar_kpi, x="vehicle_type", y="count", color="status", barmode="group", title="Status by Vehicle Type"), use_container_width=True)
    st.divider()

    # ==== AMMO FLEXIBLE SHORTAGE ANALYSIS ====
    st.header("Ammunition Shortage Dashboard (filterable, actionable)")
    st.markdown(
        "<span style='display:inline-block; width:18px; height:18px; background:#d4f8d4; border:1px solid #aaa; margin-right:8px;'></span> Green: Meets/exceeds standard "
        "<span style='display:inline-block; width:18px; height:18px; background:#ffb3b3; border:1px solid #aaa; margin-left:24px; margin-right:8px;'></span> Red: Below standard",
        unsafe_allow_html=True
    )

    # --------- Filter ammo based on vehicle filter ---------
    tank_ids = veh_view["simon"].astype(str).tolist()
    ammo_filtered = ammo_df[ammo_df["vehicle_id"].astype(str).isin(tank_ids)].copy()
    if type_filt != "All":
        show_types = [type_filt]
    else:
        show_types = [c for c in ["hetz","barzel","calanit","halul","hatzav","regular_556","mag","nafetiz60","teura60","meducut"] if c in ammo_df.columns]

    # --------- Build shortage table ---------
    shortage_rows = []
    for idx, row in ammo_filtered.iterrows():
        sid = str(row["vehicle_id"])
        meta = {"Pluga": row["pluga"], "Z": row["vehicle_id"]}
        tank_row = veh_df[veh_df["simon"].astype(str) == sid]
        meta["Location"] = tank_row.iloc[0]["location"] if not tank_row.empty else ""
        sdict = {}
        for c in standards:
            if c in row:
                have = float(row[c]) if row[c] not in ["", None] else 0
                miss = max(standards[c] - have, 0)
                sdict[c] = miss
        triple_val = sum(float(row[t]) if t in row and row[t] not in ["",None] else 0 for t in triple)
        triple_miss = max(triple_std - triple_val, 0)
        for t in triple:
            if t in row:
                sdict[t] = max(triple_miss, 0)
        sdict["Calanit+Halul+Hatzav"] = triple_miss
        shortage_row = {**meta, **sdict}
        shortage_rows.append(shortage_row)
    show_cols = ["Pluga", "Location", "Z"] + show_types + [t for t in triple if t in ammo_df.columns] + (["Calanit+Halul+Hatzav"] if "Calanit+Halul+Hatzav" in shortage_rows[0] else [])
    shortage_df = pd.DataFrame(shortage_rows)[show_cols] if shortage_rows else pd.DataFrame()

    # --------- Conditional formatting ---------
    def color_shortages(val, col):
        try: v = float(val)
        except: v = 0
        stds = dict(standards)
        stds["calanit"] = stds["halul"] = stds["hatzav"] = triple_std
        stds["Calanit+Halul+Hatzav"] = triple_std
        if col in stds:
            if v > 0: return "background-color: #ffb3b3"
            else: return "background-color: #d4f8d4"
        return ""
    if not shortage_df.empty:
        st.dataframe(
            shortage_df.style.applymap(lambda v, c=col: color_shortages(v,c), subset=[c for c in show_cols if c not in ["Pluga","Location","Z"]]),
            use_container_width=True
        )
    else:
        st.info("No ammunition data after filtering.")

    # --------- Shortages by Pluga, Location, Z, Type ---------
    st.markdown("### Shortage Summary by Pluga / Location / Tank")
    if not shortage_df.empty:
        group_cols = ["Pluga", "Location"]
        for group in group_cols:
            st.write(f"**Total shortage by {group}:**")
            gtab = shortage_df.groupby(group)[[c for c in shortage_df.columns if c not in ["Pluga","Location","Z"]]].sum()
            st.dataframe(gtab, use_container_width=True)
        st.write("**Total shortage by Tank (Z):**")
        st.dataframe(shortage_df.set_index("Z")[[c for c in shortage_df.columns if c not in ["Pluga","Location","Z"]]], use_container_width=True)

    # --------- Battalion totals vs. standard, and bar chart ---------
    st.markdown("### Battalion totals vs. standards")
    current_total = {c: ammo_filtered[c].astype(float).sum() for c in standards.keys() if c in ammo_filtered.columns}
    triple_total = sum(sum(float(row[t]) if t in row and row[t] not in ["",None] else 0 for t in triple) for _, row in ammo_filtered.iterrows())
    current_total["Calanit+Halul+Hatzav"] = triple_total
    n_tanks = len(ammo_filtered)
    standard_total = {c: standards[c]*n_tanks for c in standards if c in ammo_filtered.columns}
    standard_total["Calanit+Halul+Hatzav"] = triple_std * n_tanks
    chart_data = pd.DataFrame({
        "Ammo Type": list(current_total.keys()),
        "Current": [current_total[k] for k in current_total],
        "Standard": [standard_total.get(k,0) for k in current_total]
    })
    st.plotly_chart(
        px.bar(chart_data, x="Ammo Type", y=["Current", "Standard"], barmode="group", title="Battalion: Current vs Standard"),
        use_container_width=True
    )

    add_footer()

# ==== VEHICLES TAB ====
with tab2:
    st.header("Live vehicle status grid (editable)")
    ed_veh = st.data_editor(
        veh_df,
        use_container_width=True,
        num_rows="dynamic",
        key="veh_edit"
    )
    if st.button("💾 Save vehicle changes", key="save_veh_btn"):
        save_with_history(ed_veh, "vehicles", "vehicles_history", conn)
        st.cache_data.clear()
        st.success("Saved! Changes logged in history.")
    add_footer()

# ==== AMMUNITION TAB ====
with tab3:
    st.header("Live ammunition grid (editable)")
    ed_ammo = st.data_editor(
        ammo_df,
        use_container_width=True,
        num_rows="dynamic",
        key="ammo_edit"
    )
    if st.button("💾 Save ammo changes", key="save_ammo_btn"):
        save_with_history(ed_ammo, "ammo", "ammo_history", conn)
        st.cache_data.clear()
        st.success("Ammo saved! Changes logged in history.")
    add_footer()

# ==== HISTORY TAB ====
with tab4:
    st.header("History: View all past snapshots")
    hist_veh = pd.read_sql("SELECT DISTINCT ts FROM vehicles_history ORDER BY ts DESC", conn)["ts"].tolist()
    hist_ammo = pd.read_sql("SELECT DISTINCT ts FROM ammo_history ORDER BY ts DESC", conn)["ts"].tolist()
    hist_ts = sorted(list(set(hist_veh) & set(hist_ammo)), reverse=True)
    if not hist_ts:
        st.info("No history data available yet. Save vehicles/ammo at least once to create history.")
    else:
        ts_sel = st.selectbox("Select snapshot time", hist_ts)
        veh_hist = pd.read_sql("SELECT * FROM vehicles_history WHERE ts=?", conn, params=[ts_sel]).drop(columns="ts")
        ammo_hist = pd.read_sql("SELECT * FROM ammo_history WHERE ts=?", conn, params=[ts_sel]).drop(columns="ts")
        st.subheader("Vehicles snapshot"); st.dataframe(veh_hist, use_container_width=True)
        st.subheader("Ammo snapshot"); st.dataframe(ammo_hist, use_container_width=True)
    add_footer()