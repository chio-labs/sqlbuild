TEST (name "int_customer_identity__links_identities_and_flags_duplicates");

WITH __ref__stg_customers AS (
  SELECT
    'C1' AS customer_id,
    'ada@x.test' AS email_normalised,
    '+441234' AS phone_normalised,
    'Ada' AS first_name,
    'Featherby' AS last_name,
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
  UNION ALL
  SELECT
    'C2',
    'ada@x.test',
    '+441234',
    'Ada',
    'Featherby',
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
    '+15550000',
    'Bob',
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

__ref__stg_web_identifies AS (
  SELECT
    'W1' AS identity_link_key,
    'anon-2' AS anonymous_id,
    'C1' AS customer_id,
    NULL AS first_seen_at_utc,
    NULL AS last_seen_at_utc,
    NULL AS event_count,
    NULL AS identify_methods
  UNION ALL
  SELECT
    'W2',
    'anon-1',
    'C1',
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'W3',
    'anon-1',
    'C1',
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_newsletter_subscriptions AS (
  SELECT
    'N1' AS list_subscription_id,
    'ada@x.test' AS email,
    'weekly' AS list_code,
    'subscribed' AS list_status,
    NULL AS subscribed_at,
    NULL AS unsubscribed_at,
    NULL AS signup_form,
    NULL AS is_double_opt_in,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'N2',
    'ada@x.test',
    'offers',
    'unsubscribed',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_tickets AS (
  SELECT
    'T1' AS ticket_id,
    'ada@x.test' AS customer_email,
    NULL AS channel,
    NULL AS priority,
    NULL AS ticket_status,
    NULL AS created_at,
    NULL AS solved_at,
    NULL AS order_id,
    NULL AS contact_reason,
    NULL AS tag_list,
    NULL AS is_vip,
    NULL AS custom_fields,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'T2',
    'ada@x.test',
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

__expected__int_customer_identity AS (
  SELECT
    'C1' AS customer_id,
    'x.test' AS email_domain,
    'Ada Featherby' AS full_name,
    2 AS anonymous_id_count,
    2 AS ticket_count,
    'C2' AS duplicate_candidate_id,
    100 AS duplicate_name_similarity,
    2 AS accounts_sharing_email
  UNION ALL
  SELECT
    'C2' AS customer_id,
    'x.test' AS email_domain,
    'Ada Featherby' AS full_name,
    0 AS anonymous_id_count,
    2 AS ticket_count,
    'C1' AS duplicate_candidate_id,
    100 AS duplicate_name_similarity,
    2 AS accounts_sharing_email
  UNION ALL
  SELECT
    'C3' AS customer_id,
    CAST(NULL AS VARCHAR) AS email_domain,
    CAST(NULL AS VARCHAR) AS full_name,
    0 AS anonymous_id_count,
    0 AS ticket_count,
    CAST(NULL AS VARCHAR) AS duplicate_candidate_id,
    CAST(NULL AS INT) AS duplicate_name_similarity,
    1 AS accounts_sharing_email
),

__assert__newsletter_lists_hold_only_subscribed_lists AS (
  SELECT i.customer_id
  FROM __ref("int_customer_identity") AS i
  WHERE
    i.customer_id = 'C1'
    AND ARRAY_TO_STRING(i.newsletter_lists, ',') <> 'weekly'
)
