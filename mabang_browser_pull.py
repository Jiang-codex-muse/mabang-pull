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
下面只有 listing 那页是按你发的截图核对过的, 其他页是占位,
跑之前必须按真实页面核对选择器, 核对方法在每页的 "verify" 里写了。
不要猜选择器, 猜了也跑不通, 发截图过来改最快。

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

# ---- 多页面配置：按你实际页面核对这里 ----
# verify: 每个页面都写了“按什么核对”, 核对完把 verified 改成 True。
PAGES = {
    "listing": {
        "name": "在售 Listing",
        "nav": ["商品"],
        "tab": "在售Listing",
        "verified": True,
        "verify": "已按江 2026-11-13 发的截图核对：顶部导航 商品，标签 在售Listing，"
                  "筛选有 全部国家/全部店铺/在售/上架时间（开始日期-结束日期），"
                  "右上角有“下载”按钮和“列配置”，共 529 条、200 条/页。"
                  "列：MSKU/FNSKU、ASIN、品名/SKU、日均销量、上架时间、库龄。",
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
        "nav": ["销售"],
        "tab": "FBA订单",
        "verified": False,
        "verify": "未核对：需要江发 FBA订单页截图，确认筛选（店铺/日期/状态）、"
                  "导出/下载按钮文字和位置、列名（订单号、下单时间、SKU、件数、金额、状态）后再改。",
        "filters": {"shop": "全部店铺", "date_field": "下单时间"},
        "download_button": "text=导出",
        "selectors": {
            "nav_sales": "text=销售",
            "tab_fba_orders": "text=FBA订单",
            "export": "text=导出",
            "download": "text=下载",
        },
        "output_subdir": "orders",
    },
    "inventory": {
        "name": "库存 / FBA 库存",
        "nav": ["仓储"],
        "tab": "FBA库存",
        "verified": False,
        "verify": "未核对：需要江发库存页截图，确认筛选（店铺/仓库/快照日期）、"
                  "下载按钮、列名（SKU、FNSKU、ASIN、FBA可售、在途、在库）后再改。",
        "filters": {"shop": "全部店铺", "date_field": "快照日期"},
        "download_button": "text=下载",
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
        "nav": ["仓储", "物流"],
        "tab": "FBA发货",
        "verified": False,
        "verify": "未核对：需要江发马帮 FBA 发货页截图，确认字段（FBA货件号、目的仓、"
                  "发货量、入库量、状态、海运单号）和下载按钮后再改。这是补工作台"
                  "FBA 货件信息的关键一页。",
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
