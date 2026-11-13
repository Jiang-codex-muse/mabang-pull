#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
马帮 ERP 拉数程序 - API 模式 (v0.1)
=====================================
用途: 不用每次手动下载表格, 一条命令自动拉马帮订单,
算出销量 / 销售额, 按天 / 店铺 / SKU 汇总, 输出 CSV (+Excel, 如已装 openpyxl)。

接口依据 (公开资料, 已核对):
- 订单: POST https://api.mabang.com/order-get-order-list-new
  参数示例: updateTimeStart, updateTimeEnd, maxRows=1000, status=[6,7]
  来源: 轻易云马帮集成案例, POST /order-get-order-list-new, Host: api.mabang.com
- 店铺: sys-get-shop-list
- 库存 SKU: stock-do-search-sku-list-new
- 认证: AppKey + HMAC-SHA256 签名 (马帮官方公开的规范, 具体拼串方式以
  你开放平台帮助中心 "开放平台入口与前期准备" 那页为准)

重要提醒 - 直说, 别踩坑:
1. 这个程序现在是 v0.1, 没有用你的真实账号跑通过。
   原因: 你的开放平台账号登录提示 "无管理权限",
   还没有 AppKey / AppSecret, 我这边也没法替你登录验证。
2. 签名拼串方式: 马帮官方文档在登录后的帮助中心里,
   公开网页上只写了 "HMAC-SHA256", 没写死拼串细节。
   所以本程序把签名做成可配置的, config.json 里 sign_method 可选:
     - "hmac_json":  HMAC-SHA256(appSecret, 请求 JSON 体) -> hex
     - "hmac_sorted": 先把业务参数按 key 排序拼成 k=v&k=v, 再 HMAC-SHA256
     - "hmac_timestamp": HMAC-SHA256(appSecret, timestamp 字符串)
   先用 --test-sign 跑一遍, 把三种签名的输出发我 / 对照官方文档示例,
   选对的那一种, 改 config 后再正式拉数。不要盲目相信默认项。
3. Codex 现在正在改工作台, 这个程序先不放进 jcf-workbench 仓库,
   单独放在 Windows 工作电脑上跑, 等 Codex 改完 push 后再决定要不要合进去。

用法 (Windows, 在工作电脑的 PowerShell / CMD 里):
  pip install requests openpyxl
  copy config.example.json config.json
  # 用记事本打开 config.json, 填 appKey / appSecret, 别把密钥发到群里 / 提交到仓库
  python mabang_pull.py --start 2026-11-01 --end 2026-11-13
  python mabang_pull.py --start 2026-11-01 --end 2026-11-13 --mock   # 没密钥时先跑通流程, 用模拟订单
  python mabang_pull.py --test-sign                                # 只打印三种签名, 不调接口
  python mabang_pull.py --shops                                    # 只拉店铺列表 sys-get-shop-list

输出:
  output/orders_raw_YYYYMMDD-HHMMSS.csv     原始订单 (一单多行按商品拆开也保留)
  output/sales_by_day_*.csv                 按天汇总: 日期 / 店铺 / 销量 / 销售额
  output/sales_by_sku_*.csv                 按 SKU 汇总: SKU / 店铺 / 销量 / 销售额
  同名 .xlsx (如已装 openpyxl, 三个 sheet 在一个文件里)
"""
import argparse
import csv
import hashlib
import hmac
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

API_HOST = "https://api.mabang.com"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# ---------- 签名 ----------
def make_sign(body: dict, app_key: str, app_secret: str, timestamp: int, method: str) -> str:
    """返回 hex 签名. method 见文件头说明, 以官方文档为准, 这里不硬编一个'一定对'的算法."""
    if method == "hmac_json":
        msg = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return hmac.new(app_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    if method == "hmac_sorted":
        msg = "&".join(f"{k}={body[k]}" for k in sorted(body.keys()))
        return hmac.new(app_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    if method == "hmac_timestamp":
        return hmac.new(app_secret.encode(), str(timestamp).encode(), hashlib.sha256).hexdigest()
    raise ValueError(f"未知 sign_method: {method}, 可选 hmac_json / hmac_sorted / hmac_timestamp")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"没找到 {CONFIG_PATH}, 先复制 config.example.json 改名 config.json 再填 AppKey")
        print("没有密钥想先跑通流程: 加 --mock")
        sys.exit(2)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

# ---------- API 调用 ----------
def call_api(cfg, api_name, body):
    if requests is None:
        raise RuntimeError("没装 requests, 先跑: pip install requests")
    timestamp = int(time.time())
    sign = make_sign(body, cfg["appKey"], cfg["appSecret"], timestamp, cfg.get("sign_method", "hmac_json"))
    # 把认证字段放进请求体 / 请求头两种常见放法都带上, 服务端只认它要的那几个, 多余的一般忽略.
    # 如果官方文档写的是只放 header, 把下面 payload 里的 appKey/timestamp/sign 删掉, 只留 header 即可.
    payload = dict(body)
    payload.update({"appKey": cfg["appKey"], "timestamp": timestamp, "sign": sign})
    headers = {
        "Content-Type": "application/json",
        "appKey": cfg["appKey"],
        "timestamp": str(timestamp),
        "sign": sign,
    }
    url = f"{API_HOST.rstrip('/')}/{api_name}"
    r = requests.post(url, json=payload, headers=headers, timeout=60)
    print(f"[{api_name}] HTTP {r.status_code}  {url}")
    try:
        data = r.json()
    except Exception:
        print("返回不是 JSON, 前 500 字:", r.text[:500])
        raise
    # 马帮常见返回: {"code":0 / "success":true, "data": {...}} 或直接 {"orders": [...]}
    # 这里只做宽容解析, 具体 code 含义以官方文档为准.
    if isinstance(data, dict) and data.get("code") not in (None, 0, 200, "0", "200") and not data.get("success", True):
        print("接口报错, 原样返回:", json.dumps(data, ensure_ascii=False)[:1000])
        raise RuntimeError(f"马帮接口返回错误: {data}")
    return data

def extract_orders(data):
    """宽容解析: 订单列表可能在 data.orders / data.data.orders / data.list / data 本身是 list."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("orders", "list", "data"):
        v = data.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for k2 in ("orders", "list"):
                if isinstance(v.get(k2), list):
                    return v[k2]
    return []

# ---------- 汇总 ----------
def _f(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def _int(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default

def summarize(orders):
    """返回 (明细行, 按天汇总, 按SKU汇总)
    金额字段别名: itemTotal / totalOrigin / orderFee / totalAmount
    数量: 订单商品明细 quantity 之和, 没有明细就按 1 件算
    日期: paidTime / createDate / orderDate, 取前 10 位 YYYY-MM-DD
    """
    rows, by_day, by_sku = [], defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
    for o in orders:
        if not isinstance(o, dict):
            continue
        shop = o.get("shopName") or o.get("shopId") or ""
        date = str(o.get("paidTime") or o.get("createDate") or o.get("orderDate") or "")[:10]
        amount = _f(o.get("itemTotal", o.get("totalOrigin", o.get("orderFee", o.get("totalAmount", 0)))))
        items = o.get("items") or o.get("orderItems") or o.get("detail") or []
        if isinstance(items, list) and items:
            for it in items:
                if not isinstance(it, dict):
                    continue
                sku = it.get("sku") or it.get("salesSku") or it.get("productSku") or ""
                qty = _int(it.get("quantity", it.get("qty", it.get("count", 1))))
                amt = _f(it.get("amount", it.get("itemTotal", 0))) or (amount / len(items) if amount else 0)
                rows.append({"date": date, "shop": shop, "platformOrderId": o.get("platformOrderId", ""),
                             "sku": sku, "qty": qty, "amount": round(amt, 2),
                             "currency": o.get("currencyId") or o.get("currency") or ""})
                by_day[(date, shop)][0] += qty
                by_day[(date, shop)][1] += amt
                by_sku[(sku, shop)][0] += qty
                by_sku[(sku, shop)][1] += amt
        else:
            qty = _int(o.get("quantity", 1))
            rows.append({"date": date, "shop": shop, "platformOrderId": o.get("platformOrderId", ""),
                         "sku": "", "qty": qty, "amount": round(amount, 2),
                         "currency": o.get("currencyId") or o.get("currency") or ""})
            by_day[(date, shop)][0] += qty
            by_day[(date, shop)][1] += amount
            by_sku[("", shop)][0] += qty
            by_sku[("", shop)][1] += amount
    day_rows = [{"date": d, "shop": s, "qty": v[0], "amount": round(v[1], 2)}
                for (d, s), v in sorted(by_day.items())]
    sku_rows = [{"sku": s, "shop": sh, "qty": v[0], "amount": round(v[1], 2)}
                for (s, sh), v in sorted(by_sku.items())]
    return rows, day_rows, sku_rows

def write_outputs(rows, day_rows, sku_rows):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    paths = {}
    for name, data in (("orders_raw", rows), ("sales_by_day", day_rows), ("sales_by_sku", sku_rows)):
        p = os.path.join(OUTPUT_DIR, f"{name}_{ts}.csv")
        if data:
            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
                w.writeheader(); w.writerows(data)
        else:
            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                f.write("")
        paths[name] = p
        print(f"写出 {p}  {len(data)} 行")
    # Excel (可选)
    try:
        from openpyxl import Workbook
        wb = Workbook()
        for i, (sheet, data) in enumerate((("原始订单", rows), ("按天汇总", day_rows), ("按SKU汇总", sku_rows))):
            ws = wb.active if i == 0 else wb.create_sheet(sheet)
            ws.title = sheet
            if data:
                ws.append(list(data[0].keys()))
                for r in data:
                    ws.append(list(r.values()))
        xp = os.path.join(OUTPUT_DIR, f"sales_summary_{ts}.xlsx")
        wb.save(xp)
        paths["xlsx"] = xp
        print(f"写出 {xp}")
    except ImportError:
        print("没装 openpyxl, 只出 CSV (想出 Excel: pip install openpyxl)")
    total_qty = sum(r["qty"] for r in day_rows)
    total_amt = sum(r["amount"] for r in day_rows)
    print(f"汇总: 销量 {total_qty} 件, 销售额 {total_amt:.2f}")
    return paths

def mock_orders():
    return [
        {"platformOrderId": "MOCK-001", "shopName": "阿联酋店", "paidTime": "2026-11-12 10:00:00",
         "currencyId": "AED", "items": [{"sku": "SKU-A", "quantity": 2, "amount": 120.0}]},
        {"platformOrderId": "MOCK-002", "shopName": "阿联酋店", "paidTime": "2026-11-12 11:00:00",
         "currencyId": "AED", "items": [{"sku": "SKU-A", "quantity": 1, "amount": 60.0},
                                        {"sku": "SKU-B", "quantity": 3, "amount": 90.0}]},
        {"platformOrderId": "MOCK-003", "shopName": "沙特店", "paidTime": "2026-11-13 09:00:00",
         "currencyId": "SAR", "items": [{"sku": "SKU-B", "quantity": 2, "amount": 80.0}]},
    ]

def main():
    ap = argparse.ArgumentParser(description="马帮 ERP 拉数 - API 模式")
    ap.add_argument("--start", default="", help="开始日期 YYYY-MM-DD, 如 2026-11-01")
    ap.add_argument("--end", default="", help="结束日期 YYYY-MM-DD, 如 2026-11-13")
    ap.add_argument("--mock", action="store_true", help="不用密钥, 用模拟订单跑通流程")
    ap.add_argument("--test-sign", action="store_true", help="只打印三种签名算法的输出, 不调接口")
    ap.add_argument("--shops", action="store_true", help="只拉店铺列表 sys-get-shop-list")
    args = ap.parse_args()

    if args.test_sign:
        cfg = load_config() if os.path.exists(CONFIG_PATH) else {"appKey": "TEST_KEY", "appSecret": "TEST_SECRET"}
        body = {"updateTimeStart": "2026-11-01 00:00:00", "updateTimeEnd": "2026-11-13 23:59:59", "maxRows": 100}
        ts = int(time.time())
        for m in ("hmac_json", "hmac_sorted", "hmac_timestamp"):
            print(m, make_sign(body, cfg["appKey"], cfg["appSecret"], ts, m))
        print("把上面输出对照马帮官方文档的签名示例, 选对的那个填进 config.json 的 sign_method")
        return

    if args.mock:
        print("MOCK 模式: 用模拟订单跑通汇总, 不调马帮接口")
        rows, day_rows, sku_rows = summarize(mock_orders())
        write_outputs(rows, day_rows, sku_rows)
        return

    cfg = load_config()
    if not cfg.get("appKey") or not cfg.get("appSecret"):
        print("config.json 里 appKey / appSecret 没填, 先填好再跑, 或加 --mock 先测试")
        sys.exit(2)

    if args.shops:
        data = call_api(cfg, "sys-get-shop-list", {})
        print(json.dumps(data, ensure_ascii=False)[:2000])
        return

    start = args.start or datetime.now().strftime("%Y-%m-%d")
    end = args.end or start
    # 分页拉取: maxRows=1000 一页, page 递增直到返回少于 1000 条
    # status 说明 (第三方文档): 1待处理 2配货中 3已发货 4已完成 5已作废 6所有未发货 7所有非未发货
    # 销量/销售额要全量, 这里默认拉 6,7 (未发货+非未发货, 即全部), 如只要已完成改成 [4]
    all_orders, page = [], 1
    while True:
        body = {"updateTimeStart": f"{start} 00:00:00", "updateTimeEnd": f"{end} 23:59:59",
                "maxRows": 1000, "status": [6, 7], "page": page}
        data = call_api(cfg, "order-get-order-list-new", body)
        orders = extract_orders(data)
        print(f"第 {page} 页拉到 {len(orders)} 单")
        if not orders:
            break
        all_orders.extend(orders)
        if len(orders) < 1000:
            break
        page += 1
        if page > 100:
            print("页数超过 100, 停一下防死循环, 缩小时间范围再拉")
            break
    print(f"共拉到 {len(all_orders)} 单, {start} 至 {end}")
    rows, day_rows, sku_rows = summarize(all_orders)
    write_outputs(rows, day_rows, sku_rows)

if __name__ == "__main__":
    main()
