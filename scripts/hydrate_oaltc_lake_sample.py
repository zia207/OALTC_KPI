#!/usr/bin/env python3
"""
Load notebook-compatible sample rows into BigQuery (`oaltc_dim` / `oaltc_raw`).

Requires Application Default Credentials (or GOOGLE_APPLICATION_CREDENTIALS).
Run DDL first: bigquery/bootstrap_oaltc_lake.sql

Uses WRITE_TRUNCATE on each target table (idempotent re-run).

Usage:
  export GOOGLE_CLOUD_PROJECT=oaltc-kpi-project-7748   # optional if --project passed
  python scripts/hydrate_oaltc_lake_sample.py
  python scripts/hydrate_oaltc_lake_sample.py --seed 42 --project my-gcp-project
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from google.cloud import bigquery


def synthetic_facility_master_df(rng: np.random.Generator) -> pd.DataFrame:
    regions = [
        "Western NY",
        "Central NY",
        "Capital Region",
        "NYC Metro",
        "Long Island",
        "North Country",
    ]
    facility_types = ["Skilled Nursing Facility", "Nursing Home", "CCRC"]
    ownership = ["Not-for-profit", "For-profit", "Government"]
    city_pools = {
        "Western NY": ["Buffalo", "Niagara Falls", "Lockport", "Batavia", "Olean"],
        "Central NY": ["Syracuse", "Utica", "Rome", "Auburn", "Cortland"],
        "Capital Region": ["Albany", "Troy", "Schenectady", "Saratoga Springs", "Glens Falls"],
        "NYC Metro": ["Bronx", "Brooklyn", "Queens", "Manhattan", "Staten Island"],
        "Long Island": ["Hempstead", "Babylon", "Huntington", "Oyster Bay", "Islip"],
        "North Country": ["Watertown", "Plattsburgh", "Ogdensburg", "Malone", "Canton"],
    }
    facilities = []
    for i in range(50):
        reg = regions[i % len(regions)]
        city = city_pools[reg][i % 5]
        facilities.append(
            {
                "facility_id": f"NH-{i + 1:03d}",
                "facility_name": f"{city} Care Center {i // 6 + 1}",
                "region": reg,
                "facility_type": rng.choice(facility_types),
                "ownership": rng.choice(ownership),
                "licensed_beds": int(rng.integers(60, 200)),
                "county": city,
                "zip_code": str(f"1{rng.integers(1000, 9999)}"),
            }
        )
    return pd.DataFrame(facilities)


def synthetic_discharge_events(df_facilities: pd.DataFrame, rng: np.random.Generator, n_months: int = 13) -> pd.DataFrame:
    records = []
    end_date = datetime(2026, 5, 1)
    start_date = end_date - timedelta(days=30 * n_months)
    for _, fac in df_facilities.iterrows():
        base_readmit = rng.uniform(0.10, 0.28)
        base_ulcer = rng.uniform(0.001, 0.007)
        base_adl_score = rng.uniform(6, 18)
        monthly_discharges = int(rng.integers(15, 60))
        current = start_date
        while current < end_date:
            for _ in range(monthly_discharges):
                admit_date = current - timedelta(days=int(rng.integers(5, 90)))
                discharge_date = current + timedelta(days=int(rng.integers(0, 28)))
                readmitted = rng.random() < base_readmit
                dq_issue = rng.random() < 0.05
                bad_admit = dq_issue and rng.random() < 0.3
                records.append(
                    {
                        "facility_id": fac["facility_id"],
                        "resident_id": f"RES-{rng.integers(100000, 999999)}",
                        "admit_date": None
                        if bad_admit
                        else pd.Timestamp(admit_date).normalize(),
                        "discharge_date": pd.Timestamp(discharge_date).normalize(),
                        "report_year": current.year,
                        "report_month": current.month,
                        "readmitted_30d": readmitted,
                        "new_pressure_ulcer": rng.random() < base_ulcer,
                        "adl_score": round(float(base_adl_score + rng.normal(0, 2)), 1)
                        if not (dq_issue and rng.random() < 0.2)
                        else np.nan,
                        "outcome_code": rng.choice(["01", "02", "03", "04", "05"])
                        if not (dq_issue and rng.random() < 0.15)
                        else None,
                        "payer_type": rng.choice(
                            ["Medicaid", "Medicare", "Private", "Other"],
                            p=[0.55, 0.25, 0.15, 0.05],
                        ),
                        "race_ethnicity": rng.choice(
                            ["White", "Black", "Hispanic", "Asian", "Other"],
                            p=[0.55, 0.20, 0.15, 0.06, 0.04],
                        ),
                        "data_quality_flag": "FAIL" if dq_issue else "PASS",
                        "submission_date": pd.Timestamp(
                            current + timedelta(days=int(rng.integers(1, 15)))
                        ).normalize(),
                    }
                )
            current = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
    return pd.DataFrame(records)


def synthetic_workforce(df_facilities: pd.DataFrame, rng: np.random.Generator, n_quarters: int = 6) -> pd.DataFrame:
    records = []
    quarters = [(2025, 1), (2025, 2), (2025, 3), (2025, 4), (2026, 1), (2026, 2)][:n_quarters]
    for _, fac in df_facilities.iterrows():
        base_turnover = rng.uniform(0.15, 0.65)
        for yr, qtr in quarters:
            avg_headcount = int(rng.integers(40, 180))
            separations = int(avg_headcount * base_turnover / 4 * rng.uniform(0.7, 1.3))
            dq_issue = rng.random() < 0.04
            records.append(
                {
                    "facility_id": fac["facility_id"],
                    "report_year": yr,
                    "report_quarter": qtr,
                    "avg_staff_headcount": float(avg_headcount) if not dq_issue else np.nan,
                    "staff_separations": separations,
                    "rn_hours_per_day": round(float(rng.uniform(0.3, 1.8)), 2),
                    "vacancy_rate_pct": round(float(rng.uniform(2, 25)), 1),
                    "data_quality_flag": "FAIL" if dq_issue else "PASS",
                }
            )
    return pd.DataFrame(records)


def synthetic_complaints(df_facilities: pd.DataFrame, rng: np.random.Generator, n_months: int = 13) -> pd.DataFrame:
    records = []
    for _, fac in df_facilities.iterrows():
        base_rate = rng.uniform(0.6, 1.5)
        for month_offset in range(n_months):
            dt = datetime(2025, 4, 1) + timedelta(days=30 * month_offset)
            n = max(0, int(rng.poisson(base_rate)))
            for _ in range(n):
                resolved_days = int(
                    rng.choice(
                        [rng.integers(1, 10), rng.integers(10, 30)],
                        p=[0.78, 0.22],
                    )
                )
                records.append(
                    {
                        "facility_id": fac["facility_id"],
                        "report_year": dt.year,
                        "report_month": dt.month,
                        "complaint_id": f"CMP-{rng.integers(100000, 999999)}",
                        "days_to_resolution": resolved_days,
                        "complaint_type": rng.choice(
                            ["Quality of Care", "Abuse/Neglect", "Environment", "Staffing", "Other"]
                        ),
                        "data_quality_flag": "PASS",
                    }
                )
    return pd.DataFrame(records)


def _load_df(
    client: bigquery.Client,
    df: pd.DataFrame,
    table_id: str,
) -> None:
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    print(f"  loaded {len(df):,} rows -> {table_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Hydrate OALTC BigQuery lake with sample data.")
    parser.add_argument(
        "--project",
        default=(
            (os.environ.get("OALTC_BQ_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "").strip()
            or "oaltc-kpi-project-7748"
        ),
        help="GCP project id (defaults to OALTC_BQ_PROJECT, GOOGLE_CLOUD_PROJECT, or oaltc-kpi-project-7748)",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible sample data")
    parser.add_argument(
        "--dataset-dim",
        default=os.environ.get("OALTC_BQ_DATASET_DIM", "oaltc_dim").strip(),
    )
    parser.add_argument(
        "--dataset-raw",
        default=os.environ.get("OALTC_BQ_DATASET_RAW", "oaltc_raw").strip(),
    )
    args = parser.parse_args()
    project = args.project.strip()
    if not project:
        print("No GCP project: set --project or GOOGLE_CLOUD_PROJECT", file=sys.stderr)
        return 1

    rng = np.random.default_rng(args.seed)
    df_fac = synthetic_facility_master_df(rng)
    df_dis = synthetic_discharge_events(df_fac, rng)
    df_wf = synthetic_workforce(df_fac, rng)
    df_cmp = synthetic_complaints(df_fac, rng)

    client = bigquery.Client(project=project)
    print(f"BigQuery project: {client.project}")
    print("Uploading (WRITE_TRUNCATE)...")

    _load_df(client, df_fac, f"{project}.{args.dataset_dim}.nh_facility_master")
    _load_df(client, df_dis, f"{project}.{args.dataset_raw}.nh_discharge_events")
    _load_df(client, df_wf, f"{project}.{args.dataset_raw}.workforce_quarterly")
    _load_df(client, df_cmp, f"{project}.{args.dataset_raw}.complaint_investigations")

    print("Done. Unset OALTC_USE_LOCAL_MOCK and re-run the notebook Section 3.1 cells.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
