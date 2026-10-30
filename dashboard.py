import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine
from datetime import datetime
import os
import sys
import toml
import threading
import time
import zipfile
import io
from urllib.parse import quote_plus

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="Visibility IQ Dashboard",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Demo mode: run with synthetic CSVs from ./sample_data (no database needed).
#   streamlit run dashboard.py -- --mock     (or set env var VIQ_MOCK=1)
MOCK_MODE = "--mock" in sys.argv or os.environ.get("VIQ_MOCK") == "1"

SERVER, DATABASE, USERNAME, PASSWORD = None, None, None, None

try:
    if MOCK_MODE:
        raise KeyError("mock mode - skipping credentials")
    SERVER = st.secrets["DB_SERVER"]
    DATABASE = st.secrets["DB_NAME"]
    USERNAME = st.secrets["DB_USER"]
    PASSWORD = st.secrets["DB_PASSWORD"]
except Exception:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [
        os.path.join(current_dir, ".streamlit", "secrets.toml"),
        os.path.join(current_dir, "secrets.toml")
    ]
    if MOCK_MODE:
        possible_paths = []
    file_found = False
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                config = toml.load(f)
                SERVER = config.get("DB_SERVER")
                DATABASE = config.get("DB_NAME")
                USERNAME = config.get("DB_USER")
                PASSWORD = config.get("DB_PASSWORD")
                file_found = True
                break
    if not file_found and not MOCK_MODE:
        st.error("⚠️ Config Error: Could not locate 'secrets.toml' file in your project layout.")
        st.stop()

if not MOCK_MODE and not all([SERVER, DATABASE, USERNAME, PASSWORD]):
    st.error("⚠️ Database credentials are incomplete. Please check your secrets configuration.")
    st.stop()

odbc_str = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={SERVER},1433;"
    f"DATABASE={DATABASE};"
    f"UID={USERNAME};"
    f"PWD={PASSWORD};"
    f"TrustServerCertificate=yes;"
    f"Encrypt=no;"
    f"Connection Timeout=30;"
)
params = quote_plus(odbc_str)
CONNECTION_STRING = f"mssql+pyodbc:///?odbc_connect={params}"

# =============================================================================
# HELPER: strip % and convert to numeric safely (keeps NaN, does NOT fillna 0)
# =============================================================================
def to_numeric_pct(series):
    """Strips '%' if present, converts to float. Returns NaN for unparseable values."""
    return pd.to_numeric(
        series.astype(str).str.replace('%', '', regex=False).str.strip(),
        errors='coerce'
    )

# =============================================================================
# CSS
# =============================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Overall page background */
.stApp { background: #f4f6fb; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: #ffffff;
    padding-top: 1rem;
    border-right: 1px solid #e2e8f0;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    color: #1e293b !important;
}

.stSelectbox div[data-baseweb="select"] > div {
    background: white !important; border-radius: 10px !important;
    border: 1px solid #cbd5e1 !important; min-height: 45px;
}
.stSelectbox span { color: #111827 !important; font-weight: 500 !important; }
.stDateInput input { background: white !important; color: #111827 !important; }

/* KPI metric cards */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    padding: 1.1rem 1.2rem;
    border-radius: 16px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    transition: box-shadow 0.2s ease;
}
[data-testid="stMetric"]:hover { box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08); }
[data-testid="stMetricLabel"] {
    color: #64748b !important; font-size: 0.8rem !important;
    font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.03em;
}
[data-testid="stMetricValue"] { color: #0f172a !important; font-size: 2rem !important; font-weight: 800 !important; }

/* Tabs */
.stTabs [role="tab"] {
    font-weight: 700; color: #475569 !important;
    padding: 0.6rem 1.2rem; font-size: 0.95rem;
}
.stTabs [aria-selected="true"] {
    color: #2563eb !important;
    border-bottom: 3px solid #2563eb !important;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 0.5rem; border-bottom: 1px solid #e2e8f0;
}

/* Plotly chart cards */
.js-plotly-plot {
    background: white !important;
    border-radius: 16px;
    padding: 12px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

/* Data tables */
[data-testid="stDataFrame"] {
    background: white; border-radius: 12px; border: 1px solid #e2e8f0;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

/* Section headers */
h2, h3 {
    color: #1e293b !important;
    font-weight: 800 !important;
    border-left: 4px solid #2563eb;
    padding-left: 0.6rem;
    margin-top: 1.4rem !important;
}

/* Header banner */
.dashboard-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 60%, #3b82f6 100%);
    padding: 1.6rem 2rem; border-radius: 18px; margin-bottom: 1.4rem;
    box-shadow: 0 4px 16px rgba(37, 99, 235, 0.18);
}
.dashboard-title { font-size: 1.9rem; font-weight: 800; color: white; letter-spacing: -0.01em; }
.dashboard-subtitle { color: rgba(255,255,255,0.85); margin-top: 4px; font-size: 0.92rem; }

/* Empty state */
.empty-state {
    background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 12px;
    padding: 2rem; text-align: center; color: #94a3b8; font-size: 0.9rem;
}

/* Insight / summary callout box (after charts) */
.insight-box {
    background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%);
    border: 1px solid #bfdbfe;
    border-left: 4px solid #2563eb;
    border-radius: 12px;
    padding: 0.85rem 1.1rem;
    margin: -0.4rem 0 1.1rem 0;
    font-size: 0.88rem;
    color: #334155;
    line-height: 1.5;
}
.insight-box b { color: #1e3a5f; }
.insight-label {
    display: inline-block;
    background: #2563eb;
    color: white;
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 2px 8px;
    border-radius: 6px;
    margin-right: 8px;
}

/* Section caption under subheaders */
.section-caption {
    color: #64748b; font-size: 0.88rem; margin-top: -0.6rem; margin-bottom: 0.8rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="dashboard-header">
    <div class="dashboard-title">📡 Visibility IQ Dashboard</div>
    <div class="dashboard-subtitle">Executive Fleet Intelligence &nbsp;|&nbsp; Version 2.0</div>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# INSIGHT / SUMMARY HELPER — renders a light callout box under a chart
# =============================================================================
def insight(text):
    """Render a brief, plain-language summary box under a chart for stakeholders."""
    st.markdown(
        f'<div class="insight-box"><span class="insight-label">Insight</span>{text}</div>',
        unsafe_allow_html=True
    )

# =============================================================================
# PLOTLY THEME
# =============================================================================
PLOTLY_THEME = dict(
    template="simple_white",
    paper_bgcolor="white",
    plot_bgcolor="white",
    font=dict(family="Inter", color="#111827", size=13),
    title_font=dict(size=15, color="#111827"),
    margin=dict(l=20, r=20, t=50, b=20),
    height=420
)
COLOR_SEQ = px.colors.qualitative.Safe

def apply_theme(fig, title=" "):
    """Apply standard theme. Pass title string — always set even if empty string."""
    fig.update_layout(**PLOTLY_THEME, title=title)
    return fig

def date_col(df):
    """Return the date column name for a dataframe."""
    return 'Created_Date' if 'Created_Date' in df.columns else ('Date' if 'Date' in df.columns else None)

# =============================================================================
# DATA LOADING
# =============================================================================
@st.cache_data(ttl=300)
def load_data(query):
    _engine = create_engine(CONNECTION_STRING)
    try:
        with _engine.connect() as conn:
            return pd.read_sql(query, conn)
    finally:
        _engine.dispose()

# =============================================================================
# CSV FALLBACK CONFIG
# Maps each table name to its CSV filename (placed in same folder as script)
# =============================================================================
CSV_FALLBACK = {
    "Battery_Level_Master":                      "Battery_Level_Master.csv",
    "Battery_Swap_Activity_Master":              "Battery_Swap_Activity_Master.csv",
    "Battery_Discharge_Rate_Master":             "Battery_Discharge_Rate_Master.csv",
    "Smart_Battery_Health_Master":               "Smart_Battery_Health_Master.csv",
    "Application_Analytics_Device_Usage_Master": "Application_Analytics_Device_Usage_Master.csv",
    "Total_Device_Master":                       "Total_Device_Master.csv",
    "Device_Disruption_Master":                  "Device_Disruption_Master.csv",
    "Device_Disruption_Device_Master":           "Device_Disruption_Device_Master.csv",
    "Storage_Memory_Utilization_Master":         "Storage_Memory_Utilization_Master.csv",
    "Out_Of_Contanct_Device_Master":             "Out_Of_Contanct_Device_Master.csv",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def normalize_df(df):
    """
    Normalize column types after loading from CSV.
    Serial_Number must always be string — if pandas reads nulls it infers float64,
    which breaks merges against string columns from other tables.
    """
    if 'Serial_Number' in df.columns:
        df['Serial_Number'] = df['Serial_Number'].astype(str).str.strip().replace('nan', pd.NA)
    return df

def load_csv_fallback(table_name):
    """Load data from a local CSV file when DB is unavailable."""
    filename = CSV_FALLBACK.get(table_name)
    if not filename:
        return pd.DataFrame()
    csv_path = os.path.join(SCRIPT_DIR, "sample_data" if MOCK_MODE else "", filename)
    if os.path.exists(csv_path):
        return normalize_df(pd.read_csv(csv_path))
    return pd.DataFrame()

DB_CONNECTED = True

try:
    if MOCK_MODE:
        raise RuntimeError("mock mode")
    df_level             = load_data("SELECT * FROM Battery_Level_Master")
    df_swap              = load_data("SELECT * FROM Battery_Swap_Activity_Master")
    df_discharge         = load_data("SELECT * FROM Battery_Discharge_Rate_Master")
    df_health            = load_data("SELECT * FROM Smart_Battery_Health_Master")
    df_app               = load_data("SELECT * FROM Application_Analytics_Device_Usage_Master")
    df_total             = load_data("SELECT * FROM Total_Device_Master")
    df_disruption        = load_data("SELECT * FROM Device_Disruption_Master")
    df_disruption_device = load_data("SELECT * FROM Device_Disruption_Device_Master")
    df_storage           = load_data("SELECT * FROM Storage_Memory_Utilization_Master")
    df_ooc               = load_data("SELECT * FROM Out_Of_Contanct_Device_Master")
except Exception as e:
    DB_CONNECTED = False
    if MOCK_MODE:
        st.info("🧪 Demo mode: showing synthetic sample data (no database connected).")
    else:
        st.warning(
            f"⚠️ Database connection failed: {e}\n\n"
            "Falling back to local CSV files. Data may not reflect the latest updates."
        )
    df_level             = load_csv_fallback("Battery_Level_Master")
    df_swap              = load_csv_fallback("Battery_Swap_Activity_Master")
    df_discharge         = load_csv_fallback("Battery_Discharge_Rate_Master")
    df_health            = load_csv_fallback("Smart_Battery_Health_Master")
    df_app               = load_csv_fallback("Application_Analytics_Device_Usage_Master")
    df_total             = load_csv_fallback("Total_Device_Master")
    df_disruption        = load_csv_fallback("Device_Disruption_Master")
    df_disruption_device = load_csv_fallback("Device_Disruption_Device_Master")
    df_storage           = load_csv_fallback("Storage_Memory_Utilization_Master")
    df_ooc               = load_csv_fallback("Out_Of_Contanct_Device_Master")

    # If ALL CSVs are empty, nothing to show
    all_empty = all(df.empty for df in [
        df_level, df_swap, df_discharge, df_health, df_app,
        df_total, df_disruption, df_disruption_device, df_storage, df_ooc
    ])
    if all_empty:
        st.error(
            "❌ No CSV fallback files found either. "
            "Please place the CSV files in the same folder as this script."
        )
        st.stop()

# =============================================================================
# AUTOMATED REPORTING PIPELINE
# Exports a summary report every REPORT_INTERVAL_SECONDS in the background.
# Reports are saved to /reports/ folder next to this script.
# =============================================================================
REPORT_INTERVAL_SECONDS = 900   # 15 minutes — matches your dashboard refresh
REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

def generate_report(
    df_level, df_swap, df_discharge, df_health,
    df_app, df_total, df_disruption, df_disruption_device,
    df_storage, df_ooc
):
    """
    Build a summary report dictionary from current dataframes.
    Returns a dict of {sheet_name: DataFrame} ready for export.
    """
    report = {}

    # 1. Battery summary — avg battery level per site
    if not df_level.empty and 'Site_Name' in df_level.columns and 'Battery_Level_Avg' in df_level.columns:
        batt_summary = (
            df_level.groupby('Site_Name')['Battery_Level_Avg']
            .mean().round(2).reset_index()
            .rename(columns={'Battery_Level_Avg': 'Avg_Battery_Level_%'})
        )
        batt_summary['Report_Time'] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        report['Battery_Summary'] = batt_summary

    # 2. Swap summary — total swaps per site
    if not df_swap.empty and 'Site_Name' in df_swap.columns and 'Total_Swap' in df_swap.columns:
        swap_summary = (
            df_swap.groupby('Site_Name')['Total_Swap']
            .sum().reset_index()
            .rename(columns={'Total_Swap': 'Total_Swaps'})
        )
        swap_summary['Report_Time'] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        report['Swap_Summary'] = swap_summary

    # 3. Device status summary
    if not df_total.empty and 'Status' in df_total.columns:
        device_summary = (
            df_total['Status'].value_counts()
            .reset_index()
            .rename(columns={'index': 'Status', 'Status': 'Count'})
        )
        device_summary['Report_Time'] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        report['Device_Status'] = device_summary

    # 4. Disruption summary — total disruptions per device
    if not df_disruption_device.empty and 'Serial_Number' in df_disruption_device.columns and 'Total_Disruption' in df_disruption_device.columns:
        dis_summary = (
            df_disruption_device.groupby('Serial_Number')['Total_Disruption']
            .sum().reset_index()
            .sort_values('Total_Disruption', ascending=False)
        )
        dis_summary['Report_Time'] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        report['Disruption_Summary'] = dis_summary

    # 5. Storage summary — avg memory & storage per model
    if not df_storage.empty and 'Model' in df_storage.columns:
        stor_cols = {}
        if 'Avg_Memory_Consumed_Percentage' in df_storage.columns:
            stor_cols['Avg_Memory_%'] = ('Avg_Memory_Consumed_Percentage', 'mean')
        if 'Avg_Storage_Consumed_Percentage' in df_storage.columns:
            stor_cols['Avg_Storage_%'] = ('Avg_Storage_Consumed_Percentage', 'mean')
        if stor_cols:
            stor_summary = df_storage.groupby('Model').agg(**stor_cols).round(2).reset_index()
            stor_summary['Report_Time'] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            report['Storage_Summary'] = stor_summary

    return report

def export_report(report_dict):
    """Save each sheet as a CSV inside a timestamped zip archive."""
    if not report_dict:
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = os.path.join(REPORTS_DIR, f"VisibilityIQ_Report_{timestamp}.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for sheet_name, df in report_dict.items():
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            zf.writestr(f"{sheet_name}.csv", csv_buffer.getvalue())

def _reporting_loop(
    df_level, df_swap, df_discharge, df_health,
    df_app, df_total, df_disruption, df_disruption_device,
    df_storage, df_ooc, interval
):
    """Background thread: generate and export a report every `interval` seconds."""
    while True:
        try:
            report = generate_report(
                df_level, df_swap, df_discharge, df_health,
                df_app, df_total, df_disruption, df_disruption_device,
                df_storage, df_ooc
            )
            export_report(report)
        except Exception:
            pass  # Never crash the background thread
        time.sleep(interval)

# Start the reporting thread once per session
if "reporting_thread_started" not in st.session_state:
    t = threading.Thread(
        target=_reporting_loop,
        args=(
            df_level, df_swap, df_discharge, df_health,
            df_app, df_total, df_disruption, df_disruption_device,
            df_storage, df_ooc, REPORT_INTERVAL_SECONDS
        ),
        daemon=True
    )
    t.start()
    st.session_state["reporting_thread_started"] = True

for df in [df_level, df_swap, df_discharge, df_health,
           df_app, df_total, df_disruption, df_disruption_device, df_storage, df_ooc]:
    for col in ['Created_Date', 'Date']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

# Measurement columns — strip % but keep NaN (do NOT fillna 0)
pct_cols = ['Battery_Level_Avg', 'Battery_Discharge_Rate', 'Avg_Memory_Consumed_Percentage', 'Avg_Storage_Consumed_Percentage']
for df in [df_level, df_discharge, df_storage]:
    for col in pct_cols:
        if col in df.columns:
            df[col] = to_numeric_pct(df[col])

# Count/sum columns — fill 0 for aggregation
count_cols = ['Total_Swap', 'Charge_Cycle_Count', 'TotalUsage', 'Total_Disruption', 'Total_Anrs', 'Total_Crashes', 'Age']
for df in [df_swap, df_health, df_app, df_disruption_device, df_disruption, df_ooc]:
    for col in count_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.header("🔍 Filters")

    if 'Organisation' in df_total.columns:
        org_opts = ["All"] + sorted(df_total['Organisation'].dropna().unique().tolist())
    else:
        org_opts = ["All", "Demo Organisation"]
    selected_org = st.selectbox("Select Organisation", org_opts, index=0)

    site_options = ["All"] + sorted(df_level['Site_Name'].dropna().unique().tolist())
    selected_site = st.selectbox("Select Site / Plant", site_options, index=0)

    model_options = ["All"] + sorted(df_level['Model'].dropna().unique().tolist())
    selected_model = st.selectbox("Select Device Type", model_options, index=0)

    all_dates = []
    for df in [df_level, df_swap, df_discharge, df_app, df_total, df_disruption, df_storage]:
        col = date_col(df)
        if col:
            vals = df[col].dropna()
            if not vals.empty:
                all_dates.extend([vals.min(), vals.max()])

    global_min = min(all_dates).date() if all_dates else datetime.today().date()
    global_max = max(all_dates).date() if all_dates else datetime.today().date()
    date_range = st.date_input("Date Range", [global_min, global_max], format="DD/MM/YYYY")
    st.markdown("---")

    # Data source indicator
    if DB_CONNECTED:
        st.success("🟢 Live Database")
    else:
        st.warning("🧪 Demo Mode (synthetic data)" if MOCK_MODE else "🟡 CSV Fallback Mode")

    # Manual report download
    st.markdown("**📥 Download Report**")
    if st.button("Generate & Download Now"):
        report_dict = generate_report(
            df_level, df_swap, df_discharge, df_health,
            df_app, df_total, df_disruption, df_disruption_device,
            df_storage, df_ooc
        )
        if report_dict:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for sheet_name, df in report_dict.items():
                    csv_buffer = io.StringIO()
                    df.to_csv(csv_buffer, index=False)
                    zf.writestr(f"{sheet_name}.csv", csv_buffer.getvalue())
            zip_buffer.seek(0)
            st.download_button(
                label="⬇️ Download ZIP",
                data=zip_buffer,
                file_name=f"VisibilityIQ_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip"
            )
        else:
            st.warning("No data available to export.")

    st.markdown("---")
    st.caption("Fleet Intelligence Dashboard | v2.0")

# =============================================================================
# FILTER FUNCTION
# =============================================================================
def filter_df(df):
    if df.empty:
        return df
    mask = pd.Series(True, index=df.index)
    if 'Organisation' in df.columns and selected_org != 'All':
        mask &= df['Organisation'] == selected_org
    if 'Site_Name' in df.columns and selected_site != 'All':
        mask &= df['Site_Name'] == selected_site
    if 'Model' in df.columns and selected_model != 'All':
        mask &= df['Model'] == selected_model
    
    df_date_col = date_col(df)
    if df_date_col and isinstance(date_range, (list, tuple)):
        # Safely handle if the user clicks just one date (tuple of length 1)
        if len(date_range) == 2:
            mask &= (
                (df[df_date_col].dt.date >= date_range[0]) &
                (df[df_date_col].dt.date <= date_range[1])
            )
        elif len(date_range) == 1:
            mask &= (df[df_date_col].dt.date == date_range[0])
            
    return df[mask]

f_level             = filter_df(df_level)
f_swap              = filter_df(df_swap)
f_discharge         = filter_df(df_discharge)
f_health            = filter_df(df_health)
f_app               = filter_df(df_app)
f_total             = filter_df(df_total)
f_disruption        = filter_df(df_disruption)
f_disruption_device = filter_df(df_disruption_device)
f_storage           = filter_df(df_storage)
f_ooc               = filter_df(df_ooc)

# =============================================================================
# TABS
# =============================================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "🔋 Battery Analytics",
    "📱 Application Analytics",
    "🖥️ Device Management",
    "💾 Storage Analytics"
])

def empty_chart(msg="No data available for selected filters."):
    st.markdown(f'<div class="empty-state">📭 {msg}</div>', unsafe_allow_html=True)

def add_time_metrics(df, group_col, value_col):
    """Adds Last Updated, Weekly Avg and Monthly Avg columns."""
    dc = date_col(df)
    if dc is None or value_col not in df.columns:
        return pd.DataFrame()

    latest_date = df[dc].max()
    weekly_cutoff = latest_date - pd.Timedelta(days=7)
    monthly_cutoff = latest_date - pd.Timedelta(days=30)

    result = (
        df.groupby(group_col)
        .agg(
            Last_Updated=(dc, "max"),
            Current_Value=(value_col, "mean")
        )
        .reset_index()
    )

    weekly_avg = (
        df[df[dc] >= weekly_cutoff]
        .groupby(group_col)[value_col]
        .mean()
        .reset_index()
        .rename(columns={value_col: "Weekly Avg"})
    )

    monthly_avg = (
        df[df[dc] >= monthly_cutoff]
        .groupby(group_col)[value_col]
        .mean()
        .reset_index()
        .rename(columns={value_col: "Monthly Avg"})
    )

    result = result.merge(weekly_avg, on=group_col, how="left")
    result = result.merge(monthly_avg, on=group_col, how="left")
    result["Last_Updated"] = result["Last_Updated"].dt.strftime("%d-%m-%Y")

    return result

# =============================================================================
# TAB 1 — BATTERY ANALYTICS
# =============================================================================
with tab1:
    st.subheader("🔋 Battery Analytics")
    st.markdown('<p class="section-caption">Fleet-wide battery health, discharge, swap activity, and charge level performance.</p>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Devices",
              f"{f_level['Serial_Number'].nunique():,}" if not f_level.empty else "—")
    c2.metric("Battery Swaps",
              f"{int(f_swap['Total_Swap'].sum()):,}" if not f_swap.empty else "—")

    if not f_level.empty and 'Battery_Level_Avg' in f_level.columns:
        valid_batt = f_level['Battery_Level_Avg'].dropna()
        c3.metric("Avg Battery Level", f"{valid_batt.mean():.1f}%" if not valid_batt.empty else "—")
    else:
        c3.metric("Avg Battery Level", "—")

    if not f_health.empty and 'Health_Status' in f_health.columns:
        critical = f_health[
            f_health['Health_Status'].astype(str).str.contains(
                'critical|poor|replace', case=False, na=False)
        ].shape[0]
        c4.metric("Critical Devices", critical)
    else:
        c4.metric("Critical Devices", "—")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        df_full_data = pd.merge(df_discharge, df_level, on='Serial_Number', how='outer', suffixes=('_d', '_l'))
        df_line = df_full_data.copy()
        dc = 'Created_Date_d' 
        serial_col = 'Serial_Number' 

        # 3. Data Cleaning
        if 'Battery_Discharge_Rate' in df_line.columns:
            df_line['Discharge_Clean'] = to_numeric_pct(df_line['Battery_Discharge_Rate'])
        
        # Ensure the date column is in datetime format
        df_line[dc] = pd.to_datetime(df_line[dc])
        
        # Drop rows missing essential data
        df_line = df_line.dropna(subset=['Discharge_Clean', dc])

        # 4. Plotting
        if not df_line.empty:
            df_line = df_line.sort_values([serial_col, dc])
            df_grouped = df_line.groupby([dc, serial_col])['Discharge_Clean'].mean().reset_index()
            
            fig = px.line(
                df_grouped, 
                x=dc, 
                y='Discharge_Clean', 
                color=serial_col, 
                markers=True, 
                color_discrete_sequence=px.colors.qualitative.Dark24,
                title="Battery Discharge Rate for All Devices",
                labels={dc: 'Date', 'Discharge_Clean': 'Discharge Rate (%)', serial_col: 'Serial No.'}
            )
            
            fig.update_traces(connectgaps=True)
            apply_theme(fig, "Battery Discharge Rate for All Devices")
            st.plotly_chart(fig, use_container_width=True)

            avg_discharge = df_grouped['Discharge_Clean'].mean()
            n_devices = df_grouped['Serial_Number'].nunique()
            insight(
                f"Tracking <b>{n_devices}</b> device(s) with an average discharge rate of "
                f"<b>{avg_discharge:.1f}%</b>. Sustained high discharge rates may indicate "
                "battery wear or heavy device usage and could warrant proactive replacement planning."
            )
        else:
            st.markdown("**Battery Discharge Rate by Serial Number**")
            st.warning("No valid data found to plot. Check if dates/discharge rates are present.")

    with col2:
        df_sw = f_swap.copy()
        dc_sw = date_col(df_sw)
        if dc_sw and 'Total_Swap' in df_sw.columns:
            df_sw = df_sw.dropna(subset=['Total_Swap', dc_sw])

        if not df_sw.empty and dc_sw and 'Total_Swap' in df_sw.columns:
            total_all = df_sw['Total_Swap'].sum()
            site_tots = df_sw.groupby('Site_Name')['Total_Swap'].sum().reset_index()
            site_tots.rename(columns={'Total_Swap': 'SiteTot'}, inplace=True)
            df_sw = df_sw.merge(site_tots, on='Site_Name')
            df_sw['Site_Display'] = (
                df_sw['Site_Name'] + " (" + df_sw['SiteTot'].astype(int).astype(str) + " swaps)"
            )
            df_sw = df_sw.sort_values(['Site_Display', dc_sw])
            fig2 = px.line(
                df_sw, x=dc_sw, y='Total_Swap', color='Site_Display',
                markers=True, color_discrete_sequence=COLOR_SEQ,
                title="Battery Swaps Over Time by Site",
                labels={dc_sw: 'Date', 'Total_Swap': 'Swaps', 'Site_Display': 'Site'}
            )
            fig2.update_traces(mode='lines+markers', connectgaps=True)
            apply_theme(fig2, "Battery Swaps Over Time by Site")
            fig2.update_layout(
                annotations=[dict(
                    text=f"Total across all sites: {int(total_all):,}",
                    x=0, xref='paper', y=1.12, yref='paper',
                    showarrow=False, font=dict(size=12, color='#64748b')
                )],
                margin=dict(t=70)
            )
            st.plotly_chart(fig2, use_container_width=True)

            top_site = site_tots.sort_values('SiteTot', ascending=False).iloc[0]
            insight(
                f"A total of <b>{int(total_all):,}</b> battery swaps were recorded across all sites. "
                f"<b>{top_site['Site_Name']}</b> leads with <b>{int(top_site['SiteTot']):,}</b> swaps, "
                "suggesting it may have higher device utilization or shorter battery cycle life — "
                "worth reviewing for spare battery stock allocation."
            )
        else:
            st.markdown("**Battery Swaps Over Time by Site**")
            empty_chart()

    col3, col4 = st.columns(2)

    with col3:
        if not f_health.empty and 'Health_Status' in f_health.columns and 'Model' in f_health.columns:
            fig3 = px.sunburst(
                f_health, path=['Health_Status', 'Model'], values='Charge_Cycle_Count',
                title="Battery Health Status by Model",
                color_discrete_sequence=COLOR_SEQ
            )
            apply_theme(fig3, "Battery Health Status by Model")
            st.plotly_chart(fig3, use_container_width=True)

            if 'Health_Status' in f_health.columns:
                status_counts = f_health['Health_Status'].value_counts()
                critical_n = f_health['Health_Status'].astype(str).str.contains(
                    'critical|poor|replace', case=False, na=False).sum()
                top_status = status_counts.index[0] if not status_counts.empty else "N/A"
                insight(
                    f"Most batteries fall under <b>{top_status}</b> health status. "
                    f"<b>{int(critical_n)}</b> battery record(s) flag as critical/poor and may "
                    "need inspection or replacement to avoid unplanned downtime."
                )
        else:
            st.markdown("**Battery Health Status by Model**")
            empty_chart()

    with col4:
        dc_lv = date_col(f_level)
        if not f_level.empty and dc_lv and 'Battery_Level_Avg' in f_level.columns:
            valid_lvl = f_level.dropna(subset=['Battery_Level_Avg'])
            if not valid_lvl.empty:
                trend_lvl = (
                    valid_lvl.groupby(valid_lvl[dc_lv].dt.date)['Battery_Level_Avg']
                    .mean().reset_index()
                )
                trend_lvl.columns = ['Date', 'Avg Battery Level (%)']
                fig4 = px.area(
                    trend_lvl, x='Date', y='Avg Battery Level (%)',
                    title="Fleet Average Battery Level Trend",
                    color_discrete_sequence=['#2563eb']
                )
                apply_theme(fig4, "Fleet Average Battery Level Trend")
                st.plotly_chart(fig4, use_container_width=True)

                latest_lvl = trend_lvl.iloc[-1]['Avg Battery Level (%)']
                overall_lvl = trend_lvl['Avg Battery Level (%)'].mean()
                trend_word = "above" if latest_lvl >= overall_lvl else "below"
                insight(
                    f"The fleet's most recent average battery level is <b>{latest_lvl:.1f}%</b>, "
                    f"which is {trend_word} the period average of <b>{overall_lvl:.1f}%</b>. "
                    "Consistently low levels across the fleet may signal charging infrastructure "
                    "or scheduling issues that need attention."
                )
            else:
                st.markdown("**Fleet Average Battery Level Trend**")
                empty_chart("Battery Level values are all null — check DB column.")
        else:
            st.markdown("**Fleet Average Battery Level Trend**")
            empty_chart()

    dc_lv = date_col(f_level)
    if not f_level.empty and 'Model' in f_level.columns and 'Battery_Level_Avg' in f_level.columns:
        valid_box = f_level.dropna(subset=['Battery_Level_Avg'])
        if not valid_box.empty:
            fig_box = px.box(
                valid_box, x='Model', y='Battery_Level_Avg', color='Model',
                title="Battery Level Distribution by Model",
                color_discrete_sequence=COLOR_SEQ,
                labels={'Battery_Level_Avg': 'Battery Level (%)'}
            )
            apply_theme(fig_box, "Battery Level Distribution by Model")
            st.plotly_chart(fig_box, use_container_width=True)

            model_avgs = valid_box.groupby('Model')['Battery_Level_Avg'].mean().sort_values()
            lowest_model = model_avgs.index[0]
            highest_model = model_avgs.index[-1]
            insight(
                f"<b>{highest_model}</b> devices show the highest average battery levels "
                f"(<b>{model_avgs.iloc[-1]:.1f}%</b>), while <b>{lowest_model}</b> devices run "
                f"lowest on average (<b>{model_avgs.iloc[0]:.1f}%</b>). Wide spread within a model "
                "may indicate inconsistent charging habits across that fleet segment."
            )
        else:
            st.markdown("**Battery Level Distribution by Model**")
            empty_chart("Battery Level values are all null — check DB column.")

    dc = "Created_Date"

    if (
        not f_level.empty
        and "Battery_Level_Avg" in f_level.columns
        and "Serial_Number" in f_level.columns
        and dc in f_level.columns
    ):

        df_chart = (
            f_level[
                ["Serial_Number", dc, "Battery_Level_Avg"]
            ]
            .dropna(subset=["Battery_Level_Avg", dc])
            .copy()
        )

        df_chart = (
            df_chart.groupby(
                [dc, "Serial_Number"]
            )["Battery_Level_Avg"]
            .mean()
            .reset_index()
        )

        fig = px.line(
            df_chart,
            x=dc,
            y="Battery_Level_Avg",
            color="Serial_Number",
            markers=True,
            title="Battery Level Trend by Serial Number",
            labels={
                dc: "Date",
                "Battery_Level_Avg": "Battery Level (%)",
                "Serial_Number": "Serial Number"
            }
        )

        fig.update_traces(connectgaps=True)

        apply_theme(fig, "Battery Level Trend by Serial Number")

        st.plotly_chart(fig, use_container_width=True)

        n_serials = df_chart['Serial_Number'].nunique()
        below_threshold = (
            df_chart.groupby('Serial_Number')['Battery_Level_Avg'].mean() < 20
        ).sum()
        insight(
            f"Battery level trends are shown for <b>{n_serials}</b> device(s). "
            f"<b>{int(below_threshold)}</b> device(s) average below <b>20%</b> battery, "
            "which may need closer monitoring or earlier swap scheduling to prevent outages."
        )

    else:
        empty_chart("No battery level data available.")

    st.markdown("---")
    st.subheader("Fleet Audit Table")
    if not f_level.empty and 'Battery_Level_Avg' in f_level.columns:
        audit = (
            f_level.groupby("Serial_Number")
            .agg(
                Model=("Model","first"),
                Site_Name=("Site_Name","first"),
                Last_Updated=("Created_Date","max"),
                Avg_Battery_Level=("Battery_Level_Avg","mean")
            )
            .reset_index()
        )
        latest_date = f_level["Created_Date"].max()
        weekly_avg = (
            f_level[
                f_level["Created_Date"] >= latest_date - pd.Timedelta(days=7)
            ]
            .groupby("Serial_Number")["Battery_Level_Avg"]
            .mean()
            .reset_index()
            .rename(columns={"Battery_Level_Avg":"Weekly Avg (%)"})
        )
        monthly_avg = (
            f_level[
                f_level["Created_Date"] >= latest_date - pd.Timedelta(days=30)
            ]
            .groupby("Serial_Number")["Battery_Level_Avg"]
            .mean()
            .reset_index()
            .rename(columns={"Battery_Level_Avg":"Monthly Avg (%)"})
        )
        audit = audit.merge(weekly_avg,on="Serial_Number",how="left")
        audit = audit.merge(monthly_avg,on="Serial_Number",how="left")
        audit["Time"] = audit["Last_Updated"].dt.strftime("%H:%M:%S")
        audit["Last_Updated"] = audit["Last_Updated"].dt.strftime("%d-%m-%Y")
        audit = audit.rename(columns={"Avg_Battery_Level":"Current Avg Battery (%)"})
        try:
            display_df = audit.round(1)
        except TypeError:
            display_df = audit
        cols = ['Serial_Number', 'Model', 'Site_Name', 'Last_Updated', 'Time', 'Current Avg Battery (%)', 'Weekly Avg (%)', 'Monthly Avg (%)']
        existing_cols = [c for c in cols if c in audit.columns]
        st.dataframe(audit[existing_cols].round(1), use_container_width=True, hide_index=True)


# =============================================================================
# TAB 2 — APPLICATION ANALYTICS
# =============================================================================
with tab2:
    st.subheader("📱 Application Analytics")
    st.markdown('<p class="section-caption">App-level usage patterns, run-state distribution, and peak activity windows across the fleet.</p>', unsafe_allow_html=True)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Active Devices",
              f"{f_app['Serial_Number'].nunique():,}" if not f_app.empty else "—")
    k2.metric("Usage Events", f"{len(f_app):,}" if not f_app.empty else "—")
    k3.metric("Avg Usage / Event",
              f"{f_app['TotalUsage'].mean():.1f}" if not f_app.empty and 'TotalUsage' in f_app.columns else "—")
    k4.metric("Total Usage",
              f"{int(f_app['TotalUsage'].sum()):,}" if not f_app.empty and 'TotalUsage' in f_app.columns else "—")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        if not f_app.empty and 'Active_Status' in f_app.columns:
            df_status = f_app.copy()
            df_status['Status_Label'] = df_status['Active_Status'].map({1: 'Active', 0: 'Inactive'})
            
            status_g = df_status.groupby(['App_Name', 'Status_Label'])['TotalUsage'].count().reset_index(name='Records')
            
            fig_status = px.bar(
                status_g, x='App_Name', y='Records', color='Status_Label',
                title="📊 Application Run State Distribution",
                barmode='stack',
                color_discrete_map={'Active': '#10b981', 'Inactive': '#ef4444'},
                labels={'Records': 'Event Count', 'App_Name': 'Application', 'Status_Label': 'State'}
            )
            apply_theme(fig_status, "Application Run State Distribution")
            st.plotly_chart(fig_status, use_container_width=True)

            active_total = status_g[status_g['Status_Label'] == 'Active']['Records'].sum()
            inactive_total = status_g[status_g['Status_Label'] == 'Inactive']['Records'].sum()
            total_recs = active_total + inactive_total
            active_pct = (active_total / total_recs * 100) if total_recs else 0
            insight(
                f"<b>{active_pct:.0f}%</b> of recorded application events were in an "
                f"<b>Active</b> state (<b>{int(active_total):,}</b> of <b>{int(total_recs):,}</b>). "
                "A high inactive share for specific apps could point to underused licenses "
                "or apps that can be decommissioned."
            )
        else:
            st.markdown("**Application Run State Distribution**")
            empty_chart()

    with col2:
        if not f_app.empty and 'App_Name' in f_app.columns and 'TotalUsage' in f_app.columns:
            top_apps = (
                f_app.groupby('App_Name')['TotalUsage']
                .sum().reset_index()
                .sort_values('TotalUsage', ascending=True)
            )
            fig2 = px.bar(
                top_apps, x='TotalUsage', y='App_Name', orientation='h',
                title=f"Top Applications by Usage",
                color='TotalUsage', color_continuous_scale='Blues',
                labels={'TotalUsage': 'Total Usage', 'App_Name': 'Application'}
            )
            apply_theme(fig2, f"Top Applications by Usage")
            fig2.update_layout(coloraxis_showscale=False)
            st.plotly_chart(fig2, use_container_width=True)

            top_app_row = top_apps.sort_values('TotalUsage', ascending=False).iloc[0]
            share = (top_app_row['TotalUsage'] / top_apps['TotalUsage'].sum() * 100) if top_apps['TotalUsage'].sum() else 0
            insight(
                f"<b>{top_app_row['App_Name']}</b> is the most-used application, accounting for "
                f"<b>{share:.0f}%</b> of total usage across the fleet. This app may be critical "
                "to operations and a priority for performance monitoring."
            )
        else:
            st.markdown("**Top Applications by Usage**")
            empty_chart()

    col3, col4 = st.columns(2)

    with col3:
        if not f_app.empty and 'Site_Name' in f_app.columns and 'TotalUsage' in f_app.columns:
            site_usage = (
                f_app.groupby('Site_Name')['TotalUsage'].sum().reset_index()
                .sort_values('TotalUsage', ascending=False)
            )
            fig3 = px.bar(
                site_usage, x='Site_Name', y='TotalUsage',
                title="Application Usage by Site",
                color='Site_Name', color_discrete_sequence=COLOR_SEQ,
                labels={'TotalUsage': 'Total Usage', 'Site_Name': 'Site'}
            )
            apply_theme(fig3, "Application Usage by Site")
            fig3.update_layout(showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)

            top_site_usage = site_usage.iloc[0]
            insight(
                f"<b>{top_site_usage['Site_Name']}</b> drives the highest application usage "
                f"(<b>{int(top_site_usage['TotalUsage']):,}</b> events). Comparing this against "
                "device counts per site can help identify whether usage is proportional to "
                "fleet size or concentrated in a few locations."
            )
        else:
            st.markdown("**Application Usage by Site**")
            empty_chart()

    with col4:
        if not f_app.empty and 'Model' in f_app.columns and 'TotalUsage' in f_app.columns:
            model_usage = f_app.groupby('Model')['TotalUsage'].sum().reset_index()
            fig4 = px.pie(
                model_usage, names='Model', values='TotalUsage',
                title="Usage by Device Model",
                hole=0.4, color_discrete_sequence=COLOR_SEQ
            )
            apply_theme(fig4, "Usage by Device Model")
            st.plotly_chart(fig4, use_container_width=True)

            top_model_row = model_usage.sort_values('TotalUsage', ascending=False).iloc[0]
            model_share = (top_model_row['TotalUsage'] / model_usage['TotalUsage'].sum() * 100) if model_usage['TotalUsage'].sum() else 0
            insight(
                f"<b>{top_model_row['Model']}</b> devices generate <b>{model_share:.0f}%</b> of "
                "total application usage, highlighting which device model carries the most "
                "operational load."
            )
        else:
            st.markdown("**Usage by Device Model**")
            empty_chart()

    if not f_app.empty and 'Created_Date' in f_app.columns and 'TotalUsage' in f_app.columns:
        df_heat = f_app.copy()
        df_heat['Hour'] = df_heat['Created_Date'].dt.hour
        df_heat['Day'] = df_heat['Created_Date'].dt.day_name()
        
        # Order days chronologically
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        heatmap_data = df_heat.groupby(['Day', 'Hour'])['TotalUsage'].sum().reset_index()
        heatmap_matrix = heatmap_data.pivot(index='Day', columns='Hour', values='TotalUsage').reindex(day_order).fillna(0)
        
        fig_heat = px.imshow(
            heatmap_matrix,
            labels=dict(x="Hour of Day", y="Day of Week", color="Total Usage"),
            x=heatmap_matrix.columns,
            y=heatmap_matrix.index,
            color_continuous_scale='Blues',
            title="🎯 Peak Application Usage Times (Hourly Heatmap)"
        )
        apply_theme(fig_heat, "Peak Application Usage Times (Hourly Heatmap)")
        st.plotly_chart(fig_heat, use_container_width=True)

        peak_idx = heatmap_data['TotalUsage'].idxmax()
        peak_row = heatmap_data.loc[peak_idx]
        insight(
            f"Peak application activity occurs on <b>{peak_row['Day']}</b> around "
            f"<b>{int(peak_row['Hour'])}:00</b>. Aligning maintenance windows or device "
            "checks outside these peak hours can minimize disruption to users."
        )
    
    dc_app = date_col(f_app)
    if not f_app.empty and dc_app and 'TotalUsage' in f_app.columns:
        f_app[dc_app] = pd.to_datetime(f_app[dc_app], errors='coerce')
        f_app['Display_Time'] = f_app[dc_app].dt.floor('h')
        trend = (
            f_app.groupby('Display_Time', as_index=False)['TotalUsage']
            .sum()
            .sort_values('Display_Time')
        )
        trend.columns = ['Date & Time', 'Total Usage']
        fig = px.line(
            trend,
            x='Date & Time',
            y='Total Usage',
            markers=True,
            title="Application Usage Trend (Date & Time Wise)",
            color_discrete_sequence=['#2563eb'],
            labels={
                'Date & Time': 'Date & Time',
                'Total Usage': 'Total Usage Count'
            }
        )

        apply_theme(fig, "Application Usage Trend (Date & Time Wise)")
        st.plotly_chart(fig, use_container_width=True)

        peak_period = trend.sort_values('Total Usage', ascending=False).iloc[0]
        avg_usage = trend['Total Usage'].mean()
        insight(
            f"Application usage averages <b>{avg_usage:,.0f}</b> events per hour, with the "
            f"highest spike of <b>{int(peak_period['Total Usage']):,}</b> on "
            f"<b>{peak_period['Date & Time']:%d-%b-%Y %H:%M}</b>. Sudden spikes can indicate "
            "shift changes, batch jobs, or unusual activity worth investigating."
        )

    else:
        st.markdown("**Application Usage Trend**")
        empty_chart()

    st.markdown("---")
    st.subheader("Application Usage Detail")
    if not f_app.empty and 'App_Name' in f_app.columns and 'TotalUsage' in f_app.columns:
        latest_date = f_app["Created_Date"].max()
        app_detail = (
            f_app.groupby("App_Name")
            .agg(
                Devices=("Serial_Number","nunique"),
                Total_Usage=("TotalUsage","sum"),
                Avg_Usage=("TotalUsage","mean"),
                Last_Updated=("Created_Date","max")
            )
            .reset_index()
        )
        weekly_avg = (
            f_app[
                f_app["Created_Date"] >= latest_date - pd.Timedelta(days=7)
            ]
            .groupby("App_Name")["TotalUsage"]
            .mean()
            .reset_index()
            .rename(columns={"TotalUsage":"Weekly Avg"})
        )

        monthly_avg = (
            f_app[
                f_app["Created_Date"] >= latest_date - pd.Timedelta(days=30)
            ]
            .groupby("App_Name")["TotalUsage"]
            .mean()
            .reset_index()
            .rename(columns={"TotalUsage":"Monthly Avg"})
        )

        app_detail = (
            app_detail
            .merge(weekly_avg,on="App_Name",how="left")
            .merge(monthly_avg,on="App_Name",how="left")
        )
        app_detail["Time"] = app_detail["Last_Updated"].dt.strftime("%H:%M:%S")
        app_detail["Last_Updated"] = app_detail["Last_Updated"].dt.strftime("%d-%m-%Y")
        
        st.dataframe(app_detail, use_container_width=True, hide_index=True)
    else:
        empty_chart("No application data for selected filters.")


# =============================================================================
# TAB 3 — DEVICE MANAGEMENT
# =============================================================================
with tab3:
    st.subheader("🖥️ Device Management")
    st.markdown('<p class="section-caption">Operational status, disruption trends, and crash patterns across the registered device fleet.</p>', unsafe_allow_html=True)

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Registered Devices",
              f"{f_total['Serial_Number'].nunique():,}" if not f_total.empty else "—")

    if not f_total.empty and 'Status' in f_total.columns:
        out_of_contact = f_total[f_total['Status'].astype(str).str.lower() == 'out of contact'].shape[0]
        active = f_total[f_total['Status'].astype(str).str.lower() == 'active'].shape[0]
    else:
        out_of_contact, active = 0, 0

    d2.metric("Out Of Contact", out_of_contact)
    d3.metric("Active Devices", active)
    d4.metric("Total Disruptions",
              f"{int(f_disruption_device['Total_Disruption'].sum()):,}" if not f_disruption_device.empty and 'Total_Disruption' in f_disruption_device.columns else "—")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        if not f_total.empty and 'Status' in f_total.columns:
            fig = px.pie(
                f_total, names='Status', hole=0.4,
                title="Device Operational State",
                color_discrete_sequence=COLOR_SEQ
            )
            apply_theme(fig, "Device Operational State")
            st.plotly_chart(fig, use_container_width=True)

            status_counts = f_total['Status'].value_counts()
            total_devices = status_counts.sum()
            top_status_name = status_counts.index[0]
            top_status_pct = (status_counts.iloc[0] / total_devices * 100) if total_devices else 0
            insight(
                f"<b>{top_status_pct:.0f}%</b> of devices are currently "
                f"<b>{top_status_name}</b>. Any segment showing 'Out of Contact' or "
                "'Inactive' status should be prioritized for field follow-up to restore connectivity."
            )
        else:
            st.markdown("**Device Operational State**")
            empty_chart()

    with col2:
        dc_dis_dev = date_col(f_disruption_device)
        
        if (
            not f_disruption_device.empty 
            and dc_dis_dev 
            and 'Serial_Number' in f_disruption_device.columns 
            and 'Total_Disruption' in f_disruption_device.columns
        ):
            # 1. Clear out missing values and copy the active slice
            df_dis_trend = f_disruption_device.dropna(subset=['Total_Disruption', dc_dis_dev]).copy()
            
            # 2. Group by exact Date-Time and Serial Number to cleanly map intersections
            df_dis_trend = (
                df_dis_trend.groupby([dc_dis_dev, 'Serial_Number'])['Total_Disruption']
                .sum()
                .reset_index()
                .sort_values(by=dc_dis_dev)
            )
            
            # 3. Build the Plotly multi-line express model
            fig_dis_line = px.line(
                df_dis_trend,
                x=dc_dis_dev,
                y='Total_Disruption',
                color='Serial_Number',
                markers=True,
                title="📉 Unique Device Disruption Trend Over Time (Date & Time Wise)",
                labels={
                    dc_dis_dev: 'Date & Time',
                    'Total_Disruption': 'Disruptions Count',
                    'Serial_Number': 'Serial Number'
                },
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            
            # 4. Handle sparse timeline intervals smoothly
            fig_dis_line.update_traces(connectgaps=True)
            
            # 5. Apply your uniform dashboard template layout
            apply_theme(fig_dis_line, "Unique Device Disruption Trend Over Time (Date & Time Wise)")
            st.plotly_chart(fig_dis_line, use_container_width=True)

            total_disruptions = df_dis_trend['Total_Disruption'].sum()
            worst_device = (
                df_dis_trend.groupby('Serial_Number')['Total_Disruption'].sum()
                .sort_values(ascending=False).index[0]
            )
            insight(
                f"A total of <b>{int(total_disruptions):,}</b> disruption events were recorded "
                f"across tracked devices. Device <b>{worst_device}</b> shows the highest "
                "cumulative disruption count and may benefit from a hardware or connectivity check."
            )
        else:
            st.markdown("**Unique Device Disruption Trend Over Time**")
            empty_chart("No device-level disruption date/time markers found for selected filters.")

    col3, col4 = st.columns(2)

    with col3:
        if not f_disruption_device.empty and 'Serial_Number' in f_disruption_device.columns and 'Total_Disruption' in f_disruption_device.columns:
            top_dis = (
                f_disruption_device.groupby('Serial_Number')['Total_Disruption']
                .sum().reset_index()
                .sort_values('Total_Disruption', ascending=True)
                .tail(10)
            )
            fig3 = px.bar(
                top_dis, x='Total_Disruption', y='Serial_Number', orientation='h',
                title="Top 10 Devices by Disruptions",
                color='Total_Disruption', color_continuous_scale='Reds',
                labels={'Total_Disruption': 'Disruptions', 'Serial_Number': 'Device'}
            )
            apply_theme(fig3, "Top 10 Devices by Disruptions")
            fig3.update_layout(coloraxis_showscale=False)
            st.plotly_chart(fig3, use_container_width=True)

            worst_dev = top_dis.iloc[-1]
            insight(
                f"Device <b>{worst_dev['Serial_Number']}</b> recorded the most disruptions "
                f"(<b>{int(worst_dev['Total_Disruption']):,}</b>) among the top 10. Repeated "
                "disruptions on the same units often signal hardware faults rather than "
                "network-wide issues."
            )
        else:
            st.markdown("**Top 10 Devices by Disruptions**")
            empty_chart()

    with col4:
        if not f_disruption_device.empty and 'Site_Name' in f_disruption_device.columns and 'Total_Disruption' in f_disruption_device.columns:
            site_dis = (
                f_disruption_device.groupby('Site_Name')['Total_Disruption']
                .sum().reset_index()
                .sort_values('Total_Disruption', ascending=False)
            )
            fig4 = px.bar(
                site_dis, x='Site_Name', y='Total_Disruption',
                title="Disruptions by Site",
                color='Site_Name', color_discrete_sequence=COLOR_SEQ,
                labels={'Total_Disruption': 'Disruptions', 'Site_Name': 'Site'}
            )
            apply_theme(fig4, "Disruptions by Site")
            fig4.update_layout(showlegend=False)
            st.plotly_chart(fig4, use_container_width=True)

            top_site_dis = site_dis.iloc[0]
            insight(
                f"<b>{top_site_dis['Site_Name']}</b> has the highest disruption count "
                f"(<b>{int(top_site_dis['Total_Disruption']):,}</b>) among all sites. This site "
                "may warrant a network or infrastructure review to reduce service interruptions."
            )
        else:
            st.markdown("**Disruptions by Site**")
            empty_chart()

    if not f_disruption.empty and 'Total_Crashes' in f_disruption.columns:
        dc_dis = date_col(f_disruption)
        if dc_dis:
            crash_trend = (
                f_disruption.groupby(f_disruption[dc_dis].dt.date)['Total_Crashes']
                .sum().reset_index()
            )
            crash_trend.columns = ['Date', 'Crashes']
            fig_c = px.area(
                crash_trend, x='Date', y='Crashes',
                title="Crash Trend Over Time",
                color_discrete_sequence=['#f59e0b']
            )
            apply_theme(fig_c, "Crash Trend Over Time")
            st.plotly_chart(fig_c, use_container_width=True)

            total_crashes = crash_trend['Crashes'].sum()
            peak_crash_day = crash_trend.sort_values('Crashes', ascending=False).iloc[0]
            insight(
                f"<b>{int(total_crashes):,}</b> total crashes were recorded over the selected "
                f"period, with the highest single-day count of <b>{int(peak_crash_day['Crashes']):,}</b> "
                f"on <b>{peak_crash_day['Date']}</b>. Spikes in crashes often correlate with "
                "software updates or specific app versions and should be cross-checked with release dates."
            )

    st.markdown("---")
    st.subheader("Device Detail Table")
    if not f_total.empty:
        device_detail = (
            f_total.groupby("Serial_Number")
            .agg(
                Model=("Model","first") if "Model" in f_total.columns else None,
                Site_Name=("Site_Name","first") if "Site_Name" in f_total.columns else None,
                Status=("Status","first") if "Status" in f_total.columns else None,
                Last_Updated=("Created_Date","max") if "Created_Date" in f_total.columns else None
            )
            .reset_index()
        )
        device_detail = device_detail.dropna(axis=1, how='all')

        if "Last_Updated" in device_detail.columns:
            device_detail["Time"] = device_detail["Last_Updated"].dt.strftime("%H:%M:%S")
            device_detail["Last_Updated"] = device_detail["Last_Updated"].dt.strftime("%d-%m-%Y")

        st.dataframe(device_detail, use_container_width=True, hide_index=True)
    else:
        empty_chart("No device data for selected filters.")


# =============================================================================
# TAB 4 — STORAGE ANALYTICS
# =============================================================================
with tab4:
    st.subheader("💾 Storage & Memory Analytics")
    st.markdown('<p class="section-caption">Memory consumption trends, storage distribution by model, and out-of-contact device aging.</p>', unsafe_allow_html=True)

    s1, s2, s3, s4 = st.columns(4)

    if not f_storage.empty and 'Avg_Memory_Consumed_Percentage' in f_storage.columns:
        valid_mem = f_storage['Avg_Memory_Consumed_Percentage'].dropna()
        s1.metric("Avg Memory Usage",
                  f"{valid_mem.mean():.1f}%" if not valid_mem.empty else "—")
    else:
        s1.metric("Avg Memory Usage", "—")

    if not f_storage.empty and 'Avg_Storage_Consumed_Percentage' in f_storage.columns:
        valid_stor = f_storage['Avg_Storage_Consumed_Percentage'].dropna()
        s2.metric("Avg Storage Usage",
                  f"{valid_stor.mean():.1f}%" if not valid_stor.empty else "—")
    else:
        s2.metric("Avg Storage Usage", "—")

    s3.metric("Out Of Contact Devices",
              f"{f_ooc['Serial_Number'].nunique():,}" if not f_ooc.empty else "—")
    s4.metric("Total Records", f"{len(f_storage):,}" if not f_storage.empty else "—")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        dc_st = date_col(f_storage)
        if not f_storage.empty and dc_st and 'Avg_Memory_Consumed_Percentage' in f_storage.columns:
            valid_m = f_storage.dropna(subset=['Avg_Memory_Consumed_Percentage'])
            if not valid_m.empty:
                # Use tabs to organize Fleet Summary vs Unique Device Hourly Breakdown
                tab_fleet, tab_device = st.tabs(["📊 Fleet Summary", "📱 Hourly Unique Devices"])
                
                with tab_fleet:
                    mem_t = (
                        valid_m.groupby(valid_m[dc_st].dt.date)['Avg_Memory_Consumed_Percentage']
                        .mean().reset_index()
                    )
                    mem_t.columns = ['Date', 'Memory (%)']
                    fig = px.line(
                        mem_t, x='Date', y='Memory (%)', markers=True,
                        title="Memory Consumption Trend (Fleet)",
                        color_discrete_sequence=['#8b5cf6'],
                        labels={'Memory (%)': 'Avg Memory Usage (%)'}
                    )
                    apply_theme(fig, "Memory Consumption Trend")
                    st.plotly_chart(fig, use_container_width=True)

                    latest_mem = mem_t.iloc[-1]['Memory (%)']
                    avg_mem = mem_t['Memory (%)'].mean()
                    insight(
                        f"Fleet-wide memory usage currently averages <b>{latest_mem:.1f}%</b> "
                        f"versus a period average of <b>{avg_mem:.1f}%</b>. Memory usage "
                        "consistently above 80% across the fleet may impact device performance "
                        "and could justify a memory upgrade or app optimization review."
                    )
                
                with tab_device:
                    if 'Serial_Number' in valid_m.columns:
                        # Create a safe copy and floor the timestamps to hourly precision
                        valid_m_hourly = valid_m.copy()
                        valid_m_hourly['Hourly_Timestamp'] = pd.to_datetime(valid_m_hourly[dc_st]).dt.floor('h')
                        
                        # Aggregate memory consumption by hour and individual serial number
                        mem_hourly_df = (
                            valid_m_hourly.groupby(['Hourly_Timestamp', 'Serial_Number'])['Avg_Memory_Consumed_Percentage']
                            .mean().reset_index()
                        )
                        
                        fig_hourly = px.line(
                            mem_hourly_df,
                            x='Hourly_Timestamp',
                            y='Avg_Memory_Consumed_Percentage',
                            color='Serial_Number',
                            markers=True,
                            title="Hourly Unique Device Memory Consumption Trend",
                            labels={
                                'Hourly_Timestamp': 'Date & Time (Hourly)',
                                'Avg_Memory_Consumed_Percentage': 'Memory Usage (%)',
                                'Serial_Number': 'Device Serial'
                            },
                            color_discrete_sequence=px.colors.qualitative.Safe
                        )
                        
                        # Handle missing data gaps smoothly and preserve dashboard styles
                        fig_hourly.update_traces(connectgaps=True)
                        apply_theme(fig_hourly, "Hourly Unique Device Memory Consumption Trend")
                        st.plotly_chart(fig_hourly, use_container_width=True)

                        top_mem_device = (
                            mem_hourly_df.groupby('Serial_Number')['Avg_Memory_Consumed_Percentage']
                            .mean().sort_values(ascending=False)
                        )
                        insight(
                            f"Device <b>{top_mem_device.index[0]}</b> runs at the highest "
                            f"average memory usage (<b>{top_mem_device.iloc[0]:.1f}%</b>) "
                            "among tracked devices. Devices nearing full memory may experience "
                            "slowdowns or app crashes and could need a cache clear or storage cleanup."
                        )
                    else:
                        st.markdown("**Device Memory Consumption Trend**")
                        empty_chart("Serial_Number column not found in database schema.")
            else:
                st.markdown("**Memory Consumption Trend**")
                empty_chart("Memory % values are all null — check DB column.")
        else:
            st.markdown("**Memory Consumption Trend**")
            empty_chart()

    with col2:
        if not f_storage.empty and 'Model' in f_storage.columns and 'Avg_Memory_Consumed_Percentage' in f_storage.columns:
            valid_bx = f_storage.dropna(subset=['Avg_Memory_Consumed_Percentage'])
            if not valid_bx.empty:
                fig_box = px.box(
                    valid_bx, x='Model', y='Avg_Memory_Consumed_Percentage', color='Model',
                    title="Memory Usage Distribution by Model",
                    color_discrete_sequence=COLOR_SEQ,
                    labels={'Avg_Memory_Consumed_Percentage': 'Memory Usage (%)'}
                )
                apply_theme(fig_box, "Memory Usage Distribution by Model")
                st.plotly_chart(fig_box, use_container_width=True)

                model_mem = valid_bx.groupby('Model')['Avg_Memory_Consumed_Percentage'].mean().sort_values(ascending=False)
                insight(
                    f"<b>{model_mem.index[0]}</b> devices show the highest median memory "
                    f"consumption (avg <b>{model_mem.iloc[0]:.1f}%</b>). If this model also "
                    "shows a wide spread, some units in this segment may need closer monitoring "
                    "than others."
                )
            else:
                st.markdown("**Memory Usage Distribution by Model**")
                empty_chart("Memory % values are all null.")
        else:
            st.markdown("**Memory Usage Distribution by Model**")
            empty_chart()
    col3, col4 = st.columns(2)

    with col3:
        dc_ooc = date_col(f_ooc)
        if not f_ooc.empty and dc_ooc:
            ooc_t = (
                f_ooc.groupby(f_ooc[dc_ooc].dt.date)['Serial_Number']
                .nunique().reset_index()
            )
            ooc_t.columns = ['Date', 'OOC Devices']
            fig_ooc = px.area(
                ooc_t, x='Date', y='OOC Devices',
                title="Out-Of-Contact Devices Over Time",
                color_discrete_sequence=['#ef4444'],
                labels={'OOC Devices': 'OOC Device Count'}
            )
            apply_theme(fig_ooc, "Out-Of-Contact Devices Over Time")
            st.plotly_chart(fig_ooc, use_container_width=True)

            latest_ooc = ooc_t.iloc[-1]['OOC Devices']
            max_ooc = ooc_t['OOC Devices'].max()
            insight(
                f"There are currently <b>{int(latest_ooc):,}</b> out-of-contact device(s), "
                f"compared to a peak of <b>{int(max_ooc):,}</b> in the selected period. "
                "Rising OOC counts may indicate connectivity issues, depleted batteries, "
                "or devices that have been physically misplaced."
            )
        else:
            st.markdown("**Out-Of-Contact Devices Over Time**")
            empty_chart()

    with col4:
        if not f_ooc.empty and 'Age' in f_ooc.columns:
            ooc_clean = f_ooc.dropna(subset=['Age'])
            if not ooc_clean.empty:
                fig_age = px.histogram(
                    ooc_clean, x='Age', nbins=20,
                    title="Out-Of-Contact Device Aging",
                    color_discrete_sequence=['#f59e0b'],
                    labels={'Age': 'Device Age (days)', 'count': 'Devices'}
                )
                apply_theme(fig_age, "Out-Of-Contact Device Aging")
                st.plotly_chart(fig_age, use_container_width=True)

                avg_age = ooc_clean['Age'].mean()
                long_term_ooc = (ooc_clean['Age'] > 30).sum()
                insight(
                    f"Out-of-contact devices have been disconnected for an average of "
                    f"<b>{avg_age:.0f} days</b>. <b>{int(long_term_ooc)}</b> device(s) have "
                    "been unreachable for over 30 days and may be candidates for write-off "
                    "or asset recovery action."
                )
            else:
                st.markdown("**Out-Of-Contact Device Aging**")
                empty_chart("Age data is empty after filtering.")
        else:
            st.markdown("**Out-Of-Contact Device Aging**")
            empty_chart("'Age' column not found in OOC table.")

    # OOC Devices Over Time
    

    st.markdown("---")
    st.subheader("Storage Detail Table")
    
    if not f_storage.empty:
        # 1. Dynamically build the aggregation dictionary
        base_aggs = {}
        if "Model" in f_storage.columns: base_aggs["Model"] = ("Model", "first")
        if "Site_Name" in f_storage.columns: base_aggs["Site_Name"] = ("Site_Name", "first")
        
        # ADDED: Include Last Updated here
        if "Created_Date" in f_storage.columns: base_aggs["Last_Updated"] = ("Created_Date", "max")
        
        if "Avg_Memory_Consumed_Percentage" in f_storage.columns:
            base_aggs["Avg_Memory"] = ("Avg_Memory_Consumed_Percentage", "mean")
        if "Avg_Storage_Consumed_Percentage" in f_storage.columns:
            base_aggs["Avg_Storage"] = ("Avg_Storage_Consumed_Percentage", "mean")

        if not base_aggs:
            empty_chart("No valid columns to display.")
        else:
            storage_detail = f_storage.groupby("Serial_Number").agg(**base_aggs).reset_index()

            # 2. Add time-based averages (Weekly/Monthly)
            if "Created_Date" in f_storage.columns:
                latest_date = f_storage["Created_Date"].max()
                
                time_cols = {}
                if "Avg_Memory_Consumed_Percentage" in f_storage.columns: time_cols["Memory"] = "Avg_Memory_Consumed_Percentage"
                if "Avg_Storage_Consumed_Percentage" in f_storage.columns: time_cols["Storage"] = "Avg_Storage_Consumed_Percentage"

                if time_cols:
                    w_aggs = {f"Weekly_{k}": (v, "mean") for k, v in time_cols.items()}
                    weekly_stats = f_storage[f_storage["Created_Date"] >= latest_date - pd.Timedelta(days=7)].groupby("Serial_Number").agg(**w_aggs).reset_index()
                    
                    m_aggs = {f"Monthly_{k}": (v, "mean") for k, v in time_cols.items()}
                    monthly_stats = f_storage[f_storage["Created_Date"] >= latest_date - pd.Timedelta(days=30)].groupby("Serial_Number").agg(**m_aggs).reset_index()

                    storage_detail = storage_detail.merge(weekly_stats, on="Serial_Number", how="left")
                    storage_detail = storage_detail.merge(monthly_stats, on="Serial_Number", how="left")

                # 3. Format the Last_Updated column to Date format (DD-MM-YYYY)
                if "Last_Updated" in storage_detail.columns:
                    storage_detail["Time"] = storage_detail["Last_Updated"].dt.strftime("%H:%M:%S")
                    storage_detail["Last_Updated"] = pd.to_datetime(storage_detail["Last_Updated"]).dt.strftime("%d-%m-%Y")

            # 4. Display
            st.dataframe(
                storage_detail.round(1),
                use_container_width=True,
                hide_index=True
            )
    else:
        empty_chart("No storage data for selected filters.")