"""
Generate fully synthetic sample data for the Visibility IQ dashboard.

All names, serial numbers, IDs and values are randomly generated.
No real company, customer or device data is used.

Usage:
    python generate_mock_data.py            # writes CSVs into ./sample_data
    python generate_mock_data.py --devices 120 --days 45
"""
import argparse
import os
import random
import string

import numpy as np
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--devices", type=int, default=60)
parser.add_argument("--days", type=int, default=30)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--out", default="sample_data")
args = parser.parse_args()

rng = np.random.default_rng(args.seed)
random.seed(args.seed)
os.makedirs(args.out, exist_ok=True)

# ----------------------------------------------------------------------------
# Fake master data
# ----------------------------------------------------------------------------
SITES = ["DEMO RETAIL - MUMBAI HUB", "DEMO RETAIL - PUNE DC", "DEMO RETAIL - DELHI STORE"]
MODELS = {
    "MX100W": "MX100B-2S1P9B21-A6",
    "MX100L": "MX100B-2S1M9B22-A6",
    "MX200":  "MX200C-3S2P9B31-B2",
}
BSPS = ["15.15.30.00", "15.16.15.00", "14.10.20.00"]
OS_VERSIONS = ["13", "14", "15"]
APPS = [
    ("DataWedge", "Utility"), ("Demo Scanner", "Productivity"), ("Demo Showcase", "Utility"),
    ("Settings", "System"), ("Launcher", "System"), ("Demo Store App", "Productivity"),
]

start = pd.Timestamp("2026-04-01")
days = pd.date_range(start, periods=args.days, freq="D")
event_ids = {d: "".join(random.choices("0123456789abcdef", k=16)) for d in days}


def fake_serial():
    return "DM" + "".join(random.choices(string.digits, k=6)) + random.choice("ABCDE") + "".join(random.choices(string.digits, k=4))


def ts(day, hour=None):
    h = random.randint(0, 23) if hour is None else hour
    return (day + pd.Timedelta(hours=h, minutes=random.randint(0, 59), seconds=random.randint(0, 59))
            ).strftime("%Y-%m-%d %H:%M:%S.000")


def pct(x, nd=2):
    return f"{x:.{nd}f}%"


devices = []
for _ in range(args.devices):
    model = random.choices(list(MODELS), weights=[5, 3, 2])[0]
    devices.append(dict(
        serial=fake_serial(), model=model, full_model=MODELS[model],
        site=random.choice(SITES), os=random.choice(OS_VERSIONS), bsp=random.choice(BSPS),
        base_batt=rng.uniform(45, 95), drain=rng.uniform(1, 8),
        health=rng.uniform(55, 100), flaky=rng.random() < 0.15,
        mem_total=random.choice([30000.0, 45067.8, 60000.0]),
    ))

# Make a few devices clearly "bad" so the dashboard shows interesting outliers
for d in random.sample(devices, max(3, args.devices // 12)):
    d["health"] = rng.uniform(25, 50)
    d["flaky"] = True


def save(name, rows):
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(args.out, f"{name}.csv"), index=False)
    print(f"{name}.csv: {len(df)} rows")


# ----------------------------------------------------------------------------
# 1. Total_Device_Master
# ----------------------------------------------------------------------------
rows = []
for i, d in enumerate(devices, 1):
    rows.append({
        "Total_Device_Id": i, "Event_Unique_Id": event_ids[days[-1]], "Site_Hierarchy": "NOT_AVAILABLE",
        "Asset_Name": d["model"], "Serial_Number": d["serial"], "Full_Model": d["full_model"],
        "Site_Name": d["site"], "Model": d["model"], "Device_Type": "MOBILE COMPUTER",
        "Status": "In Operation", "BSSID": "N/A", "Phone_Number": "N/A", "IP_Address": "N/A",
        "GPS_Coordinates": "N/A", "OS": d["os"], "Contract_Id": "90000001",
        "IMEI": "".join(random.choices(string.digits, k=15)), "Network_Connection_Type": "WIFI",
        "LGVersion": "U00",
        "MAC_Address": ":".join(f"{random.randint(0, 255):02X}" for _ in range(6)),
        "Created_Date": ts(days[-1]), "Active_Status": 0, "Modify_Date": None,
    })
save("Total_Device_Master", rows)

# ----------------------------------------------------------------------------
# 2. Battery_Level_Master  (one reading per device per day)
# ----------------------------------------------------------------------------
rows, n = [], 1
for day in days:
    for d in devices:
        level = np.clip(d["base_batt"] + rng.normal(0, 8), 5, 100)
        rows.append({
            "Battery_Level_Id": n, "Event_Unique_ID": event_ids[day], "Serial_Number": d["serial"],
            "Asset_Name": d["model"], "Device_Type": "MOBILE COMPUTER", "Model": d["model"], "OS": d["os"],
            "Site_Name": d["site"], "Site_Hierarchy": "NOT_AVAILABLE", "Battery_Level_Avg": pct(level),
            "Created_Date": ts(day), "Active_Status": 0, "Modify_Date": None,
        })
        n += 1
save("Battery_Level_Master", rows)

# ----------------------------------------------------------------------------
# 3. Battery_Swap_Activity_Master
# ----------------------------------------------------------------------------
rows, n = [], 1
for day in days:
    for d in devices:
        if rng.random() < 0.35:
            rows.append({
                "Battery_Swap_Activity_Id": n, "Event_Unique_ID": event_ids[day], "Serial_Number": d["serial"],
                "Device_Name": d["model"], "Device_Type": "MOBILE COMPUTER", "Model": d["model"],
                "Total_Swap": int(rng.integers(1, 5)), "Site_Name": d["site"],
                "Site_Hierarchy": "NOT_AVAILABLE", "Company_ID": 1, "Created_Date": ts(day),
                "Active_Status": 0, "Modify_Date": None,
            })
            n += 1
save("Battery_Swap_Activity_Master", rows)

# ----------------------------------------------------------------------------
# 4. Battery_Discharge_Rate_Master
# ----------------------------------------------------------------------------
rows, n = [], 1
for day in days:
    for d in random.sample(devices, k=max(5, len(devices) // 3)):
        rate = np.clip(d["drain"] + rng.normal(0, 1.2), 0.5, 15)
        rows.append({
            "Battery_Discharge_ID": n, "Event_Unique_ID": event_ids[day], "Asset_Name": d["model"],
            "Battery_Discharge_Rate": pct(rate, 1).replace(".0%", "%"), "Device_Type": "MOBILE COMPUTER",
            "Model": d["model"], "OS": d["os"], "Serial_Number": d["serial"], "Site_Name": d["site"],
            "Created_Date": ts(day), "Active_Status": 0, "Modify_Date": None,
        })
        n += 1
save("Battery_Discharge_Rate_Master", rows)

# ----------------------------------------------------------------------------
# 5. Smart_Battery_Health_Master
# ----------------------------------------------------------------------------
rows, n = [], 1
for day in days[::3]:
    for d in devices:
        h = np.clip(d["health"] + rng.normal(0, 3), 10, 100)
        if h < 40:
            status, reason = "Critical Battery", "Health below replacement threshold"
        elif h < 60:
            status, reason = "Replace Soon", "Health trending toward threshold"
        elif d["flaky"] and rng.random() < 0.3:
            status, reason = "Investigate Data Transmission", "Undefined transmission issue"
        else:
            status, reason = "Good Battery", "Within normal range"
        rows.append({
            "Smart_Battery_Health_ID": n, "Event_Unique_Id": event_ids[day], "Health_Percent": round(h, 1),
            "Battery_PartNumber": "BT-DEMO-0001", "Model": d["model"], "Last_Seen_Datetime": ts(day),
            "Rul": int(max(0, (h - 30) * 6)), "Battery_Type": "PP",
            "Battery_Serial_Number": "B" + "".join(random.choices(string.digits, k=5)),
            "Battery_Manufacture_Date": (day - pd.Timedelta(days=int(rng.integers(60, 700)))).strftime("%Y-%m-%d"),
            "Last_Seen_SiteName": d["site"], "Is_Decommissioned": "N", "Health_Status": status,
            "Reason_For_Status": reason, "State": random.choices(["ACTIVE", "OOC"], weights=[7, 3])[0],
            "Charge_Cycle_Count": int(np.clip((100 - h) * 9 + rng.normal(0, 30), 1, 900)),
            "Serial_Number": d["serial"], "Status": "IN USE", "Device_Type": "MOBILE COMPUTER",
            "Created_Date": ts(day), "Active_Status": 0,
        })
        n += 1
save("Smart_Battery_Health_Master", rows)

# ----------------------------------------------------------------------------
# 6. Application_Analytics_Device_Usage_Master
# ----------------------------------------------------------------------------
rows, n = [], 1
for day in days:
    for d in random.sample(devices, k=max(5, len(devices) // 4)):
        app, _ = random.choice(APPS)
        rows.append({
            "Application_Analytics_Device_Usage_ID": n, "Event_Unique_Id": event_ids[day],
            "Application_Analytics_Usages_Id": n, "App_Name": app, "Site_Name": d["site"],
            "Model": d["model"], "TotalUsage": int(rng.integers(20, 5000)), "Serial_Number": d["serial"],
            "Site_Hierarchy": "NOT_AVAILABLE", "Created_Date": ts(day), "Active_Status": 0,
        })
        n += 1
save("Application_Analytics_Device_Usage_Master", rows)

# ----------------------------------------------------------------------------
# 7. Device_Disruption_Master  (daily fleet totals)
# ----------------------------------------------------------------------------
rows = []
for i, day in enumerate(days, 1):
    anrs, sysr, usr = int(rng.poisson(6)), int(rng.poisson(3)), int(rng.poisson(10))
    rows.append({
        "Device_Disruption_Id": i, "Event_Unique_Id": event_ids[day], "Date": day.strftime("%Y-%m-%d"),
        "Total_Anrs": anrs, "Anr_Device_Count": min(anrs, args.devices),
        "Total_System_Reboots": sysr, "System_Reboot_Device_Count": min(sysr, args.devices),
        "Total_User_Reboots": usr, "User_Reboot_Device_Count": min(usr, args.devices),
        "User_Reboots_Normalized_Rate": round(usr / args.devices, 3),
        "System_Reboots_Normalized_Rate": round(sysr / args.devices, 3),
        "Anrs_Normalized_Rate": round(anrs / args.devices, 3),
        "Total_Crashes": int(rng.poisson(2)), "Created_Date": ts(day), "Active_Status": 0,
    })
save("Device_Disruption_Master", rows)

# ----------------------------------------------------------------------------
# 8. Device_Disruption_Device_Master  (per device per week)
# ----------------------------------------------------------------------------
rows, n = [], 1
for day in days[::7]:
    for d in devices:
        mult = 3 if d["flaky"] else 1
        sysr, usr, anrs = int(rng.poisson(1 * mult)), int(rng.poisson(2)), int(rng.poisson(1 * mult))
        rows.append({
            "Device_Disruption_Device_Id": n, "Event_Unique_ID": event_ids[day], "Serial_Number": d["serial"],
            "Asset_Name": d["model"], "Model": d["model"], "OS": d["os"],
            "Total_Disruption": sysr + usr + anrs, "Total_Reboots": sysr + usr,
            "User_Initiated_Reboots": usr, "System_Initiated_Reboots": sysr, "Total_ANRS": anrs,
            "Site_Name": d["site"], "Site_Hierarchy": "NOT_AVAILABLE", "Created_Date": ts(day),
            "Active_Status": 0,
        })
        n += 1
save("Device_Disruption_Device_Master", rows)

# ----------------------------------------------------------------------------
# 9. Storage_Memory_Utilization_Master
# ----------------------------------------------------------------------------
rows, n = [], 1
for day in days[::2]:
    for d in random.sample(devices, k=max(5, len(devices) // 2)):
        avg_pct = float(np.clip(rng.normal(35 if not d["flaky"] else 70, 12), 8, 98))
        max_pct = min(100.0, avg_pct + rng.uniform(0, 12))
        tot = d["mem_total"]
        rows.append({
            "Storage_Memory_Utilization_ID": n, "Event_Unique_Id": event_ids[day], "Serial_Number": d["serial"],
            "Asset_Name": d["model"], "Model": d["model"], "Full_Model": d["full_model"], "OS": d["os"],
            "BSP": d["bsp"], "Impacted_Days": int(avg_pct > 75) * int(rng.integers(1, 6)),
            "Total_Memory": tot, "Avg_Memory_Consumed": round(tot * avg_pct / 100, 1),
            "Avg_Memory_Consumed_Percentage": pct(avg_pct), "Max_Memory_Consumed": round(tot * max_pct / 100, 1),
            "Max_Memory_Consumed_Percentage": pct(max_pct), "Site_Name": d["site"],
            "Site_Hierarchy": "NOT_AVAILABLE", "Created_Date": ts(day), "Active_Status": 0,
        })
        n += 1
save("Storage_Memory_Utilization_Master", rows)

# ----------------------------------------------------------------------------
# 10. Out_Of_Contanct_Device_Master  (table name spelling kept as in the schema)
# ----------------------------------------------------------------------------
rows, n = [], 1
ooc_devices = random.sample(devices, k=max(5, len(devices) // 4))
for day in days[::2]:
    for d in ooc_devices:
        if rng.random() < 0.6:
            rows.append({
                "Out_Of_Contanct_Device_ID": n, "Event_Unique_ID": event_ids[day],
                "Last_Seen_Datetime": ts(day - pd.Timedelta(days=int(rng.integers(1, 9)))),
                "Access_Point_Name": "No Entry", "OS": d["os"], "Full_Model": d["full_model"], "BSSID": "N/A",
                "ManuFacture_Date": None, "In_Operation_Status": "Out of Contact", "Device_Type": "MOBILE COMPUTER",
                "Site_Hierarchy": "NOT_AVAILABLE", "Asset_Name": d["model"], "Serial_Number": d["serial"],
                "Site_Name": d["site"], "Last_Wlan_Connect_Datetime": None, "Model": d["model"], "BSP": d["bsp"],
                "Age": int(rng.integers(1, 15)), "Status": "In Operation", "Active_Status": 0,
                "Created_Date": ts(day),
            })
            n += 1
save("Out_Of_Contanct_Device_Master", rows)

print(f"\nDone. Synthetic data written to ./{args.out}/")
