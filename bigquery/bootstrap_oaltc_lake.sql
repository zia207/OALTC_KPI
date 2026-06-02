-- =============================================================================
-- OALTC KPI notebook — BigQuery lake bootstrap (dimension + raw datasets)
-- =============================================================================
-- Run as one script in the BigQuery UI (ensure "Allow multiple statements"),
-- or: bq query --use_legacy_sql=false < bigquery/bootstrap_oaltc_lake.sql
--
-- Edit the project prefix if yours is not oaltc-kpi-project-7748.
-- Use location **US** to match default BigQuery processing in the notebook unless
-- you configure client location to match elsewhere.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS `oaltc-kpi-project-7748.oaltc_dim`
OPTIONS (
  location = 'US',
  description = 'OALTC dimension tables (facility master, etc.)'
);

CREATE TABLE IF NOT EXISTS `oaltc-kpi-project-7748.oaltc_dim.nh_facility_master` (
  facility_id STRING NOT NULL,
  facility_name STRING,
  region STRING,
  facility_type STRING,
  ownership STRING,
  licensed_beds INT64,
  county STRING,
  zip_code STRING
);

CREATE SCHEMA IF NOT EXISTS `oaltc-kpi-project-7748.oaltc_raw`
OPTIONS (
  location = 'US',
  description = 'OALTC raw / lake submissions (events, workforce, complaints)'
);

CREATE TABLE IF NOT EXISTS `oaltc-kpi-project-7748.oaltc_raw.nh_discharge_events` (
  facility_id STRING NOT NULL,
  resident_id STRING,
  admit_date DATE,
  discharge_date DATE,
  report_year INT64,
  report_month INT64,
  readmitted_30d BOOL,
  new_pressure_ulcer BOOL,
  adl_score FLOAT64,
  outcome_code STRING,
  payer_type STRING,
  race_ethnicity STRING,
  data_quality_flag STRING,
  submission_date DATE
);

CREATE TABLE IF NOT EXISTS `oaltc-kpi-project-7748.oaltc_raw.workforce_quarterly` (
  facility_id STRING NOT NULL,
  report_year INT64,
  report_quarter INT64,
  avg_staff_headcount FLOAT64,
  staff_separations INT64,
  rn_hours_per_day FLOAT64,
  vacancy_rate_pct FLOAT64,
  data_quality_flag STRING
);

CREATE TABLE IF NOT EXISTS `oaltc-kpi-project-7748.oaltc_raw.complaint_investigations` (
  facility_id STRING NOT NULL,
  report_year INT64,
  report_month INT64,
  complaint_id STRING,
  days_to_resolution INT64,
  complaint_type STRING,
  data_quality_flag STRING
);

-- Tables are created empty. Load production data via your ETL pipelines,
-- or populate demo rows compatible with Section 3.1 queries:
--   python scripts/hydrate_oaltc_lake_sample.py
-- Offline-only notebooks: export OALTC_USE_LOCAL_MOCK=1
