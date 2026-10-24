TEST (name "rpt_consent_coverage__treats_missing_consent_state_as_not_granted");

WITH __ref__dim_customers AS (
  SELECT
    'C1' AS customer_id,
    NULL AS city,
    NULL AS postcode_canonical,
    NULL AS country_code,
    'EU' AS region_code,
    NULL AS email_domain,
    NULL AS full_name,
    NULL AS storefront_code,
    NULL AS preferred_language,
    NULL AS created_at,
    NULL AS age_band,
    NULL AS order_count,
    NULL AS lifetime_revenue_usd,
    NULL AS days_since_last_order,
    NULL AS rfm_segment,
    NULL AS is_vip,
    NULL AS email_marketing,
    NULL AS sms_marketing,
    NULL AS loyalty_tier_code,
    NULL AS is_multi_device,
    NULL AS possible_duplicate_of,
    NULL AS is_marketing_holdout
  UNION ALL
  SELECT
    'C2',
    NULL,
    NULL,
    NULL,
    'EU',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'C3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_customer_consent_state AS (
  SELECT
    'C1' AS customer_id,
    TRUE AS email_marketing,
    FALSE AS sms_marketing,
    TRUE AS personalisation,
    FALSE AS third_party_sharing,
    NULL AS consent_state,
    NULL AS last_consent_change_at,
    TRUE AS has_legacy_consent
  UNION ALL
  SELECT
    'C2',
    FALSE,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE
),

__expected__rpt_consent_coverage AS (
  SELECT
    'EU' AS region_code,
    2 AS customers,
    0.5::DECIMAL(9, 4) AS email_marketing_share,
    0.5::DECIMAL(9, 4) AS sms_marketing_share,
    0.5::DECIMAL(9, 4) AS personalisation_share,
    0.0::DECIMAL(9, 4) AS third_party_share,
    1 AS legacy_consent_customers
  UNION ALL
  SELECT
    'UNKNOWN' AS region_code,
    1 AS customers,
    0.0::DECIMAL(9, 4) AS email_marketing_share,
    0.0::DECIMAL(9, 4) AS sms_marketing_share,
    0.0::DECIMAL(9, 4) AS personalisation_share,
    0.0::DECIMAL(9, 4) AS third_party_share,
    0 AS legacy_consent_customers
),

__assert__region_code_is_unique_and_present AS (
  SELECT t.region_code
  FROM __ref("rpt_consent_coverage") AS t
  GROUP BY
    t.region_code
  HAVING
    COUNT(*) > 1
    OR t.region_code IS NULL
)
