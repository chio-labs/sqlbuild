TEST (name "int_newsletter_status__takes_latest_status_per_list_and_flags_prospects");

WITH __ref__stg_newsletter_subscriptions AS (
  SELECT
    'L1' AS list_subscription_id,
    'a@example.com' AS email,
    'weekly' AS list_code,
    'subscribed' AS list_status,
    '2026-01-01 10:00:00 +00:00'::TIMESTAMP_TZ AS subscribed_at,
    NULL AS unsubscribed_at,
    'footer' AS signup_form,
    TRUE AS is_double_opt_in,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'L2',
    'a@example.com',
    'weekly',
    'unsubscribed',
    '2026-01-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    '2026-02-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    'footer',
    TRUE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'L3',
    'a@example.com',
    'deals',
    'subscribed',
    '2026-02-15 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    'checkout',
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'L4',
    'info@shop.example.com',
    'weekly',
    'cleaned',
    '2026-01-05 10:00:00 +00:00'::TIMESTAMP_TZ,
    '2026-01-20 10:00:00 +00:00'::TIMESTAMP_TZ,
    'popup',
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'L5',
    NULL,
    'weekly',
    'subscribed',
    '2026-01-05 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_customers AS (
  SELECT
    'C1' AS customer_id,
    'a@example.com' AS email_normalised,
    NULL AS phone_normalised,
    NULL AS first_name,
    NULL AS last_name,
    NULL AS region_code,
    NULL AS storefront_code,
    NULL AS created_at,
    NULL AS preferred_language,
    NULL AS marketing_opt_in,
    NULL AS consent_types,
    NULL AS birth_year,
    NULL AS preferences,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_newsletter_status AS (
  SELECT
    'a@example.com' AS email,
    'example.com' AS email_domain,
    FALSE AS is_role_address,
    'C1' AS customer_id,
    FALSE AS is_prospect,
    1 AS subscribed_list_count,
    '2026-01-01 10:00:00 +00:00'::TIMESTAMPTZ AS first_subscribed_at,
    '2026-02-01 10:00:00 +00:00'::TIMESTAMPTZ AS last_unsubscribed_at,
    FALSE AS is_globally_unsubscribed,
    TRUE AS has_double_opt_in,
    'footer' AS first_signup_form
  UNION ALL
  SELECT
    'info@shop.example.com' AS email,
    'shop.example.com' AS email_domain,
    TRUE AS is_role_address,
    CAST(NULL AS VARCHAR) AS customer_id,
    TRUE AS is_prospect,
    0 AS subscribed_list_count,
    '2026-01-05 10:00:00 +00:00'::TIMESTAMPTZ AS first_subscribed_at,
    '2026-01-20 10:00:00 +00:00'::TIMESTAMPTZ AS last_unsubscribed_at,
    TRUE AS is_globally_unsubscribed,
    FALSE AS has_double_opt_in,
    'popup' AS first_signup_form
),

__assert__list_statuses_reflect_latest_change AS (
  SELECT n.email
  FROM __ref("int_newsletter_status") AS n
  WHERE
    n.email = 'a@example.com'
    AND (
      n.list_status_by_list:weekly::VARCHAR <> 'unsubscribed'
      OR ARRAY_TO_STRING(n.subscribed_lists, ',') <> 'deals'
    )
)
