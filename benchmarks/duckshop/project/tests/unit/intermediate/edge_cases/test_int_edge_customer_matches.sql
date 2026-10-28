TEST (name "int_edge_customer_matches__compares_names_by_characters_and_ranks_long_numbers");

WITH __ref__stg_edge_customer_profiles AS (
  SELECT
    v.customer_id,
    NULL AS profile_id,
    NULL AS profile_updated_at,
    NULL AS loyalty_tier,
    v.partner_order_number::NUMBER(38, 0) AS partner_order_number,
    NULL AS partner_order_number_float,
    NULL AS is_long_order_number,
    v.full_name,
    v.previous_full_name
  FROM VALUES
    ('C-1', 'Größe Ente', 'Grosse Ente', '9007199254740992'),
    ('C-2', 'e\u0301lodie o''neill', '\u00e9lodie o''neill', '9007199254740993'),
    ('C-3', '\u0133sselmeer', 'ijsselmeer', '9007199254740991'),
    ('C-4', 'Mallard 🦆', 'Mallard', '12'),
    ('C-5', 'Teal', NULL, NULL),
    ('C-6', 'Pintail', 'pintail', '12') AS v(customer_id, full_name, previous_full_name, partner_order_number)
),

__expected__int_edge_customer_matches AS (
  SELECT
    'C-1' AS customer_id,
    3 AS name_edit_distance,
    87 AS name_similarity,
    FALSE AS is_same_person,
    3 AS order_number_rank,
    2 AS order_number_float_rank
  UNION ALL
  SELECT
    'C-2' AS customer_id,
    2 AS name_edit_distance,
    80 AS name_similarity,
    FALSE AS is_same_person,
    2 AS order_number_rank,
    2 AS order_number_float_rank
  UNION ALL
  SELECT
    'C-3' AS customer_id,
    2 AS name_edit_distance,
    89 AS name_similarity,
    FALSE AS is_same_person,
    4 AS order_number_rank,
    3 AS order_number_float_rank
  UNION ALL
  SELECT
    'C-4' AS customer_id,
    2 AS name_edit_distance,
    95 AS name_similarity,
    TRUE AS is_same_person,
    5 AS order_number_rank,
    4 AS order_number_float_rank
  UNION ALL
  SELECT
    'C-5' AS customer_id,
    CAST(NULL AS NUMBER(38, 0)) AS name_edit_distance,
    CAST(NULL AS NUMBER(38, 0)) AS name_similarity,
    FALSE AS is_same_person,
    1 AS order_number_rank,
    1 AS order_number_float_rank
  UNION ALL
  SELECT
    'C-6' AS customer_id,
    0 AS name_edit_distance,
    100 AS name_similarity,
    TRUE AS is_same_person,
    5 AS order_number_rank,
    4 AS order_number_float_rank
)
