# 📡 Visibility IQ — Fleet Intelligence Dashboard

A Streamlit dashboard for monitoring the health and performance of a managed mobile-device fleet — battery health, battery swaps, application usage, device disruptions (ANRs and reboots), storage and memory pressure, and out-of-contact devices.

It was built as part of a **Data Analyst internship project** and was designed to run against a live Microsoft SQL Server database.

> ⚠️ **Data notice:** This repository contains the application code only. No credentials and no real company, customer, or device data are included. The `sample_data/` folder is **100% synthetic**, produced by `generate_mock_data.py`, so you can run the full dashboard without any database.

---

## ✨ Features

**Four analytics tabs**

| Tab | What it shows |
|---|---|
| 🔋 **Battery Analytics** | Average battery level, battery swap activity by site, discharge rates, smart-battery health status and charge-cycle counts, critical-battery count |
| 📱 **Application Analytics** | App usage by application, site and device model, usage events over time |
| 🖥️ **Device Management** | Device inventory, disruptions (ANRs, system/user reboots, crashes), out-of-contact devices and their age, fleet and hourly unique-device views |
| 💾 **Storage Analytics** | Average / peak memory consumption by device and model, high-utilisation devices |

**Platform features**
- Sidebar filters: organisation, site / plant, device type (model), and date range
- Live SQL Server connection (`pyodbc` + `SQLAlchemy`) with 5-minute query caching
- **Automatic CSV fallback** if the database is unreachable
- **Demo mode** (`--mock`) that runs entirely on synthetic CSVs
- Auto-generated summary reports every 15 minutes, plus a one-click report download
- Plain-English "insight" callouts under the charts

---

## 🧰 Tech Stack

Python · Streamlit · Plotly · Pandas · SQLAlchemy · pyodbc · Microsoft SQL Server

---

## 🏗️ Architecture

```
Microsoft SQL Server  ──(pyodbc / SQLAlchemy)──┐
                                               ├──►  Pandas cleaning & KPIs  ──►  Streamlit + Plotly UI
sample_data/*.csv (demo / fallback)  ──────────┘
```

The app reads 10 tables:
`Battery_Level_Master`, `Battery_Swap_Activity_Master`, `Battery_Discharge_Rate_Master`, `Smart_Battery_Health_Master`, `Application_Analytics_Device_Usage_Master`, `Total_Device_Master`, `Device_Disruption_Master`, `Device_Disruption_Device_Master`, `Storage_Memory_Utilization_Master`, `Out_Of_Contanct_Device_Master` *(spelling matches the source schema)*.

---

## ▶️ Quick Start — Demo Mode (no database needed)

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/visibility-iq-dashboard.git
cd visibility-iq-dashboard

# 2. (Optional) create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run with synthetic data
streamlit run dashboard.py -- --mock
```

> Note the extra `--` before `--mock`: it passes the flag to the app rather than to Streamlit.
> Alternatively set an environment variable: `VIQ_MOCK=1 streamlit run dashboard.py`
> (Windows PowerShell: `$env:VIQ_MOCK=1; streamlit run dashboard.py`)

### Regenerate or resize the sample data

```bash
python generate_mock_data.py                       # 60 devices, 30 days (default)
python generate_mock_data.py --devices 150 --days 60 --seed 7
```

---

## 🔌 Connecting Your Own SQL Server

1. Install the [Microsoft ODBC Driver 17 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server) and then `pip install pyodbc`.
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in your values:
   ```toml
   DB_SERVER = "your_server_ip"
   DB_NAME = "your_database"
   DB_USER = "your_username"
   DB_PASSWORD = "your_password"
   ```
3. Make sure your database has the 10 tables listed above (column layouts match the CSVs in `sample_data/`).
4. Run `streamlit run dashboard.py`.

`secrets.toml` is git-ignored — **never commit it.**

---

## 📁 Project Structure

```
visibility-iq-dashboard/
├── dashboard.py                  # Streamlit app (live DB, CSV fallback, demo mode)
├── generate_mock_data.py         # Builds the synthetic sample data
├── sample_data/                  # 10 synthetic CSVs (one per table)
├── .streamlit/
│   └── secrets.toml.example      # Credential template (copy to secrets.toml)
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 💡 Impact (from the internship deployment)

- Replaced manual daily Excel reporting with a live dashboard
- Surfaced at-risk batteries and devices earlier, supporting proactive maintenance
- Optimised the SQL queries behind the dashboard to cut refresh time
- Used by operations stakeholders for fleet reviews



## 👤 Author

**Yash Solanki** — Data Analyst
[LinkedIn](https://www.linkedin.com/in/solanki-yash)
