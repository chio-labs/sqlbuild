-- Run this manually to seed raw data into a fresh waffle_shop.duckdb:
--   duckdb waffle_shop.duckdb < seed_raw_data.sql

CREATE TABLE IF NOT EXISTS raw_customers (
  id INTEGER,
  first_name VARCHAR,
  last_name VARCHAR,
  email VARCHAR,
  created_at TIMESTAMP
);

INSERT INTO raw_customers VALUES
  (1, 'Leslie', 'Knope', 'leslie@pawnee.gov', '2026-01-15 09:00:00'),
  (2, 'Ron', 'Swanson', 'ron@pawnee.gov', '2026-02-01 08:00:00'),
  (3, 'Ann', 'Perkins', 'ann@pawnee.gov', '2026-02-14 10:00:00'),
  (4, 'Ben', 'Wyatt', 'ben@pawnee.gov', '2026-03-01 07:30:00'),
  (5, 'April', 'Ludgate', 'april@pawnee.gov', '2026-03-15 11:00:00');

CREATE TABLE IF NOT EXISTS raw_orders (
  id INTEGER,
  customer_id INTEGER,
  waffle_type_id INTEGER,
  quantity INTEGER,
  ordered_at TIMESTAMP,
  status VARCHAR
);

INSERT INTO raw_orders VALUES
  (1, 1, 1, 2, '2026-04-01 09:15:00', 'completed'),
  (2, 1, 4, 1, '2026-04-01 09:15:00', 'completed'),
  (3, 2, 6, 3, '2026-04-01 10:30:00', 'completed'),
  (4, 3, 2, 1, '2026-04-02 08:45:00', 'completed'),
  (5, 4, 1, 1, '2026-04-02 12:00:00', 'completed'),
  (6, 4, 3, 1, '2026-04-02 12:00:00', 'completed'),
  (7, 5, 5, 2, '2026-04-03 09:00:00', 'cancelled'),
  (8, 1, 2, 1, '2026-04-03 11:00:00', 'completed'),
  (9, 2, 6, 2, '2026-04-04 10:00:00', 'preparing'),
  (10, 3, 1, 4, '2026-04-04 14:30:00', 'placed');

CREATE TABLE IF NOT EXISTS raw_payments (
  id INTEGER,
  order_id INTEGER,
  amount_cents INTEGER,
  payment_method VARCHAR,
  paid_at TIMESTAMP,
  status VARCHAR
);

INSERT INTO raw_payments VALUES
  (1, 1, 1700, 'credit_card', '2026-04-01 09:16:00', 'success'),
  (2, 2, 1050, 'credit_card', '2026-04-01 09:16:00', 'success'),
  (3, 3, 4350, 'cash', '2026-04-01 10:31:00', 'success'),
  (4, 4, 950, 'credit_card', '2026-04-02 08:46:00', 'success'),
  (5, 5, 850, 'debit_card', '2026-04-02 12:01:00', 'success'),
  (6, 6, 750, 'debit_card', '2026-04-02 12:01:00', 'success'),
  (7, 7, 2200, 'credit_card', NULL, 'failed'),
  (8, 8, 950, 'cash', '2026-04-03 11:01:00', 'success');
