TEST (name "stg_customer_consents__skips_legacy_consents_when_no_profiles_load");

WITH __source__storefront__customer_consents AS (
  SELECT
    'CS1' AS consent_id,
    'C1' AS customer_id,
    'email marketing' AS consent_type,
    TRUE AS granted,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS captured_at,
    PARSE_JSON('{"surface": "checkout"}')::VARIANT AS source_context,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
),

__source__storefront__customers AS (
  SELECT *
  FROM __empty_fixture()
),

__expected__stg_customer_consents AS (
  SELECT
    'CS1' AS consent_id,
    'EMAIL_MARKETING' AS consent_type,
    TRUE AS is_granted,
    'checkout' AS capture_surface,
    FALSE AS is_legacy
)
