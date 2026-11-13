-- 马帮拉数 v0.2 输出库 schema（output/mabang_data.sqlite）
-- 字段名尽量对齐工作台 audit：store_id, date, sku, asin, sales, units, orders,
-- available, inbound, fba_stock, fba_id, sea_waybill 等。
-- 关联钥匙：store_id + date + sku + asin。不要改表结构，工作台后期按此读。
CREATE TABLE IF NOT EXISTS sync_state (
  job TEXT PRIMARY KEY, last_sync TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS stores (
  store_id TEXT PRIMARY KEY, name TEXT, marketplace TEXT, currency TEXT, timezone TEXT
);
CREATE TABLE IF NOT EXISTS orders (
  platform_order_id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL, date TEXT NOT NULL, sku TEXT, asin TEXT,
  qty INTEGER NOT NULL, amount REAL NOT NULL, currency TEXT,
  status TEXT, paid_time TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS daily_sales (
  store_id TEXT NOT NULL, date TEXT NOT NULL, sku TEXT NOT NULL, asin TEXT,
  units INTEGER NOT NULL, sales REAL NOT NULL, orders INTEGER NOT NULL,
  currency TEXT, source TEXT DEFAULT 'mabang',
  PRIMARY KEY (store_id, date, sku)
);
CREATE TABLE IF NOT EXISTS listings (
  store_id TEXT NOT NULL, sku TEXT NOT NULL, asin TEXT, fnsku TEXT,
  name TEXT, status TEXT, daily_sales_avg REAL, available INTEGER,
  listed_at TEXT, snapshot_date TEXT NOT NULL,
  PRIMARY KEY (store_id, sku)
);
CREATE TABLE IF NOT EXISTS inventory_snapshots (
  store_id TEXT NOT NULL, date TEXT NOT NULL, sku TEXT NOT NULL,
  asin TEXT, fnsku TEXT, available INTEGER NOT NULL,
  inbound INTEGER, fba_stock INTEGER, currency TEXT,
  PRIMARY KEY (store_id, date, sku)
);
CREATE TABLE IF NOT EXISTS fba_shipments (
  fba_id TEXT PRIMARY KEY, store_id TEXT NOT NULL,
  sea_waybill TEXT, warehouse TEXT, created_date TEXT, shipping_date TEXT,
  shipped_qty INTEGER, received_qty INTEGER, status TEXT,
  abnormal INTEGER NOT NULL DEFAULT 0, abnormal_reason TEXT,
  last_tracked_at TEXT
);
CREATE TABLE IF NOT EXISTS lead_times (
  store_id TEXT NOT NULL, sku TEXT NOT NULL, segment TEXT NOT NULL,
  days REAL, sample_n INTEGER, source TEXT,
  PRIMARY KEY (store_id, sku, segment)
);
CREATE TABLE IF NOT EXISTS replenishment (
  store_id TEXT NOT NULL, sku TEXT NOT NULL, date TEXT NOT NULL,
  month_sales_30d INTEGER, daily_sales REAL, available INTEGER,
  inbound INTEGER, extra_purchased INTEGER, lead_time_days REAL,
  target_days INTEGER, recommended_qty INTEGER, note TEXT,
  PRIMARY KEY (store_id, sku, date)
);
CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_date TEXT NOT NULL, job TEXT NOT NULL, rows_new INTEGER,
  rows_dup INTEGER, status TEXT, note TEXT, created_at TEXT
);
