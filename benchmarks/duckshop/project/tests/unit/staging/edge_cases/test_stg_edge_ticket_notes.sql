TEST (name "stg_edge_ticket_notes__finds_order_references_with_anchored_and_unanchored_patterns");

WITH __source__edge__ticket_notes AS (
  SELECT
    v.note_id,
    v.body,
    v.tags_text,
    NULL AS utm_source,
    NULL AS discount_code,
    NULL AS sku,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('TN-01', 'Customer O''Brien asks about DS-O-1001 and DS-O-1002; refund\tplease', 'bath#gift#teal'),
    ('TN-02', 'Order ds-o-77 was REFUNDED.\nPath C:\\ducks\\pond # not a comment', '#leading'),
    ('TN-03', 'DS-O-3003', 'single'),
    ('TN-04', 'No order here, refunds  are   slow', ''),
    ('TN-05', NULL, NULL),
    ('TN-06', 'Refunded DS-O-12x and DS-O-0042', 'a##b') AS v(note_id, body, tags_text)
),

__expected__stg_edge_ticket_notes AS (
  SELECT
    'TN-01' AS note_id,
    'DS-O-1001' AS first_order_ref,
    'DS-O-1001' AS first_order_ref_dollar,
    '1002' AS second_order_number,
    FALSE AS mentions_order_rlike,
    TRUE AS mentions_order_regexp_like,
    2 AS order_ref_count,
    'refund' AS refund_word,
    'Customer O''Brien asks about DS-O-1001 and DS-O-1002; refund please' AS body_collapsed,
    TRUE AS quotes_customer,
    'gift' AS second_hash_tag
  UNION ALL
  SELECT
    'TN-02' AS note_id,
    CAST(NULL AS VARCHAR) AS first_order_ref,
    CAST(NULL AS VARCHAR) AS first_order_ref_dollar,
    CAST(NULL AS VARCHAR) AS second_order_number,
    FALSE AS mentions_order_rlike,
    TRUE AS mentions_order_regexp_like,
    0 AS order_ref_count,
    'REFUNDED' AS refund_word,
    'Order ds-o-77 was REFUNDED. Path C:\\ducks\\pond # not a comment' AS body_collapsed,
    FALSE AS quotes_customer,
    'leading' AS second_hash_tag
  UNION ALL
  SELECT
    'TN-03' AS note_id,
    'DS-O-3003' AS first_order_ref,
    'DS-O-3003' AS first_order_ref_dollar,
    CAST(NULL AS VARCHAR) AS second_order_number,
    TRUE AS mentions_order_rlike,
    TRUE AS mentions_order_regexp_like,
    1 AS order_ref_count,
    CAST(NULL AS VARCHAR) AS refund_word,
    'DS-O-3003' AS body_collapsed,
    FALSE AS quotes_customer,
    '' AS second_hash_tag
  UNION ALL
  SELECT
    'TN-04' AS note_id,
    CAST(NULL AS VARCHAR) AS first_order_ref,
    CAST(NULL AS VARCHAR) AS first_order_ref_dollar,
    CAST(NULL AS VARCHAR) AS second_order_number,
    FALSE AS mentions_order_rlike,
    FALSE AS mentions_order_regexp_like,
    0 AS order_ref_count,
    'refund' AS refund_word,
    'No order here, refunds are slow' AS body_collapsed,
    FALSE AS quotes_customer,
    '' AS second_hash_tag
  UNION ALL
  SELECT
    'TN-05' AS note_id,
    CAST(NULL AS VARCHAR) AS first_order_ref,
    CAST(NULL AS VARCHAR) AS first_order_ref_dollar,
    CAST(NULL AS VARCHAR) AS second_order_number,
    CAST(NULL AS BOOLEAN) AS mentions_order_rlike,
    CAST(NULL AS BOOLEAN) AS mentions_order_regexp_like,
    CAST(NULL AS NUMBER(38, 0)) AS order_ref_count,
    CAST(NULL AS VARCHAR) AS refund_word,
    CAST(NULL AS VARCHAR) AS body_collapsed,
    CAST(NULL AS BOOLEAN) AS quotes_customer,
    CAST(NULL AS VARCHAR) AS second_hash_tag
  UNION ALL
  SELECT
    'TN-06' AS note_id,
    'DS-O-12' AS first_order_ref,
    'DS-O-12' AS first_order_ref_dollar,
    '0042' AS second_order_number,
    FALSE AS mentions_order_rlike,
    TRUE AS mentions_order_regexp_like,
    2 AS order_ref_count,
    'Refunded' AS refund_word,
    'Refunded DS-O-12x and DS-O-0042' AS body_collapsed,
    FALSE AS quotes_customer,
    '' AS second_hash_tag
)

TEST (name "stg_edge_ticket_notes__matches_codes_by_pattern_lists_and_escapes");

WITH __source__edge__ticket_notes AS (
  SELECT
    v.note_id,
    NULL AS body,
    NULL AS tags_text,
    v.utm_source,
    v.discount_code,
    NULL AS sku,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('TN-01', 'newsletter', '50%OFF'),
    ('TN-02', 'Email', 'STAFF10'),
    ('TN-03', 'partner_feed', '50PERCENT'),
    ('TN-04', 'NEWS', 'test5'),
    ('TN-05', NULL, NULL),
    ('TN-06', 'gmail', '50%'),
    ('TN-07', 'news%', 'TEST5') AS v(note_id, utm_source, discount_code)
),

__expected__stg_edge_ticket_notes AS (
  SELECT
    'TN-01' AS note_id,
    TRUE AS is_newsletter_visit,
    TRUE AS is_customer_code,
    TRUE AS is_fifty_percent_code
  UNION ALL
  SELECT
    'TN-02' AS note_id,
    TRUE AS is_newsletter_visit,
    FALSE AS is_customer_code,
    FALSE AS is_fifty_percent_code
  UNION ALL
  SELECT
    'TN-03' AS note_id,
    FALSE AS is_newsletter_visit,
    TRUE AS is_customer_code,
    FALSE AS is_fifty_percent_code
  UNION ALL
  SELECT
    'TN-04' AS note_id,
    TRUE AS is_newsletter_visit,
    TRUE AS is_customer_code,
    FALSE AS is_fifty_percent_code
  UNION ALL
  SELECT
    'TN-05' AS note_id,
    CAST(NULL AS BOOLEAN) AS is_newsletter_visit,
    CAST(NULL AS BOOLEAN) AS is_customer_code,
    CAST(NULL AS BOOLEAN) AS is_fifty_percent_code
  UNION ALL
  SELECT
    'TN-06' AS note_id,
    TRUE AS is_newsletter_visit,
    TRUE AS is_customer_code,
    TRUE AS is_fifty_percent_code
  UNION ALL
  SELECT
    'TN-07' AS note_id,
    TRUE AS is_newsletter_visit,
    FALSE AS is_customer_code,
    FALSE AS is_fifty_percent_code
)

TEST (name "stg_edge_ticket_notes__splits_skus_at_edge_positions");

WITH __source__edge__ticket_notes AS (
  SELECT
    v.note_id,
    NULL AS body,
    NULL AS tags_text,
    NULL AS utm_source,
    NULL AS discount_code,
    v.sku,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('TN-01', 'MALLARD-01'),
    ('TN-02', 'DUCK--'),
    ('TN-03', ''),
    ('TN-04', 'A-B-C-D'),
    ('TN-05', NULL),
    ('TN-06', 'EIDER'),
    ('TN-07', '-LEADING') AS v(note_id, sku)
),

__expected__stg_edge_ticket_notes AS (
  SELECT
    'TN-01' AS note_id,
    'MALLARD' AS sku_part_zero,
    '01' AS sku_part_last,
    '' AS sku_part_beyond,
    'MALLARD-01' AS sku_part_no_delimiter,
    'MAL' AS sku_from_zero,
    '01' AS sku_last_two,
    'MAL' AS sku_before_start
  UNION ALL
  SELECT
    'TN-02' AS note_id,
    'DUCK' AS sku_part_zero,
    '' AS sku_part_last,
    '' AS sku_part_beyond,
    'DUCK--' AS sku_part_no_delimiter,
    'DUC' AS sku_from_zero,
    '--' AS sku_last_two,
    '' AS sku_before_start
  UNION ALL
  SELECT
    'TN-03' AS note_id,
    '' AS sku_part_zero,
    '' AS sku_part_last,
    '' AS sku_part_beyond,
    '' AS sku_part_no_delimiter,
    '' AS sku_from_zero,
    '' AS sku_last_two,
    '' AS sku_before_start
  UNION ALL
  SELECT
    'TN-04' AS note_id,
    'A' AS sku_part_zero,
    'D' AS sku_part_last,
    '' AS sku_part_beyond,
    'A-B-C-D' AS sku_part_no_delimiter,
    'A-B' AS sku_from_zero,
    '-D' AS sku_last_two,
    '' AS sku_before_start
  UNION ALL
  SELECT
    'TN-05' AS note_id,
    CAST(NULL AS VARCHAR) AS sku_part_zero,
    CAST(NULL AS VARCHAR) AS sku_part_last,
    CAST(NULL AS VARCHAR) AS sku_part_beyond,
    CAST(NULL AS VARCHAR) AS sku_part_no_delimiter,
    CAST(NULL AS VARCHAR) AS sku_from_zero,
    CAST(NULL AS VARCHAR) AS sku_last_two,
    CAST(NULL AS VARCHAR) AS sku_before_start
  UNION ALL
  SELECT
    'TN-06' AS note_id,
    'EIDER' AS sku_part_zero,
    'EIDER' AS sku_part_last,
    '' AS sku_part_beyond,
    'EIDER' AS sku_part_no_delimiter,
    'EID' AS sku_from_zero,
    'ER' AS sku_last_two,
    '' AS sku_before_start
  UNION ALL
  SELECT
    'TN-07' AS note_id,
    '' AS sku_part_zero,
    'LEADING' AS sku_part_last,
    '' AS sku_part_beyond,
    '-LEADING' AS sku_part_no_delimiter,
    '-LE' AS sku_from_zero,
    'NG' AS sku_last_two,
    '' AS sku_before_start
)
