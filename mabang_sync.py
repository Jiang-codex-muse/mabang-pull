#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
马帮 ERP 拉数程序 v0.2 — 单独程序，主入口 mabang_sync.py
================================================================
定位：**单独程序，完成一套流程后才能对接工作台。现在绝对不接进
jcf-workbench 仓库，不要改仓库、不要 push、不要给 Codex 下集成任务。**
原因（江确认）：马帮爬来的数据准不准还没验证，贸然接进工作台会把
工作台弄乱。顺序是：先单独跑通每日同步、拿真实数据核对准确，
再对接。

它做什么（每天一次，不是“一次性”）：
  1. orders_daily       订单/销量 每日增量（last_sync_time 往前推）
  2. listing_daily      在售 Listing 每日快照（覆盖当日）
  3. inventory_daily    库存 每日快照（available 必填，缺了不写零）
  4. fba_shipments_daily FBA 货件 每日核对（upsert + 异常检查）
  5. replenishment_daily 补货建议 每日派生（只计算，不拉取）

主路线是浏览器自动导出（AppKey 拿不到，API 模式先放下）。
API 字段保留在 sync_jobs.json 里，有 AppKey 后任务名/输出表不变，
直接启用即可。

输出（后期对接用，字段名尽量对齐工作台 audit）：
  output/mabang_data.sqlite   规范表，见 output/schema.sql
  output/json/<date>/*.json    每日原始 + 汇总 JSON
  output/daily_report_YYYY-MM-DD.md  每日汇总报告
  output/last_sync.json       每个任务的上次同步时间（增量依据）

用法（Windows 工作电脑）：
  python mabang_sync.py --mock --date 2026-11-13
  python mabang_sync.py --mock --date 2026-11-13 --jobs orders_daily,inventory_daily
  python mabang_sync.py --mock --date today
  python mabang_sync.py --list-jobs
  # 真实模式（现在会明确停住，不编数据）：
  python mabang_sync.py --date 2026-11-13
  # 每日运行（见 run_daily.bat / run_daily.sh）：
  run_daily.bat

对接约定（给以后写工作台对接的人）：
  - 读库只读 output/mabang_data.sqlite，不要改它的表结构。
  - 关联钥匙：store_id + date + sku + asin。店铺 id 写死：
    one=ONE-XY(AE/AED), home=STARRY BOX(AE/AED), sa=BIGO-SA(SA/SAR)。
  - 首页逐日口径：daily_sales 里期间每一天都要有记录，缺一天
    工作台就退回月度/空白，本程序不补零，在日报里列出缺失日期。
  - 利润、汇率、采购批次、头程运价、费用拆分不在本程序里编，
    见 DATA_MAP.md §6。
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE, "output")
JSON_DIR = os.path.join(OUTPUT_DIR, "json")
DB_PATH = os.path.join(OUTPUT_DIR, "mabang_data.sqlite")
LAST_SYNC_PATH = os.path.join(OUTPUT_DIR, "last_sync.json")
JOBS_PATH = os.path.join(BASE, "sync_jobs.json")

STORES = {
    "one": {"name": "ONE-XY", "marketplace": "AE", "currency": "AED", "timezone": "Asia/Dubai"},
    "home": {"name": "STARRY BOX", "marketplace": "AE", "currency": "AED", "timezone": "Asia/Dubai"},
    "sa": {"name": "BIGO-SA", "marketplace": "SA", "currency": "SAR", "timezone": "Asia/Riyadh"},
}

SCHEMA_SQL = """
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
"""

# ---------------------------------------------------------------- mock 数据
# 每类 5-10 条，SKU 用截图里真实出现过的 XCFAE- / XCFSA- 编号，金额/数量
# 是编来跑通流程的，不是真实经营数据。真实跑时用 --mock 以外的模式。
def mock_orders(run_date):
    # 日期分散在 10-15 天内，让 30 天滚动销量不为 0
    return [
        {"platformOrderId": "MOCK-ORD-001", "store_id": "one", "date": "2026-11-10", "sku": "XCFAE-GA069", "asin": "B0F7R962XX", "qty": 4, "amount": 280.0, "currency": "AED", "status": "已完成", "paid_time": "2026-11-10 10:00:00"},
        {"platformOrderId": "MOCK-ORD-002", "store_id": "one", "date": "2026-11-11", "sku": "XCFAE-GA069", "asin": "B0F7R962XX", "qty": 3, "amount": 210.0, "currency": "AED", "status": "已完成", "paid_time": "2026-11-11 11:00:00"},
        {"platformOrderId": "MOCK-ORD-003", "store_id": "one", "date": "2026-11-12", "sku": "XCFAE-GA012", "asin": "B0H2H8F8XX", "qty": 2, "amount": 150.0, "currency": "AED", "status": "已完成", "paid_time": "2026-11-12 09:00:00"},
        {"platformOrderId": "MOCK-ORD-004", "store_id": "one", "date": "2026-11-13", "sku": "XCFAE-GA078", "asin": "B0GK1M6TXX", "qty": 5, "amount": 400.0, "currency": "AED", "status": "已发货", "paid_time": "2026-11-13 09:00:00"},
        {"platformOrderId": "MOCK-ORD-005", "store_id": "sa", "date": "2026-11-12", "sku": "XCFAE-GA009", "asin": "B0F2YYB5XX", "qty": 2, "amount": 180.0, "currency": "SAR", "status": "已完成", "paid_time": "2026-11-12 10:00:00"},
        {"platformOrderId": "MOCK-ORD-006", "store_id": "sa", "date": "2026-11-13", "sku": "XCFAE-GA009", "asin": "B0F2YYB5XX", "qty": 1, "amount": 90.0, "currency": "SAR", "status": "已发货", "paid_time": "2026-11-13 10:00:00"},
        {"platformOrderId": "MOCK-ORD-007", "store_id": "home", "date": "2026-11-13", "sku": "XCFAE-GA074", "asin": "B0F7R962XX", "qty": 3, "amount": 240.0, "currency": "AED", "status": "已完成", "paid_time": "2026-11-13 11:00:00"},
        {"platformOrderId": "MOCK-ORD-008", "store_id": "one", "date": "2026-10-28", "sku": "XCFAE-GA069", "asin": "B0F7R962XX", "qty": 6, "amount": 420.0, "currency": "AED", "status": "已完成", "paid_time": "2026-10-28 10:00:00"},
    ]

def mock_listings(run_date):
    return [
        {"store_id": "one", "sku": "XCFAE-GA069", "asin": "B0F7R962XX", "fnsku": "X002AS32BR", "name": "陶瓷花盆 CZ孔雀蓝苹果型 大号", "status": "在售", "daily_sales_avg": 0.5, "available": 12, "listed_at": "2025-05-07", "snapshot_date": run_date},
        {"store_id": "one", "sku": "XCFAE-GA074", "asin": "B0F7R962XX", "fnsku": "X002AS32BR", "name": "四合一植物灯", "status": "在售", "daily_sales_avg": 0.03, "available": 0, "listed_at": "2025-05-07", "snapshot_date": run_date},
        {"store_id": "one", "sku": "XCFAE-GA156", "asin": "B0H2H8F8XX", "fnsku": "X002LJ3EGX", "name": "花盆托盘 黑色 160#", "status": "在售", "daily_sales_avg": 0.0, "available": 5, "listed_at": "2026-05-21", "snapshot_date": run_date},
        {"store_id": "one", "sku": "XCFAE-GA041", "asin": "B0DMJ4Y2XX", "fnsku": "X00265T3AD", "name": "木蜡笔-带帽加厚款", "status": "在售", "daily_sales_avg": 0.57, "available": 20, "listed_at": "2024-11-09", "snapshot_date": run_date},
        {"store_id": "sa", "sku": "XCFAE-GA009", "asin": "B0F2YYB5XX", "fnsku": "X0029ROPP1", "name": "盆栽水壶6个装 白", "status": "在售", "daily_sales_avg": 0.06, "available": 8, "listed_at": "2025-03-29", "snapshot_date": run_date},
        {"store_id": "home", "sku": "XCFAE-GA074", "asin": "B0F7R962XX", "fnsku": "X002AS32BR", "name": "四合一植物灯", "status": "在售", "daily_sales_avg": 0.1, "available": 3, "listed_at": "2025-05-07", "snapshot_date": run_date},
    ]

def mock_inventory(run_date):
    return [
        {"store_id": "one", "date": run_date, "sku": "XCFAE-GA069", "asin": "B0F7R962XX", "fnsku": "X002AS32BR", "available": 12, "inbound": 45, "fba_stock": 12, "currency": "AED"},
        {"store_id": "one", "date": run_date, "sku": "XCFAE-GA012", "asin": "B0H2H8F8XX", "fnsku": "X002LJ3EGX", "available": 4, "inbound": 0, "fba_stock": 4, "currency": "AED"},
        {"store_id": "one", "date": run_date, "sku": "XCFAE-GA078", "asin": "B0GK1M6TXX", "fnsku": "X00210VXCH", "available": 30, "inbound": 10, "fba_stock": 30, "currency": "AED"},
        {"store_id": "one", "date": run_date, "sku": "XCFAE-GA074", "asin": "B0F7R962XX", "fnsku": "X002AS32BR", "available": 0, "inbound": 0, "fba_stock": 0, "currency": "AED"},
        {"store_id": "sa", "date": run_date, "sku": "XCFAE-GA009", "asin": "B0F2YYB5XX", "fnsku": "X0029ROPP1", "available": 8, "inbound": 20, "fba_stock": 8, "currency": "SAR"},
        {"store_id": "sa", "date": run_date, "sku": "XCFAE-GA041", "asin": "B0DMJ4Y2XX", "fnsku": "X00265T3AD", "available": 15, "inbound": 0, "fba_stock": 15, "currency": "SAR"},
        {"store_id": "home", "date": run_date, "sku": "XCFAE-GA074", "asin": "B0F7R962XX", "fnsku": "X002AS32BR", "available": 3, "inbound": 5, "fba_stock": 3, "currency": "AED"},
        {"store_id": "home", "date": run_date, "sku": "XCFAE-GA069", "asin": "B0F7R962XX", "fnsku": "X002AS32BR", "available": 6, "inbound": 0, "fba_stock": 6, "currency": "AED"},
    ]

def mock_fba_shipments(run_date):
    # 6 票：2 票异常（1 票 >70 天未入库，1 票亚马逊超时关闭但 0 入库）
    # shipping_date 到 run_date 的天数是算出来的，不要写死“异常”就完事
    return [
        {"fba_id": "FBA15MVSLHVL", "store_id": "one", "sea_waybill": "SFXA0020368", "warehouse": "DXB5", "created_date": "2026-11-10", "shipping_date": "2026-11-10", "shipped_qty": 45, "received_qty": 0, "status": "店铺货件信息已完成，物流仍在途中", "last_tracked_at": run_date},
        {"fba_id": "FBA15MSHLNCY", "store_id": "one", "sea_waybill": "SFXA0019519", "warehouse": "DXB6", "created_date": "2026-10-29", "shipping_date": "2026-10-29", "shipped_qty": 50, "received_qty": 20, "status": "船只已经开航", "last_tracked_at": run_date},
        {"fba_id": "FBA15MSHYYWR", "store_id": "one", "sea_waybill": "SFXA0019520", "warehouse": "DXB5", "created_date": "2026-10-29", "shipping_date": "2026-10-29", "shipped_qty": 163, "received_qty": 100, "status": "船只已经开航", "last_tracked_at": run_date},
        {"fba_id": "FBA15MRSCB3V", "store_id": "one", "sea_waybill": "SFXA0019241", "warehouse": "DXB5", "created_date": "2026-10-27", "shipping_date": "2026-10-27", "shipped_qty": 523, "received_qty": 523, "status": "已报关", "last_tracked_at": run_date},
        # 70 天规则示例：2026-08-20 发货，到 2026-11-13 已 85 天，0 入库 -> 异常
        {"fba_id": "FBA15OLD7001", "store_id": "one", "sea_waybill": "SFXA0018001", "warehouse": "DXB5", "created_date": "2026-08-20", "shipping_date": "2026-08-20", "shipped_qty": 100, "received_qty": 0, "status": "在途", "last_tracked_at": run_date},
        # 亚马逊超时关闭示例：状态 Closed，但 0 入库 -> 异常
        {"fba_id": "FBA15CLOSED01", "store_id": "sa", "sea_waybill": "SFXA0018002", "warehouse": "DXB6", "created_date": "2026-09-01", "shipping_date": "2026-09-01", "shipped_qty": 80, "received_qty": 0, "status": "Closed/已关闭", "last_tracked_at": run_date},
    ]

# ---------------------------------------------------------------- 工具
def load_jobs():
    with open(JOBS_PATH, encoding="utf-8") as f:
        return json.load(f)

def load_last_sync():
    if os.path.exists(LAST_SYNC_PATH):
        with open(LAST_SYNC_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_last_sync(data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(LAST_SYNC_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def init_db(conn):
    conn.executescript(SCHEMA_SQL)
    for sid, s in STORES.items():
        conn.execute(
            "INSERT OR REPLACE INTO stores(store_id,name,marketplace,currency,timezone) VALUES(?,?,?,?,?)",
            (sid, s["name"], s["marketplace"], s["currency"], s["timezone"]))
    conn.commit()
    # schema.sql 也写一份在 output/，供后期对接方直接看
    with open(os.path.join(OUTPUT_DIR, "schema.sql"), "w", encoding="utf-8") as f:
        f.write(SCHEMA_SQL.strip() + "\n")

def write_json(run_date, name, rows):
    d = os.path.join(JSON_DIR, run_date)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{name}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return p

def check_fba_abnormal(ship, run_date):
    """返回 (abnormal: bool, reason: str)。规则是江确认的新规则，起算日/关闭定义待确认，
    这里先按最直白的口径实现，并在日报里标明口径，方便江改：
    - >70 天：shipping_date 起算，到 run_date 超过 70 天，且 received_qty==0
    - 超时关闭：status 含 Closed/已关闭/超时关闭，且 received_qty==0"""
    reasons = []
    try:
        ship_d = date.fromisoformat(ship["shipping_date"])
        run_d = date.fromisoformat(run_date)
        days = (run_d - ship_d).days
        if days > 70 and (ship.get("received_qty") or 0) == 0:
            reasons.append(f"发货后 {days} 天未入库（>70 天）")
    except Exception:
        pass
    status = str(ship.get("status") or "")
    if any(k in status for k in ("Closed", "已关闭", "超时关闭")) and (ship.get("received_qty") or 0) == 0:
        reasons.append("亚马逊货件已关闭但 0 入库/0 上架")
    return (bool(reasons), "；".join(reasons))

# ---------------------------------------------------------------- 任务
def job_orders(conn, run_date, mock, last_sync):
    orders = mock_orders(run_date) if mock else []
    new, dup = 0, 0
    for o in orders:
        cur = conn.execute("SELECT 1 FROM orders WHERE platform_order_id=?", (o["platformOrderId"],)).fetchone()
        if cur:
            dup += 1
            continue
        conn.execute(
            "INSERT INTO orders(platform_order_id,store_id,date,sku,asin,qty,amount,currency,status,paid_time,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (o["platformOrderId"], o["store_id"], o["date"], o["sku"], o["asin"], o["qty"], o["amount"], o["currency"], o["status"], o["paid_time"], run_date))
        new += 1
    # 逐日汇总：按 store_id+date+sku 聚合，INSERT OR REPLACE（同一天重跑是覆盖，不重复）
    agg = defaultdict(lambda: {"units": 0, "sales": 0.0, "orders": set(), "currency": ""})
    for o in orders:
        k = (o["store_id"], o["date"], o["sku"])
        agg[k]["units"] += o["qty"]
        agg[k]["sales"] += o["amount"]
        agg[k]["orders"].add(o["platformOrderId"])
        agg[k]["currency"] = o["currency"]
    day_rows = []
    for (sid, d, sku), v in sorted(agg.items()):
        asin = next((o["asin"] for o in orders if o["store_id"] == sid and o["date"] == d and o["sku"] == sku), "")
        conn.execute(
            "INSERT OR REPLACE INTO daily_sales(store_id,date,sku,asin,units,sales,orders,currency,source) VALUES(?,?,?,?,?,?,?,?,?)",
            (sid, d, sku, asin, v["units"], round(v["sales"], 2), len(v["orders"]), v["currency"], "mabang"))
        day_rows.append({"store_id": sid, "date": d, "sku": sku, "asin": asin, "units": v["units"], "sales": round(v["sales"], 2), "orders": len(v["orders"]), "currency": v["currency"]})
    write_json(run_date, "orders", orders)
    write_json(run_date, "daily_sales", day_rows)
    return {"job": "orders_daily", "rows_new": new, "rows_dup": dup, "note": f"订单 {len(orders)} 条（新增 {new}，去重 {dup}）；逐日汇总 {len(day_rows)} 行"}

def job_listing(conn, run_date, mock, last_sync):
    rows = mock_listings(run_date) if mock else []
    for r in rows:
        conn.execute(
            "INSERT OR REPLACE INTO listings(store_id,sku,asin,fnsku,name,status,daily_sales_avg,available,listed_at,snapshot_date) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (r["store_id"], r["sku"], r["asin"], r["fnsku"], r["name"], r["status"], r["daily_sales_avg"], r["available"], r["listed_at"], r["snapshot_date"]))
    write_json(run_date, "listings", rows)
    return {"job": "listing_daily", "rows_new": len(rows), "rows_dup": 0, "note": f"Listing 快照 {len(rows)} 条（snapshot_date={run_date}，当日覆盖）"}

def job_inventory(conn, run_date, mock, last_sync):
    rows = mock_inventory(run_date) if mock else []
    for r in rows:
        conn.execute(
            "INSERT OR REPLACE INTO inventory_snapshots(store_id,date,sku,asin,fnsku,available,inbound,fba_stock,currency) VALUES(?,?,?,?,?,?,?,?,?)",
            (r["store_id"], r["date"], r["sku"], r["asin"], r["fnsku"], r["available"], r["inbound"], r["fba_stock"], r["currency"]))
    write_json(run_date, "inventory", rows)
    return {"job": "inventory_daily", "rows_new": len(rows), "rows_dup": 0, "note": f"库存快照 {len(rows)} 条（snapshot_date={run_date}）"}

def job_fba(conn, run_date, mock, last_sync):
    rows = mock_fba_shipments(run_date) if mock else []
    abnormal = 0
    for s in rows:
        ab, reason = check_fba_abnormal(s, run_date)
        if ab:
            abnormal += 1
        conn.execute(
            "INSERT INTO fba_shipments(fba_id,store_id,sea_waybill,warehouse,created_date,shipping_date,shipped_qty,received_qty,status,abnormal,abnormal_reason,last_tracked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(fba_id) DO UPDATE SET store_id=excluded.store_id, sea_waybill=excluded.sea_waybill, warehouse=excluded.warehouse, created_date=excluded.created_date, shipping_date=excluded.shipping_date, shipped_qty=excluded.shipped_qty, received_qty=excluded.received_qty, status=excluded.status, abnormal=excluded.abnormal, abnormal_reason=excluded.abnormal_reason, last_tracked_at=excluded.last_tracked_at",
            (s["fba_id"], s["store_id"], s["sea_waybill"], s["warehouse"], s["created_date"], s["shipping_date"], s["shipped_qty"], s["received_qty"], s["status"], 1 if ab else 0, reason, s["last_tracked_at"]))
        # lead_time 派生：发货日 -> 末次跟踪日（实测段之一，样本按票计）
        try:
            days = (date.fromisoformat(run_date) - date.fromisoformat(s["shipping_date"])).days
            conn.execute(
                "INSERT OR REPLACE INTO lead_times(store_id,sku,segment,days,sample_n,source) VALUES(?,?,?,?,?,?)",
                (s["store_id"], s["fba_id"], "shipping_to_tracked", float(days), 1, "fba_shipments_daily"))
        except Exception:
            pass
    write_json(run_date, "fba_shipments", [{**s, "abnormal": check_fba_abnormal(s, run_date)[0], "abnormal_reason": check_fba_abnormal(s, run_date)[1]} for s in rows])
    return {"job": "fba_shipments_daily", "rows_new": len(rows), "rows_dup": 0, "note": f"FBA 货件 {len(rows)} 票，异常 {abnormal} 票"}

def job_replenishment(conn, run_date, mock, last_sync):
    # 按单 SKU：近30天销量（daily_sales 滚动）+ 当日库存快照 + lead_time
    # mock 只有几天订单，30 天窗口内有几天算几天，不编 30 天满额。
    start30 = (date.fromisoformat(run_date) - timedelta(days=29)).isoformat()
    rows = conn.execute(
        "SELECT store_id, sku, SUM(units) FROM daily_sales WHERE date>=? AND date<=? GROUP BY store_id, sku",
        (start30, run_date)).fetchall()
    out, new = [], 0
    for store_id, sku, month_sales in rows:
        inv = conn.execute(
            "SELECT available, inbound FROM inventory_snapshots WHERE store_id=? AND sku=? AND date=?",
            (store_id, sku, run_date)).fetchone()
        available = inv[0] if inv else 0
        inbound = inv[1] if inv else 0
        extra = 0
        daily = month_sales / 30.0
        target = 110 if store_id == "sa" else 90
        # lead_time：取该店该 SKU 的实测段，取不到就留空，不编数
        lt = conn.execute(
            "SELECT AVG(days) FROM lead_times WHERE store_id=?", (store_id,)).fetchone()
        lead = round(lt[0], 1) if lt and lt[0] is not None else None
        need = max(0, int(-(-target * daily // 1)) - (available + inbound + extra)) if daily else 0
        # 上式等价于 ceil(target*daily - total)，用整数运算写清楚：
        import math
        need = max(0, math.ceil(target * daily - (available + inbound + extra))) if daily else 0
        rec = min(need, math.ceil(daily * 30)) if daily else 0
        note = "按单 SKU 算；lead_time 为店级实测均值（样本少时仅供参考，样本<3 应+2 天，见 audit §5.2）" if lead else "无实测 lead_time，待 FBA 轨迹补齐"
        conn.execute(
            "INSERT OR REPLACE INTO replenishment(store_id,sku,date,month_sales_30d,daily_sales,available,inbound,extra_purchased,lead_time_days,target_days,recommended_qty,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (store_id, sku, run_date, int(month_sales), round(daily, 3), available, inbound, extra, lead, target, int(rec), note))
        out.append({"store_id": store_id, "sku": sku, "date": run_date, "month_sales_30d": int(month_sales), "daily_sales": round(daily, 3), "available": available, "inbound": inbound, "lead_time_days": lead, "target_days": target, "recommended_qty": int(rec)})
        new += 1
    write_json(run_date, "replenishment", out)
    return {"job": "replenishment_daily", "rows_new": new, "rows_dup": 0, "note": f"补货建议 {new} 个 SKU（按单 SKU，目标 AE 90 天 / SA 110 天）"}

JOBS = {
    "orders_daily": job_orders,
    "listing_daily": job_listing,
    "inventory_daily": job_inventory,
    "fba_shipments_daily": job_fba,
    "replenishment_daily": job_replenishment,
}

# ---------------------------------------------------------------- 日报
def write_daily_report(conn, run_date, results):
    total_units = conn.execute("SELECT COALESCE(SUM(units),0) FROM daily_sales WHERE date=?", (run_date,)).fetchone()[0]
    total_sales = conn.execute("SELECT COALESCE(SUM(sales),0) FROM daily_sales WHERE date=?", (run_date,)).fetchone()[0]
    # 按店当日
    per_store = conn.execute(
        "SELECT store_id, SUM(units), SUM(sales), SUM(orders) FROM daily_sales WHERE date=? GROUP BY store_id",
        (run_date,)).fetchall()
    inv = conn.execute(
        "SELECT store_id, SUM(available), SUM(inbound), SUM(fba_stock) FROM inventory_snapshots WHERE date=? GROUP BY store_id",
        (run_date,)).fetchall()
    abnormal = conn.execute(
        "SELECT fba_id, store_id, sea_waybill, shipping_date, received_qty, abnormal_reason FROM fba_shipments WHERE abnormal=1").fetchall()
    # 首页完整性：最近 7 天每天有没有 daily_sales 记录
    missing = []
    for i in range(7):
        d = (date.fromisoformat(run_date) - timedelta(days=i)).isoformat()
        n = conn.execute("SELECT COUNT(*) FROM daily_sales WHERE date=?", (d,)).fetchone()[0]
        if n == 0:
            missing.append(d)
    lines = []
    lines.append(f"# 每日同步报告 {run_date}")
    lines.append("")
    lines.append("> 马帮拉数 v0.2（单独程序，未接进工作台）。mock 数据仅用于跑通流程，不是真实经营数据。")
    lines.append("")
    lines.append(f"## 当日营业额（{run_date}，daily_sales）")
    lines.append("")
    lines.append(f"- 总销量：{total_units} 件")
    lines.append(f"- 总销售额：{total_sales:.2f}（原币合计，AED/SAR 未换算，工作台按店分币种）")
    for sid, u, s, o in per_store:
        lines.append(f"- {STORES.get(sid, {}).get('name', sid)}（{sid}）：销量 {u} 件，销售额 {s:.2f}，订单 {o} 单")
    if not per_store:
        lines.append("- 当日无销量记录")
    lines.append("")
    lines.append("## 库存快照（当日）")
    lines.append("")
    for sid, av, ib, fs in inv:
        lines.append(f"- {STORES.get(sid, {}).get('name', sid)}（{sid}）：可售 {av} 件，在途 {ib} 件，在库 {fs} 件")
    if not inv:
        lines.append("- 当日无库存快照")
    lines.append("")
    lines.append(f"## FBA 货件异常（共 {len(abnormal)} 票）")
    lines.append("")
    for fba_id, sid, wb, sd, rq, reason in abnormal:
        lines.append(f"- {fba_id}（{sid}，海运单 {wb}，发货 {sd}，已入库 {rq} 件）：{reason}")
    if not abnormal:
        lines.append("- 无异常货件")
    lines.append("")
    lines.append("## 首页完整性检查（最近 7 天）")
    lines.append("")
    if missing:
        lines.append(f"- 缺失 daily_sales 的日期：{', '.join(missing)}（工作台逐日口径缺一天就退回月度/空白，不补零）")
    else:
        lines.append("- 最近 7 天每天都有 daily_sales 记录")
    lines.append("")
    lines.append("## 各任务结果")
    lines.append("")
    for r in results:
        lines.append(f"- {r['job']}：新增 {r['rows_new']}，去重 {r['rows_dup']}。{r['note']}")
    lines.append("")
    lines.append("## 未覆盖（不在马帮拉数里）")
    lines.append("")
    lines.append("- 广告花费/ACOS：LinkFox / SP 报告；费用按 SKU 拆分：Seller Central SKU Economics 原表；")
    lines.append("  汇率、采购批次、头程运价、税费口径：人工填。见 DATA_MAP.md §6。")
    p = os.path.join(OUTPUT_DIR, f"daily_report_{run_date}.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return p

def write_output_readme():
    p = os.path.join(OUTPUT_DIR, "README.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(
            "# output/ 说明（马帮拉数 v0.2）\n\n"
            "这是单独拉数程序的输出目录，不是工作台仓库。\n\n"
            "- `mabang_data.sqlite`：规范库，表结构见 `schema.sql`。后期对接时工作台只读这个库，\n"
            "  关联钥匙 `store_id + date + sku + asin`。\n"
            "- `schema.sql`：建表语句，与程序里 `SCHEMA_SQL` 同一份。\n"
            "- `json/<date>/*.json`：每日原始 + 汇总 JSON（orders / daily_sales / listings /\n"
            "  inventory / fba_shipments / replenishment）。\n"
            "- `last_sync.json`：每个任务的上次同步时间，增量同步的依据。删了它下次会从头拉，\n"
            "  订单仍按 `platformOrderId` 去重，不会重复计销量。\n"
            "- `daily_report_YYYY-MM-DD.md`：每日汇总报告。\n"
            "- `orders_raw_*.csv` / `sales_by_day_*.csv` 等：v0.1 的旧输出，v0.2 不再依赖，\n"
            "  留着备查。\n"
            "- `downloads/`：浏览器模式下载的原始导出表。\n\n"
            "mock 数据：`--mock` 跑出来的数字是编来跑通流程的，不是真实经营数据，\n"
            "不要当经营数据用。\n")

# ---------------------------------------------------------------- 主入口
def main():
    ap = argparse.ArgumentParser(description="马帮 ERP 拉数 v0.2 — 单独程序，每日同步")
    ap.add_argument("--date", default="today", help="同步日期 YYYY-MM-DD，或 today")
    ap.add_argument("--mock", action="store_true", help="模拟数据跑通全流程，不调真实马帮")
    ap.add_argument("--jobs", default="", help="只跑指定任务，逗号分隔，如 orders_daily,inventory_daily")
    ap.add_argument("--list-jobs", action="store_true", help="列出 sync_jobs.json 里的任务")
    ap.add_argument("--full", action="store_true", help="忽略 last_sync，全量重跑当日（订单仍去重）")
    args = ap.parse_args()

    cfg = load_jobs()
    if args.list_jobs:
        for j in cfg["jobs"]:
            print(f"{j['id']}: {j['name']} | {j['frequency']} | 来源={j.get('source_browser_page') or j.get('source_api')} | 输出={','.join(j['output_tables'])}")
        print("不从马帮拿的：")
        for n in cfg.get("not_from_mabang", []):
            print(f"  {n['field']}: {n['source']}")
        return

    run_date = date.today().isoformat() if args.date in ("today", "", None) else args.date
    # 校验日期格式
    date.fromisoformat(run_date)

    if not args.mock:
        # 真实模式现在明确停住：不编数据、不假装调通。
        print("真实模式未开通：")
        print("  - API 模式需要主账号 AppKey，江已确认拿不到，签名也未对照官方文档。")
        print("  - 浏览器模式需要马帮各页面（订单/Listing/库存/FBA）的真实选择器，")
        print("    目前只有在售 Listing 页截图核对过，其他页面还没截图确认。")
        print("  先用 --mock 跑通流程；真实拉数等页面截图确认后，再按 PAGES 逐页接通。")
        print("  浏览器导出表如已手动放在 output/downloads/，后续版本会从那里解析导入。")
        sys.exit(2)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(JSON_DIR, exist_ok=True)
    last_sync = load_last_sync()
    if args.full:
        print("--full：忽略 last_sync，全量重跑当日（订单仍按 platformOrderId 去重）")
    else:
        print(f"增量依据 last_sync.json：{last_sync or '（首次，无记录）'}")

    wanted = [j.strip() for j in args.jobs.split(",") if j.strip()] if args.jobs else list(JOBS.keys())
    unknown = [j for j in wanted if j not in JOBS]
    if unknown:
        print(f"未知任务：{unknown}，可选：{list(JOBS.keys())}")
        sys.exit(2)
    # replenishment 依赖前面的任务，先跑完其他再跑它
    wanted = [j for j in wanted if j != "replenishment_daily"] + (["replenishment_daily"] if "replenishment_daily" in wanted else [])

    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        write_output_readme()
        results = []
        for job_id in wanted:
            fn = JOBS[job_id]
            r = fn(conn, run_date, mock=True, last_sync=last_sync)
            conn.execute(
                "INSERT INTO sync_runs(run_date,job,rows_new,rows_dup,status,note,created_at) VALUES(?,?,?,?,?,?,?)",
                (run_date, job_id, r["rows_new"], r["rows_dup"], "ok", r["note"], datetime.now().isoformat()))
            conn.execute(
                "INSERT INTO sync_state(job,last_sync,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(job) DO UPDATE SET last_sync=excluded.last_sync, updated_at=excluded.updated_at",
                (job_id, f"{run_date} 23:59:59", datetime.now().isoformat()))
            conn.commit()
            last_sync[job_id] = f"{run_date} 23:59:59"
            print(f"[{job_id}] {r['note']}")
            results.append(r)
        save_last_sync(last_sync)
        report = write_daily_report(conn, run_date, results)
        print(f"写出数据库 {DB_PATH}")
        print(f"写出日报 {report}")
        print(f"写出 last_sync.json：{last_sync}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
