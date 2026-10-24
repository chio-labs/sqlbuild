TEST (name "stg_customer_consents__adds_legacy_profile_consents_without_explicit_records");

WITH __source__storefront__customer_consents AS (
  SELECT
    'CS1' AS consent_id,
    'C1' AS customer_id,
    'email marketing' AS consent_type,
    TRUE AS granted,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS captured_at,
    PARSE_JSON('{"surface": "checkout", "policy_url": "https://shop.example.com/privacy/v2.1"}')::VARIANT AS source_context,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'CS2',
    'C1',
    'sms-marketing',
    TRUE,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    'I',
    2,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'CS2',
    'C1',
    'sms-marketing',
    NULL,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    'U',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'CS3',
    'C2',
    'email marketing',
    TRUE,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    'I',
    4,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'CS3',
    'C2',
    'email marketing',
    TRUE,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    'D',
    5,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
),

__source__storefront__customers AS (
  SELECT
    'C1' AS customer_id,
    NULL AS email,
    NULL AS phone,
    NULL AS full_name,
    NULL AS region_code,
    NULL AS storefront_code,
    '2026-01-01 10:00:00 +00:00'::TIMESTAMP_TZ AS created_at,
    NULL AS updated_at,
    PARSE_JSON('{"consents": ["email marketing", "push"]}')::VARIANT AS profile,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'C2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-01-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    PARSE_JSON('{"consents": ["push"]}')::VARIANT,
    'I',
    2,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'C2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-01-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    PARSE_JSON('{"consents": ["push"]}')::VARIANT,
    'D',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_customer_consents AS (
  SELECT
    'CS1' AS consent_id,
    'EMAIL_MARKETING' AS consent_type,
    TRUE AS is_granted,
    'checkout' AS capture_surface,
    '2.1' AS policy_version,
    FALSE AS is_legacy
  UNION ALL
  SELECT
    'CS2' AS consent_id,
    'SMS_MARKETING' AS consent_type,
    FALSE AS is_granted,
    'unknown' AS capture_surface,
    CAST(NULL AS VARCHAR) AS policy_version,
    FALSE AS is_legacy
  UNION ALL
  SELECT
    'legacy:C1:PUSH' AS consent_id,
    'PUSH' AS consent_type,
    TRUE AS is_granted,
    'profile' AS capture_surface,
    CAST(NULL AS VARCHAR) AS policy_version,
    TRUE AS is_legacy
)
