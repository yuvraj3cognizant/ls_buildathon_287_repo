"""
Single source of truth for the Athena schema description injected into
prompts. Defined once here and imported everywhere it's needed, so the
schema never drifts between the SQL Agent and the Analyst Agent.
"""

ATHENA_SCHEMA_DESCRIPTION = """
Database: clinical_db

Table: clinical_trials
  - trial_id (string, primary key)
  - trial_name (string)
  - phase (string)
  - therapeutic_area (string)
  - sponsor (string)
  - start_date (date)
  - end_date (date)
  - enrollment_target (int)
  - principal_investigator (string)
  - status (string)

Table: trial_sites
  - site_id (string, primary key)
  - trial_id (string, FK -> clinical_trials.trial_id)
  - site_name (string)
  - city (string)
  - country (string)
  - principal_investigator (string)
  - enrollment (int)

Table: patient_data
  - patient_id (string, primary key)
  - trial_id (string, FK -> clinical_trials.trial_id)
  - site_id (string, FK -> trial_sites.site_id)
  - gender (string)
  - age (int)
  - dropout_flag (boolean)
  - dropout_reason (string)
  - enrollment_date (date)

Table: adverse_events
  - ae_id (string, primary key)
  - patient_id (string, FK -> patient_data.patient_id)
  - trial_id (string, FK -> clinical_trials.trial_id)
  - severity (string)
  - event_term (string)
  - occurrence_date (date)
  - outcome (string)

Table: study_metrics
  - trial_id (string, FK -> clinical_trials.trial_id)
  - site_id (string, FK -> trial_sites.site_id)
  - avg_visit_duration_min (int)
  - avg_dropout_rate (double)
  - avg_ae_rate (double)

Relationships:
  trial_sites.trial_id       = clinical_trials.trial_id
  patient_data.trial_id      = clinical_trials.trial_id
  patient_data.site_id       = trial_sites.site_id
  adverse_events.trial_id    = clinical_trials.trial_id
  adverse_events.patient_id  = patient_data.patient_id
  study_metrics.trial_id     = clinical_trials.trial_id
  study_metrics.site_id      = trial_sites.site_id

Rules:
  - Only these five tables exist. Never invent columns or tables.
  - principal_investigator exists in both clinical_trials (trial-level) and
    trial_sites (site-level); always qualify it with the table alias.
  - Always qualify ambiguous columns with table aliases in JOINs.
  - Only SELECT statements are permitted (read-only).
""".strip()
