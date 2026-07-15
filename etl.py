"""
ETL: Reads the real uploaded workbook (Data_for_Assignment.xlsx) and builds a clean
SQLite database for the Executive Admissions & Marketing BI Dashboard.

Sources used (chosen because they contain the most complete, real, non-fabricated data):
  - 'Master file'  -> admissions_master  (98 real records, fully populated funnel:
                       lead source -> school -> course -> status, with geography & team)
  - 'Diploma' + 'Degree' sheets -> admissions_detail (582 real counselling records,
                       used for drop-reason analysis, TAT/turnaround-time, coach performance)

No synthetic/fabricated rows are added. Only real cells from the workbook are stored.
"""
import re
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

SRC = str(Path(__file__).parent / "source_data" / "Data_for_Assignment.xlsx")
DB = str(Path(__file__).parent / "data" / "institute.db")

# Normalize a few known typos in State names so the geo-map matches real Indian states
STATE_FIX = {
    "Maharastra": "Maharashtra",
    "Uttrakhand": "Uttarakhand",
    "Uttaranchal": "Uttarakhand",
}


def clean_state(s):
    if pd.isna(s):
        return None
    s = str(s).strip()
    return STATE_FIX.get(s, s)


def to_date(s):
    return pd.to_datetime(s, errors="coerce", dayfirst=False)


def build_master():
    df = pd.read_excel(SRC, sheet_name="Master file", header=0)
    df.columns = [c.strip() for c in df.columns]

    out = pd.DataFrame()
    out["reg_month"] = df["Month"]
    out["registration_date"] = to_date(df["Registration Date"])
    out["student_name"] = df["Student Name"].astype(str).str.strip()
    out["gender"] = df["Gender"]
    out["city"] = df["City"].astype(str).str.strip().replace({"nan": None})
    out["state"] = df["States"].apply(clean_state)
    out["admission_manager"] = df["Admission Manager"].astype(str).str.strip()
    out["team"] = df["Team"]
    out["school"] = df["School"].astype(str).str.strip()
    out["course"] = df["Course"]
    out["programme"] = df["Programe"]
    out["duration"] = df["Duration"]
    out["batch"] = df["Batch"]
    out["lead_source"] = df["Lead source"].astype(str).str.strip()
    out["admission_coach"] = df["Admission Coach"]
    out["coach_stage"] = df["Coach Stage"]
    out["coach_status"] = df["Coach Status"]
    out["coach_reason"] = df["Coach Reason"]
    out["test_taken"] = df["Test taken date"] if "Test taken date" in df.columns else None
    out["interview"] = df["Interview"]
    out["interview_date"] = to_date(df["Interview Date"])
    out["admission_letter"] = df["Admission Letter"]
    out["admission_letter_date"] = to_date(df["Admission Letter Date"])
    out["application_stage"] = df["Application stage"]
    out["total_fee"] = pd.to_numeric(df["Total Fee"], errors="coerce")
    out["fee_outstanding"] = pd.to_numeric(df["Fee o/s"], errors="coerce")
    out["confirmation_date"] = to_date(df["Confiirmation Date"])
    out["days_in_pipeline"] = pd.to_numeric(df["Days"], errors="coerce")
    out["bucket"] = df["Bucket"]
    out["status"] = df["Status"].astype(str).str.strip().replace({"nan": None})

    out = out.reset_index(drop=True)
    out.insert(0, "id", range(1, len(out) + 1))
    return out


def build_detail():
    frames = []
    for sheet, ptype in [("Diploma", "Diploma"), ("Degree", "Degree")]:
        df = pd.read_excel(SRC, sheet_name=sheet, header=2)
        df.columns = [str(c).strip() for c in df.columns]
        # Only keep rows that actually have a student name (real records)
        df = df[df["Student Name"].notna()].copy()

        sub = pd.DataFrame()
        sub["programme_type"] = ptype
        sub["admission_coach"] = df["Admission Coach"]
        sub["calling_date"] = to_date(df["Calling Date"])
        sub["status"] = df["Status"].astype(str).str.strip().replace({"nan": None})
        sub["reason"] = df["Reason"]
        sub["registration_date"] = to_date(df["Registration Date"])
        sub["file_collected_date"] = to_date(df["File Collected Date"])
        sub["tat_days"] = pd.to_numeric(df["TAT"], errors="coerce")
        sub["student_name"] = df["Student Name"]
        sub["qualification"] = df["Qualification"]
        sub["gender"] = df["Gender"]
        sub["city"] = df["City"].astype(str).str.strip().replace({"nan": None})
        sub["state"] = df["States"].apply(clean_state)
        sub["admission_manager"] = df["Admission Manager"]
        sub["team"] = df["Team"]
        sub["school"] = df["School"].astype(str).str.strip().replace({"nan": None})
        sub["course"] = df["Course"]
        sub["programme"] = df["Programe"]
        sub["duration"] = df["Duration"]
        sub["batch"] = df["Batch"]
        sub["sales_joined"] = df["Sales Joined"] if "Sales Joined" in df.columns else None
        sub["academic_joined"] = df["Academic Joined"] if "Academic Joined" in df.columns else None
        frames.append(sub)

    out = pd.concat(frames, ignore_index=True)
    out.insert(0, "id", range(1, len(out) + 1))
    return out


def main():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    master = build_master()
    detail = build_detail()

    # SQLite can't store native datetimes; store as ISO strings
    for col in master.columns:
        if pd.api.types.is_datetime64_any_dtype(master[col]):
            master[col] = master[col].dt.strftime("%Y-%m-%d")
    for col in detail.columns:
        if pd.api.types.is_datetime64_any_dtype(detail[col]):
            detail[col] = detail[col].dt.strftime("%Y-%m-%d")

    master = master.replace({np.nan: None})
    detail = detail.replace({np.nan: None})

    conn = sqlite3.connect(DB)
    master.to_sql("admissions_master", conn, if_exists="replace", index=False)
    detail.to_sql("admissions_detail", conn, if_exists="replace", index=False)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_master_school ON admissions_master(school)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_master_state ON admissions_master(state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_master_status ON admissions_master(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_master_source ON admissions_master(lead_source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_detail_school ON admissions_detail(school)")
    conn.commit()

    print(f"Loaded admissions_master: {len(master)} rows")
    print(f"Loaded admissions_detail: {len(detail)} rows")
    print(f"DB written to: {DB}")
    conn.close()


if __name__ == "__main__":
    main()
