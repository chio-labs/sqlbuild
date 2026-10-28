TEST (name "stg_edge_customer_profiles__ranks_a_snapshot_without_update_time_first");

WITH __source__edge__customer_profiles AS (
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
    v.profile_updated_at::TIMESTAMP_NTZ AS profile_updated_at,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('PR-1', 'C-1', 'Duckling', '2026-03-01 09:00:00'),
    ('PR-2', 'C-1', 'Golden Duck', NULL),
    ('PR-3', 'C-2', 'Duckling', '2026-03-01 09:00:00'),
    ('PR-4', 'C-2', 'Mallard', '2026-03-02 09:00:00'),
    ('PR-5', 'C-3', 'Mallard', '2026-03-02 09:00:00'),
    ('PR-6', 'C-3', 'Teal', '2026-03-02 09:00:00'),
    ('PR-7', NULL, 'BLOCKED', NULL) AS v(profile_id, customer_id, loyalty_tier, profile_updated_at)
),

__expected__stg_edge_customer_profiles AS (
  SELECT
    'C-1' AS customer_id,
    'PR-2' AS profile_id,
    'Golden Duck' AS loyalty_tier
  UNION ALL
  SELECT
    'C-2' AS customer_id,
    'PR-4' AS profile_id,
    'Mallard' AS loyalty_tier
  UNION ALL
  SELECT
    'C-3' AS customer_id,
    'PR-6' AS profile_id,
    'Teal' AS loyalty_tier
)

TEST (name "stg_edge_customer_profiles__joins_name_and_address_parts_that_may_be_missing");

WITH __source__edge__customer_profiles AS (
  SELECT
    v.profile_id,
    v.customer_id,
    NULL AS full_name,
    NULL AS previous_full_name,
    v.first_name,
    v.middle_name,
    v.last_name,
    v.address_line1,
    v.address_line2,
    NULL AS loyalty_tier,
    NULL AS partner_order_number,
    NULL AS profile_updated_at,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('PR-1', 'C-1', 'Ada', 'Mallard', 'Drake', '1 Pond Lane', 'Flat 2'),
    ('PR-2', 'C-2', 'Ada', NULL, 'Drake', '1 Pond Lane', NULL),
    ('PR-3', 'C-3', 'Ada', '', 'Drake', '1 Pond Lane', ''),
    ('PR-4', 'C-4', NULL, NULL, 'Drake', NULL, 'Flat 2'),
    ('PR-5', 'C-5', 'Ada', NULL, NULL, NULL, NULL) AS v(profile_id, customer_id, first_name, middle_name, last_name, address_line1, address_line2)
),

__expected__stg_edge_customer_profiles AS (
  SELECT
    'C-1' AS customer_id,
    'Ada Mallard Drake' AS display_name,
    'Ada Drake' AS display_name_concat,
    'Ada Mallard Drake' AS display_name_skip_nulls,
    '1 Pond Lane, Flat 2' AS postal_address
  UNION ALL
  SELECT
    'C-2' AS customer_id,
    CAST(NULL AS VARCHAR) AS display_name,
    'Ada Drake' AS display_name_concat,
    CAST(NULL AS VARCHAR) AS display_name_skip_nulls,
    CAST(NULL AS VARCHAR) AS postal_address
  UNION ALL
  SELECT
    'C-3' AS customer_id,
    'Ada  Drake' AS display_name,
    'Ada Drake' AS display_name_concat,
    'Ada  Drake' AS display_name_skip_nulls,
    '1 Pond Lane, ' AS postal_address
  UNION ALL
  SELECT
    'C-4' AS customer_id,
    CAST(NULL AS VARCHAR) AS display_name,
    CAST(NULL AS VARCHAR) AS display_name_concat,
    CAST(NULL AS VARCHAR) AS display_name_skip_nulls,
    CAST(NULL AS VARCHAR) AS postal_address
  UNION ALL
  SELECT
    'C-5' AS customer_id,
    CAST(NULL AS VARCHAR) AS display_name,
    CAST(NULL AS VARCHAR) AS display_name_concat,
    CAST(NULL AS VARCHAR) AS display_name_skip_nulls,
    CAST(NULL AS VARCHAR) AS postal_address
)

TEST (name "stg_edge_customer_profiles__measures_and_recases_names_in_many_scripts");

WITH __source__edge__customer_profiles AS (
  SELECT
    v.profile_id,
    v.customer_id,
    v.full_name,
    NULL AS previous_full_name,
    v.first_name,
    NULL AS middle_name,
    NULL AS last_name,
    NULL AS address_line1,
    NULL AS address_line2,
    NULL AS loyalty_tier,
    NULL AS partner_order_number,
    NULL AS profile_updated_at,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('PR-1', 'C-1', 'größe ente', 'jürgen'),
    ('PR-2', 'C-2', 'e\u0301lodie o''neill-smith', 'e\u0301lodie'),
    ('PR-3', 'C-3', '\u0133sselmeer van der eend', '\u0133sbrand'),
    ('PR-4', 'C-4', '\u10DC\u10D8\u10DC\u10DD \u10D1\u10D4\u10E0\u10D8\u10EB\u10D4', 'ab'),
    ('PR-5', 'C-5', 'ann (dup)', 'ann'),
    ('PR-6', 'C-6', 'mallard 🦆 fan', '🦆'),
    ('PR-7', 'C-7', 'STRASSE straße', 'straße') AS v(profile_id, customer_id, full_name, first_name)
),

__expected__stg_edge_customer_profiles AS (
  SELECT
    'C-1' AS customer_id,
    'Größe Ente' AS name_title_case,
    'GRÖSSE ENTE' AS name_upper,
    10 AS name_length,
    'g' AS name_initial,
    '**jürgen' AS first_name_padded
  UNION ALL
  SELECT
    'C-2' AS customer_id,
    'E\u0301lodie O''neill-Smith' AS name_title_case,
    'E\u0301LODIE O''NEILL-SMITH' AS name_upper,
    21 AS name_length,
    'e' AS name_initial,
    '*e\u0301lodie' AS first_name_padded
  UNION ALL
  SELECT
    'C-3' AS customer_id,
    'Ĳsselmeer Van Der Eend' AS name_title_case,
    'ĲSSELMEER VAN DER EEND' AS name_upper,
    22 AS name_length,
    'ĳ' AS name_initial,
    '*ĳsbrand' AS first_name_padded
  UNION ALL
  SELECT
    'C-4' AS customer_id,
    'ნინო ბერიძე' AS name_title_case,
    'ნინო ბერიძე' AS name_upper,
    11 AS name_length,
    'ნ' AS name_initial,
    '******ab' AS first_name_padded
  UNION ALL
  SELECT
    'C-5' AS customer_id,
    'Ann (Dup)' AS name_title_case,
    'ANN (DUP)' AS name_upper,
    9 AS name_length,
    'a' AS name_initial,
    '*****ann' AS first_name_padded
  UNION ALL
  SELECT
    'C-6' AS customer_id,
    'Mallard 🦆 Fan' AS name_title_case,
    'MALLARD 🦆 FAN' AS name_upper,
    13 AS name_length,
    'm' AS name_initial,
    '*******🦆' AS first_name_padded
  UNION ALL
  SELECT
    'C-7' AS customer_id,
    'Strasse Straße' AS name_title_case,
    'STRASSE STRASSE' AS name_upper,
    14 AS name_length,
    'S' AS name_initial,
    '**straße' AS first_name_padded
)

TEST (name "stg_edge_customer_profiles__compares_order_numbers_past_double_precision_with_floats");

WITH __source__edge__customer_profiles AS (
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
    NULL AS loyalty_tier,
    v.partner_order_number::NUMBER(38, 0) AS partner_order_number,
    NULL AS profile_updated_at,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('PR-1', 'C-1', '9007199254740992'),
    ('PR-2', 'C-2', '9007199254740993'),
    ('PR-3', 'C-3', '9007199254740991'),
    ('PR-4', 'C-4', '12345678901234567890'),
    ('PR-5', 'C-5', '10000000000000000001'),
    ('PR-6', 'C-6', '-9223372036854775809') AS v(profile_id, customer_id, partner_order_number)
),

__expected__stg_edge_customer_profiles AS (
  SELECT
    'C-1' AS customer_id,
    9007199254740992 AS partner_order_number,
    '9007199254740992.0'::FLOAT AS partner_order_number_float,
    TRUE AS is_long_order_number
  UNION ALL
  SELECT
    'C-2' AS customer_id,
    9007199254740993 AS partner_order_number,
    '9007199254740992.0'::FLOAT AS partner_order_number_float,
    TRUE AS is_long_order_number
  UNION ALL
  SELECT
    'C-3' AS customer_id,
    9007199254740991 AS partner_order_number,
    '9007199254740991.0'::FLOAT AS partner_order_number_float,
    FALSE AS is_long_order_number
  UNION ALL
  SELECT
    'C-4' AS customer_id,
    12345678901234567890 AS partner_order_number,
    '1.2345678901234567e+19'::FLOAT AS partner_order_number_float,
    FALSE AS is_long_order_number
  UNION ALL
  SELECT
    'C-5' AS customer_id,
    10000000000000000001 AS partner_order_number,
    '1e+19'::FLOAT AS partner_order_number_float,
    TRUE AS is_long_order_number
  UNION ALL
  SELECT
    'C-6' AS customer_id,
    -9223372036854775809 AS partner_order_number,
    '-9.223372036854776e+18'::FLOAT AS partner_order_number_float,
    FALSE AS is_long_order_number
)
