TEST (name "dim_carriers__summarises_current_rate_cards_and_dispatch_record");

WITH __ref__stg_carrier_rate_cards AS (
  SELECT
    'RC1' AS rate_card_id,
    'FLAPWING' AS carrier_code,
    'STANDARD' AS service_level,
    'DE' AS origin_country,
    'FR' AS destination_country,
    'EUR' AS currency_code,
    '2026-01-01'::DATE AS valid_from,
    NULL AS valid_to,
    NULL AS band_count,
    NULL AS bands,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'RC2',
    'FLAPWING',
    'EXPRESS',
    'DE',
    'AT',
    'EUR',
    '2026-01-01'::DATE,
    '2027-01-01'::DATE,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'RC3',
    'FLAPWING',
    'STANDARD',
    'DE',
    'NL',
    'EUR',
    '2025-01-01'::DATE,
    '2026-03-01'::DATE,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'RC4',
    'WINGBEAT',
    'EXPRESS',
    'DE',
    'FR',
    'EUR',
    '2026-05-01'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_fulfilment_sla AS (
  SELECT
    'S1' AS shipment_id,
    NULL AS order_id,
    NULL AS warehouse_code,
    'FLAPWING' AS carrier_code,
    NULL AS placed_at_local,
    NULL AS shipped_at_local,
    NULL AS calendar_days_to_ship,
    NULL AS business_days_to_ship,
    NULL AS holidays_in_window,
    NULL AS dispatch_business_minutes,
    TRUE AS is_dispatch_on_time,
    NULL AS delivered_at_utc,
    24.0::DECIMAL(10, 2) AS hours_to_deliver
  UNION ALL
  SELECT
    'S2',
    NULL,
    NULL,
    'FLAPWING',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    NULL,
    48.0::DECIMAL(10, 2)
  UNION ALL
  SELECT
    'S3',
    NULL,
    NULL,
    'FLAPWING',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL
),

__seed__carriers AS (
  SELECT
    'FLAPWING' AS carrier_code,
    'Flapwing Parcels' AS carrier_name,
    'https://track.example.com/flapwing/{tracking_number}' AS tracking_url_template,
    FALSE AS is_express
  UNION ALL
  SELECT
    'WINGBEAT',
    'Wingbeat Couriers',
    'http://wingbeat.example.com/t/{tracking_number}',
    TRUE
  UNION ALL
  SELECT
    'WEBFOOT',
    'Webfoot Freight',
    NULL,
    FALSE
),

__expected__dim_carriers AS (
  SELECT
    'FLAPWING' AS carrier_code,
    'Flapwing Parcels' AS carrier_name,
    FALSE AS is_express,
    'track.example.com' AS tracking_host,
    2 AS destination_country_count,
    2 AS active_rate_card_count,
    3 AS shipment_count,
    0.6667::DECIMAL(9, 4) AS on_time_dispatch_rate,
    36.0::DECIMAL(10, 2) AS median_hours_to_deliver
  UNION ALL
  SELECT
    'WINGBEAT' AS carrier_code,
    'Wingbeat Couriers' AS carrier_name,
    TRUE AS is_express,
    'wingbeat.example.com' AS tracking_host,
    0 AS destination_country_count,
    0 AS active_rate_card_count,
    0 AS shipment_count,
    CAST(NULL AS DECIMAL(9, 4)) AS on_time_dispatch_rate,
    CAST(NULL AS DECIMAL(10, 2)) AS median_hours_to_deliver
  UNION ALL
  SELECT
    'WEBFOOT' AS carrier_code,
    'Webfoot Freight' AS carrier_name,
    FALSE AS is_express,
    CAST(NULL AS VARCHAR) AS tracking_host,
    0 AS destination_country_count,
    0 AS active_rate_card_count,
    0 AS shipment_count,
    CAST(NULL AS DECIMAL(9, 4)) AS on_time_dispatch_rate,
    CAST(NULL AS DECIMAL(10, 2)) AS median_hours_to_deliver
),

__assert__service_levels_are_distinct_and_sorted AS (
  SELECT c.carrier_code
  FROM __ref("dim_carriers") AS c
  WHERE
    ARRAY_TO_STRING(c.service_levels, ',') <> IFF(
      c.carrier_code = 'FLAPWING',
      'EXPRESS,STANDARD',
      ''
    )
),

__assert__carrier_code_is_unique_and_present AS (
  SELECT t.carrier_code
  FROM __ref("dim_carriers") AS t
  GROUP BY
    t.carrier_code
  HAVING
    COUNT(*) > 1
    OR t.carrier_code IS NULL
)
