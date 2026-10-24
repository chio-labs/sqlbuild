TEST (name "rpt_newsletter_growth_monthly__nets_global_unsubscribes_against_signups");

WITH __ref__int_newsletter_status AS (
  SELECT
    'a@example.com' AS email,
    NULL AS email_domain,
    NULL AS is_role_address,
    NULL AS customer_id,
    FALSE AS is_prospect,
    NULL AS list_status_by_list,
    NULL AS subscribed_lists,
    NULL AS subscribed_list_count,
    '2026-01-10 10:00:00 +00:00'::TIMESTAMPTZ AS first_subscribed_at,
    NULL AS last_unsubscribed_at,
    FALSE AS is_globally_unsubscribed,
    NULL AS has_double_opt_in,
    NULL AS first_signup_form
  UNION ALL
  SELECT
    'b@example.com',
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    '2026-01-20 10:00:00 +00:00'::TIMESTAMPTZ,
    '2026-02-05 10:00:00 +00:00'::TIMESTAMPTZ,
    TRUE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'c@example.com',
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    '2026-02-01 10:00:00 +00:00'::TIMESTAMPTZ,
    '2026-02-10 10:00:00 +00:00'::TIMESTAMPTZ,
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'd@example.com',
    NULL,
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMPTZ,
    TRUE,
    NULL,
    NULL
),

__expected__rpt_newsletter_growth_monthly AS (
  SELECT
    '2026-01-01'::DATE AS activity_month,
    2 AS new_subscribers,
    1 AS new_prospects,
    0 AS unsubscribes,
    2 AS net_growth,
    2 AS running_audience
  UNION ALL
  SELECT
    '2026-02-01'::DATE AS activity_month,
    1 AS new_subscribers,
    1 AS new_prospects,
    1 AS unsubscribes,
    0 AS net_growth,
    2 AS running_audience
  UNION ALL
  SELECT
    '2026-03-01'::DATE AS activity_month,
    0 AS new_subscribers,
    0 AS new_prospects,
    1 AS unsubscribes,
    -1 AS net_growth,
    1 AS running_audience
),

__assert__activity_month_is_unique_and_present AS (
  SELECT t.activity_month
  FROM __ref("rpt_newsletter_growth_monthly") AS t
  GROUP BY
    t.activity_month
  HAVING
    COUNT(*) > 1
    OR t.activity_month IS NULL
)
