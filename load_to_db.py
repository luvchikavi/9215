import sqlite3, pandas as pd, pathlib

DB_FILE = pathlib.Path("tank_battalion.db")
VEH_CSV = pathlib.Path("vehicles_full.csv")
AMMO_CSV = pathlib.Path("ammo_full.csv")

AMMO_COL_MAP = {
    "Pluga":        "pluga",
    "Z":            "vehicle_id",
    "Hetz":         "hetz",
    "Calanit":      "calanit",
    "Halul":        "halul",
    "Hatzav":       "hatzav",
    "Barzel":       "barzel",
    "5.56":         "regular_556",
    "Mag":          "mag",
    "Nafitiz60":    "nafetiz60",
    "Teura60":      "teura60",
    "Meducut":      "meducut",
    "Rimon Ashan":  "rimon_ashan",
    "Rimon Resses": "rimon_resses",
    "Metan Nituk":  "metan_nituk",
    "Nonel":        "nonel",
    "Comments":     "comments"
}

VEH_COL_MAP = {
    "Type":        "vehicle_type",
    "Categorey":   "categorey",
    "Pluga":       "pluga",
    "Mark":        "mark",
    "Z":           "simon",
    "Location":    "location",
    "Status":      "status",
    "Issue":       "issue",
    "Fixing":      "repair_status",
    "Comments":    "notes"
}

def clean_and_map(df, colmap):
    newcols = {c:colmap[c.strip()] for c in df.columns if c.strip() in colmap}
    df2 = df.rename(columns=newcols)
    return df2[[col for col in colmap.values() if col in df2.columns]]

veh_df = pd.read_csv(VEH_CSV, encoding="utf-8-sig")
veh_df = clean_and_map(veh_df, VEH_COL_MAP)
ammo_df = pd.read_csv(AMMO_CSV, encoding="utf-8-sig")
ammo_df = clean_and_map(ammo_df, AMMO_COL_MAP)

conn = sqlite3.connect(DB_FILE)
with conn:
    conn.execute("DROP TABLE IF EXISTS vehicles")
    conn.execute("DROP TABLE IF EXISTS ammo")

    conn.execute("""
    CREATE TABLE vehicles(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      vehicle_type TEXT,
      categorey TEXT,
      pluga TEXT,
      mark TEXT,
      simon TEXT,
      location TEXT,
      status TEXT,
      issue TEXT,
      repair_status TEXT,
      notes TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE ammo(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      pluga TEXT,
      vehicle_id TEXT,
      hetz INTEGER,
      calanit INTEGER,
      halul INTEGER,
      hatzav INTEGER,
      barzel INTEGER,
      regular_556 INTEGER,
      mag INTEGER,
      nafetiz60 INTEGER,
      teura60 INTEGER,
      meducut INTEGER,
      rimon_ashan INTEGER,
      rimon_resses INTEGER,
      metan_nituk INTEGER,
      nonel INTEGER,
      comments TEXT
    )
    """)
    veh_df.to_sql("vehicles", conn, if_exists="append", index=False)
    ammo_df.to_sql("ammo", conn, if_exists="append", index=False)

print(f"✅ Database refreshed. {len(veh_df)} vehicles, {len(ammo_df)} ammo rows.")