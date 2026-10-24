TEST (name "int_customer_consent_state__keeps_latest_decision_per_consent_type");

WITH __ref__stg_customer_consents AS (
  SELECT
    'K1' AS consent_id,
    'C1' AS customer_id,
    'EMAIL_MARKETING' AS consent_type,
    TRUE AS is_granted,
    '2026-01-01 00:00:00 +00:00'::TIMESTAMP_TZ AS captured_at,
    NULL AS capture_surface,
    NULL AS policy_version,
    FALSE AS is_legacy
  UNION ALL
  SELECT
    'K2',
    'C1',
    'EMAIL_MARKETING',
    FALSE,
    '2026-02-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'K3',
    'C1',
    'SMS_MARKETING',
    TRUE,
    '2026-01-15 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    FALSE
  UNION ALL
  SELECT
    'K4',
    'C1',
    'PERSONALISATION',
    TRUE,
    '2025-06-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    TRUE
),

__expected__int_customer_consent_state AS (
  SELECT
    'C1' AS customer_id,
    FALSE AS email_marketing,
    TRUE AS sms_marketing,
    TRUE AS personalisation,
    FALSE AS third_party_sharing,
    '2026-02-01 00:00:00 +00:00'::TIMESTAMPTZ AS last_consent_change_at,
    TRUE AS has_legacy_consent
),

__assert__consent_state_records_revocation AS (
  SELECT s.customer_id
  FROM __ref("int_customer_consent_state") AS s
  WHERE s.consent_state:EMAIL_MARKETING::BOOLEAN IS DISTINCT FROM FALSE
)
