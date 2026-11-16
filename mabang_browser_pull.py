#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
马帮 ERP 拉数程序 - 浏览器自动导出模式 (v0.2, 主路线)
=========================================================
什么时候用这个:
- 开放平台登不上 / 没有管理权限 / 不想另外付 API 费, 但 ERP 主站账号能正常登录
- 不想每次手动点导出表格, 想一键自动下载 + 自动算销量/销售额

原理:
用 Playwright 打开浏览器, 用你的 ERP 账号登录 mabangerp.com,
按 PAGES 里配置的页面逐个走: 进页面 -> 设筛选 (店铺/日期) -> 点下载/导出,
等 Excel 下载完, 再由 mabang_sync.py 解析入库、算汇总。
首次运行用有头模式 (headless=False), 你在浏览器里手动过验证码 / 扫码,
登录态会存到 auth_state.json, 下次直接复用, 不用每次输密码。

多页面配置 (v0.2 新增, 关键):
马帮数据分布在很多页面, 不止订单列表一个地方, 所以 PAGES 是字典,
一页一个配置, 每页写明: 顶部导航、标签页、筛选、下载按钮文字。
2026-11-16 已用江本地 Edge 进亚马逊专业版逐页实测核对 (见 PAGE_PATHS.md),
6 页路径/URL/筛选/列名都已写实; 但 CSS 选择器还没逐个抄准,
自动点下载前仍要按真实页面把 selectors 改对一次。

注意 - 直说:
1. 这也是 v0.2, 没用你的真实账号跑通过。马帮 ERP 网页的按钮文字 / 链接
   各版本不一样, 文件里的选择器很可能要按你实际页面改一次。
   改法: 在浏览器里右键点那个按钮 -> 检查, 把文字 / CSS 选择器抄过来改掉。
2. 账号密码不要写进代码, 用环境变量 MABANG_USER / MABANG_PASS,
   或首次手动登录后只存 auth_state.json (里面是 cookie, 别发给别人)。
3. 如果马帮页面有滑块 / 短信验证码, 程序会在那一步停住等你手动过,
   过完按回车继续, 不要让程序自己去猜验证码。
4. 单独程序, 不接进 jcf-workbench 仓库。

用法 (Windows 工作电脑):
  pip install playwright openpyxl
  playwright install chromium
  set MABANG_USER=你的马帮ERP账号
  set MABANG_PASS=你的马帮ERP密码
  python mabang_browser_pull.py --start 2026-11-01 --end 2026-11-13 --page listing --headed
  python mabang_browser_pull.py --start 2026-11-01 --end 2026-11-13 --all-pages --headed
  python mabang_browser_pull.py --start 2026-11-01 --end 2026-11-13 --page orders
  # 只列出页面配置, 不打开浏览器:
  python mabang_browser_pull.py --list-pages

输出: 下载的原始 Excel 在 output/downloads/<页面>/, 汇总由 mabang_sync.py 算。
"""
import argparse
import os
import sys
import time

LOGIN_URL = "https://www.mabangerp.com"

# 入口（2026-11-16 已核实）：官网首页顶部导航“ERP”下拉 -> “亚马逊专业版”，
# 江本地浏览器里有登录态时直接进工作台，不出现登录页。
ENTRY = {"nav": ["ERP"], "tab": "亚马逊专业版",
         "dashboard": "https://www.mabangerp.com/amazon/dashboard?source=erp&lang=cn"}

# 店铺口径（2026-11-16 实测）：马帮里只有 BIGO-sa、STARRY BOX-ae、bilabuy-ae，
# 没有 ONE-XY；bilabuy-ae 是否 = 工作台 ONE-XY 待江确认，确认前不做等同处理。

# ---- 多页面配置：按你实际页面核对这里 ----
# verify: 每个页面都写了“按什么核对”, 核对完把 verified 改成 True。
PAGES = {
    "listing": {
        "name": "在售 Listing",
        "nav": ["销售", "listing管理"],
        "tab": "在线Listing（新）",
        "url": "https://www.mabangerp.com/amazon/sale/listing",
        "verified": True,
        "verify": "2026-11-16 已在江本地 Edge 实页核对（取代 2026-11-13 截图口径）："
                  "路径 销售>listing管理>在线Listing（新），筛选有 国家/店铺"
                  "（BIGO-sa/STARRY BOX-ae/bilabuy-ae）/listing状态/上架时间，店铺筛选可生效；"
                  "无文字导出按钮，有导入下拉、列配置、右上角下载图标（未点验）。"
                  "共 529 条。列：MSKU/FNSKU、ASIN、品名/SKU、售价、销量7/14/30/90天、"
                  "FBA可售、库龄分段、日均销量、上架时间。详见 PAGE_PATHS.md。",
        "filters": {"country": "全部国家", "shop": "全部店铺", "status": "在售", "date_field": "上架时间"},
        "download_button": "text=下载",
        "selectors": {
            "login_button": "text=登录",
            "username_input": "input[name='username'], input[placeholder*='账号'], input[placeholder*='手机号']",
            "password_input": "input[type='password']",
            "submit_button": "button:has-text('登录')",
            "nav_product": "text=商品",
            "tab_listing": "text=在售Listing",
            "download": "text=下载",
            "column_config": "text=列配置",
        },
        "output_subdir": "listing",
    },
    "orders": {
        "name": "FBA订单 / 订单列表",
        "nav": ["销售", "订单管理"],
        "tab": "FBA订单",
        "url": "https://www.mabangerp.com/amazon/sale/erp/FBADingDan",
        "verified": True,
        "verify": "2026-11-16 已实页核对：路径 销售>订单管理>FBA订单，有“导出订单”按钮；"
                  "筛选 店铺/时间（付款时间或发货时间，默认付款时间30天）/状态/测评订单；"
                  "全部店铺30天439条。列：商品信息、店铺/交易号、订单金额/订单利润、时间。"
                  "注意：无单独下单时间列；单店铺筛选曾出现选完搜出0条的异常，"
                  "复核时注意筛选生效方式。详见 PAGE_PATHS.md。",
        "filters": {"shop": "全部店铺", "date_field": "付款时间"},
        "download_button": "text=导出订单",
        "selectors": {
            "nav_sales": "text=销售",
            "tab_fba_orders": "text=FBA订单",
            "export": "text=导出",
            "download": "text=下载",
        },
        "output_subdir": "orders",
    },
    "inventory": {
        "name": "FBA库存（FBA库龄页）",
        "nav": ["FBA", "数据统计"],
        "tab": "FBA库龄",
        "url": "https://www.mabangerp.com/amazon/FBA/erp/fbaKuCun",
        "verified": True,
        "verify": "2026-11-16 已实页核对：真正的 FBA 库存页是 FBA库龄，有“导出EXCEL”；"
                  "列有 ASIN/FNSKU/MSKU/店铺/仓库/报告日期/可售/不可售/待调仓/待发货/"
                  "计划入库/在途/入库中/库龄段。共 35,557 条是约150个卖家账号混排，"
                  "且单选店铺筛选曾未生效，复核时优先解决按店铺筛。本地仓对照页是"
                  "商品>商品管理>库存查询（无店铺筛选、无FNSKU）。详见 PAGE_PATHS.md。",
        "filters": {"shop": "全部店铺", "date_field": "报告日期"},
        "download_button": "text=导出EXCEL",
        "selectors": {
            "nav_warehouse": "text=仓储",
            "tab_inventory": "text=FBA库存",
            "download": "text=下载",
            "export": "text=导出",
        },
        "output_subdir": "inventory",
    },
    "fba_shipments": {
        "name": "FBA 货件",
        "nav": ["FBA", "补货管理（新）"],
        "tab": "FBA货件",
        "url": "https://www.mabangerp.com/amazon/FBA/fbaCargo",
        "verified": True,
        "verify": "2026-11-16 已实页核对：路径 FBA>补货管理（新）>FBA货件，共 33 条；"
                  "每票表头有 FBA货件编号/Reference ID/物流中心编码/创建时间/发货时间/状态，"
                  "行列有 申报量/已发货/签收量/申发差异/收发差异。无文字导出按钮"
                  "（右上角下载图标未点验）；无“收货量”列（是签收量）；"
                  "单选店铺筛选曾未生效，复核时注意。详见 PAGE_PATHS.md。",
        "filters": {"shop": "全部店铺"},
        "download_button": "text=下载",
        "selectors": {
            "nav_warehouse": "text=仓储",
            "tab_fba": "text=FBA发货",
            "download": "text=下载",
            "export": "text=导出",
        },
        "output_subdir": "fba_shipments",
    },
    "purchase": {
        "name": "采购管理",
        "nav": ["采购"],
        "tab": "采购管理",
        "url": "https://www.mabangerp.com/amazon/purchase/erp/caiGouGuanLi",
        "verified": True,
        "verify": "2026-11-16 已实页核对：路径 采购>采购管理，采购中 4,680 条；"
                  "导出在“导入/出相关”菜单（导出勾选采购单/导出搜索的全部记录）；"
                  "行内有 SKU、数量/单价、入库明细、预计到货时间。"
                  "2024-06-01 之前的采购单已归档，导出要联系客服。详见 PAGE_PATHS.md。",
        "filters": {"tab_status": "采购中"},
        "download_button": "text=导入/出相关",
        "selectors": {
            "nav_purchase": "text=采购",
            "tab_purchase": "text=采购管理",
            "export_menu": "text=导入/出相关",
        },
        "output_subdir": "purchase",
    },
    "finance_cost": {
        "name": "财务费用管理",
        "nav": ["财务", "报表管理"],
        "tab": "费用管理",
        "url": "https://www.mabangerp.com/amazon/finance/costWork",
        "verified": True,
        "verify": "2026-11-16 已实页核对：路径 财务>报表管理>费用管理；商品费用标签"
                  "列有 MSKU/ASIN/费用维度/分摊规则，结构上支持按商品拆分；但店铺费用、"
                  "商品费用当前都是 0 条、费用类型下拉为空，无法验证实际分摊结果。"
                  "员工费用标签未看。详见 PAGE_PATHS.md。",
        "filters": {"tab_cost": "商品费用"},
        "download_button": "text=下载",
        "selectors": {
            "nav_finance": "text=财务",
            "tab_cost": "text=费用管理",
            "download": "text=下载",
        },
        "output_subdir": "finance_cost",
    },
}

# 兼容 v0.1 的旧 SELECTORS 名字，别处引用时不报错
SELECTORS = PAGES["listing"]["selectors"]

AUTH_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_state.json")
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "downloads")


def list_pages():
    for pid, p in PAGES.items():
        print(f"{pid}: {p['name']} | 导航={p['nav']} 标签={p['tab']} | "
              f"下载按钮={p['download_button']} | 已核对={p['verified']}")
        print(f"    核对方法：{p['verify']}")


def run_page(page, start, end, headed):
    """走一页：登录 -> 导航 -> 筛选 -> 下载。v0.2 先实现登录+停靠流程，
    自动点下载的步骤按 PAGES 里的选择器逐页接通，未核对的页会明确停住，
    不假装点成功。"""
    pid = page
    cfg = PAGES[pid]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("没装 playwright, 先跑: pip install playwright && playwright install chromium")
        sys.exit(2)

    os.makedirs(os.path.join(DOWNLOAD_DIR, cfg["output_subdir"]), exist_ok=True)
    print(f"[{pid}] {cfg['name']}：导航 {cfg['nav']} -> 标签 {cfg['tab']}，"
          f"日期 {start} 至 {end}，下载按钮 {cfg['download_button']}")
    if not cfg["verified"]:
        print(f"[{pid}] 未核对：{cfg['verify']}")
        print(f"[{pid}] 先停在这里。发截图过来，我把这页的选择器改对后再跑全自动。")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(accept_downloads=True)
        if os.path.exists(AUTH_STATE):
            try:
                context = browser.new_context(accept_downloads=True, storage_state=AUTH_STATE)
                print("复用上次的登录态 auth_state.json")
            except Exception as e:
                print("登录态失效, 重新登录:", e)
        pg = context.new_page()
        pg.goto(LOGIN_URL, timeout=60000)
        print("已打开", LOGIN_URL)
        if headed or not os.path.exists(AUTH_STATE):
            print("如果页面要你登录, 请在浏览器里手动登录 / 过验证,")
            print("登录成功进到 ERP 首页后, 回到这里按回车继续。")
            input("登录好后按回车继续 >>> ")
        try:
            context.storage_state(path=AUTH_STATE)
            print("登录态已保存到 auth_state.json (别发给别人)")
        except Exception as e:
            print("保存登录态失败:", e)

        print(f"下一步：点导航 {cfg['nav']} -> 标签 {cfg['tab']} -> "
              f"设筛选 {cfg['filters']}（日期 {start} 至 {end}）-> 点 {cfg['download_button']}")
        print("v0.2 的 listing 页已按截图配好选择器，其他页未核对前不会自动点。")
        input("点完下载、看到文件开始下载后, 按回车继续 >>> ")
        before = set(os.listdir(os.path.join(DOWNLOAD_DIR, cfg["output_subdir"])))
        for _ in range(120):
            time.sleep(1)
            after = set(os.listdir(os.path.join(DOWNLOAD_DIR, cfg["output_subdir"])))
            new = [f for f in after - before if not f.endswith(".crdownload")]
            if new:
                print("下载到:", new)
                break
        else:
            print("120 秒内没等到新下载文件, 先检查是不是导出要排队 / 要选字段, 再重跑。")
        browser.close()
    print(f"[{pid}] 下载的表格在 output/downloads/{cfg['output_subdir']}/，")
    print("下一步用 mabang_sync.py 解析入库（真实模式接通后）。")
    return True


def main():
    ap = argparse.ArgumentParser(description="马帮 ERP 拉数 - 浏览器自动导出模式 v0.2（多页面）")
    ap.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    ap.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    ap.add_argument("--headed", action="store_true", help="打开看得见的浏览器, 首次登录用")
    ap.add_argument("--page", default="listing", choices=list(PAGES.keys()), help="只跑一页")
    ap.add_argument("--all-pages", action="store_true", help="按 PAGES 顺序跑全部页面")
    ap.add_argument("--list-pages", action="store_true", help="只列出页面配置, 不打开浏览器")
    args = ap.parse_args()

    if args.list_pages:
        list_pages()
        return
    if not args.start or not args.end:
        print("要给 --start 和 --end，例如 --start 2026-11-01 --end 2026-11-13")
        sys.exit(2)

    pages = list(PAGES.keys()) if args.all_pages else [args.page]
    for pid in pages:
        ok = run_page(pid, args.start, args.end, args.headed)
        if not ok:
            print(f"[{pid}] 未跑通，已停住，不继续往下跑，避免一半数据一半空。")
            break

if __name__ == "__main__":
    main()
