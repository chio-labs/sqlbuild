TEST (name "stg_experiment_assignments__keeps_first_assignment_per_visitor");

WITH __source__clickstream__experiment_assignments AS (
  SELECT
    'A1' AS assignment_id,
    'Checkout_V2' AS experiment_key,
    'Control' AS variant_key,
    'ANON1' AS anonymous_id,
    NULL AS customer_id,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS assigned_at,
    PARSE_JSON('{"surface": "app"}')::VARIANT AS context,
    NULL AS _loaded_at
  UNION ALL
  SELECT
    'A2',
    'Checkout_V2',
    'Treatment',
    'anon1',
    NULL,
    '2026-03-10 11:00:00 +00:00'::TIMESTAMP_TZ,
    PARSE_JSON('{}')::VARIANT,
    NULL
  UNION ALL
  SELECT
    'A3',
    'Checkout_V2',
    'Treatment',
    'ANON2',
    NULL,
    '2026-03-10 09:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL
),

__expected__stg_experiment_assignments AS (
  SELECT
    'A1' AS assignment_id,
    'checkout_v2' AS experiment_key,
    'control' AS variant_key,
    'anon1' AS anonymous_id,
    'app' AS assignment_surface
  UNION ALL
  SELECT
    'A3' AS assignment_id,
    'checkout_v2' AS experiment_key,
    'treatment' AS variant_key,
    'anon2' AS anonymous_id,
    'web' AS assignment_surface
)
