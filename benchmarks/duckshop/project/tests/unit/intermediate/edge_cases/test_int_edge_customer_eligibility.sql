TEST (name "int_edge_customer_eligibility__not_in_fails_everyone_when_the_blocklist_has_a_null");

WITH __ref__stg_edge_customer_profiles AS (
  SELECT v.customer_id
  FROM VALUES ('C-1'), ('C-2'), ('C-3') AS v(customer_id)
),

__source__edge__customer_profiles AS (
  SELECT
    v.profile_id,
    v.customer_id,
    NULL AS full_name,
    NULL AS previous_full_name,
    NULL AS first_name,
    NULL AS middle_name,
    NULL AS last_name,
    NULL AS address_line1,
    NULL AS address_line2,
    v.loyalty_tier,
    NULL AS partner_order_number,
    NULL AS profile_updated_at,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('PR-1', 'C-1', 'Duckling'),
    ('PR-2', 'C-3', 'BLOCKED'),
    ('PR-3', NULL, 'BLOCKED') AS v(profile_id, customer_id, loyalty_tier)
),

__expected__int_edge_customer_eligibility AS (
  SELECT
    'C-1' AS customer_id,
    FALSE AS passes_not_in,
    TRUE AS passes_not_exists
  UNION ALL
  SELECT
    'C-2' AS customer_id,
    FALSE AS passes_not_in,
    TRUE AS passes_not_exists
  UNION ALL
  SELECT
    'C-3' AS customer_id,
    FALSE AS passes_not_in,
    FALSE AS passes_not_exists
)

TEST (name "int_edge_customer_eligibility__not_in_and_not_exists_agree_without_nulls");

WITH __ref__stg_edge_customer_profiles AS (
  SELECT v.customer_id
  FROM VALUES ('C-1'), ('C-2'), ('C-3') AS v(customer_id)
),

__source__edge__customer_profiles AS (
  SELECT
    v.profile_id,
    v.customer_id,
    NULL AS full_name,
    NULL AS previous_full_name,
    NULL AS first_name,
    NULL AS middle_name,
    NULL AS last_name,
    NULL AS address_line1,
    NULL AS address_line2,
    v.loyalty_tier,
    NULL AS partner_order_number,
    NULL AS profile_updated_at,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('PR-1', 'C-1', 'Duckling'),
    ('PR-2', 'C-3', 'BLOCKED') AS v(profile_id, customer_id, loyalty_tier)
),

__expected__int_edge_customer_eligibility AS (
  SELECT
    'C-1' AS customer_id,
    TRUE AS passes_not_in,
    TRUE AS passes_not_exists
  UNION ALL
  SELECT
    'C-2' AS customer_id,
    TRUE AS passes_not_in,
    TRUE AS passes_not_exists
  UNION ALL
  SELECT
    'C-3' AS customer_id,
    FALSE AS passes_not_in,
    FALSE AS passes_not_exists
)
