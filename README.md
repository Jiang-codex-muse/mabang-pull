# 马帮 ERP 拉数程序 v0.2（单独程序）

> **完成一套流程、核对数据准确后才能对接工作台，现在绝对不接进 `jcf-workbench` 仓库。**
> 原因：马帮爬来的数据准不准还没验证，贸然接进工作台会把工作台弄乱。
> 顺序是：先单独跑通每日同步、拿真实数据核对准确，再对接。
> 本仓库是单独的 `Jiang-codex-muse/mabang-pull`，只放这个拉数程序；Codex 可以来这里挑问题、提修改意见，但不要把它集成进工作台。

目标：不用每次手动下载表格，每天一条命令自动拉马帮数据，算销量 / 销售额 /
库存 / 补货 / FBA 异常，输出工作台后期能直接读的格式。

## v0.2 有什么新东西

- **数据对照表** `DATA_MAP.md`：工作台每个模块要什么字段、马帮哪个页面给、
  更新频率（每日增量 / 每日快照 / 每月 / 人工）、必填与否，一张表说清。
- **主入口** `mabang_sync.py` + 任务配置 `sync_jobs.json`：
  `orders_daily`（订单/销量每日增量）、`listing_daily`（在售 Listing 每日快照）、
  `inventory_daily`（库存每日快照）、`fba_shipments_daily`（FBA 货件每日核对）、
  `replenishment_daily`（补货建议每日派生，按单 SKU 算）。
- **增量同步**：`output/last_sync.json` 存每个任务的上次同步时间，下次从上次
  开始拉；订单按 `platformOrderId` 去重，销量按天汇总不重复；库存/Listing
  同一天重跑是覆盖，不是叠加。
- **可对接的输出**：`output/mabang_data.sqlite`（表结构见 `output/schema.sql`），
  字段名尽量对齐工作台 audit（`store_id, date, sku, asin, sales, units, orders,
  available, inbound, fba_stock, fba_id, sea_waybill` 等），另有每日 JSON
  和 `output/daily_report_YYYY-MM-DD.md`。
- **浏览器多页面** `mabang_browser_pull.py`：`PAGES` 字典，listing / orders /
  inventory / fba_shipments 各一页。只有 listing 按你发的截图核对过，其他页
  明确标“未核对”，跑之前要发截图确认。
- **每日运行**：`run_daily.bat` / `run_daily.sh`，一条命令跑完当天所有任务。

## v0.2 每日用法

```
python mabang_sync.py --mock --date 2026-11-13        # 模拟跑通全流程
python mabang_sync.py --mock --date today
python mabang_sync.py --list-jobs
run_daily.bat                                          # Windows 每日运行
sh run_daily.sh --mock                                 # Linux/WSL 模拟每日运行
```

真实模式现在会明确停住，不编数据（见 `mabang_sync.py` 主入口说明）。

## v0.1（保留）

目标：不用每次手动下载表格，一条命令自动拉订单，算销量 / 销售额。

## 两个模式，先用哪个？

| 模式 | 文件 | 适合 | 需要 |
|---|---|---|---|
| API 模式（推荐，又快又稳） | `mabang_pull.py` | 长期自动拉数 | 开放平台主账号权限 + AppKey / AppSecret |
| 浏览器自动导出 | `mabang_browser_pull.py` | API 开不通时过渡 | ERP 主站能正常登录的账号 |

现在你的情况是：开放平台账号提示“无管理权限”，所以 **API 模式暂时跑不通，先用浏览器模式过渡，或者先找主账号开 API 权限**。

## API 模式用法（Windows 工作电脑）

```
pip install requests openpyxl
copy config.example.json config.json
# 记事本打开 config.json，填 appKey / appSecret
python mabang_pull.py --start 2026-11-01 --end 2026-11-13
python mabang_pull.py --start 2026-11-01 --end 2026-11-13 --mock   # 没密钥先跑通流程
python mabang_pull.py --test-sign                                # 对签名
python mabang_pull.py --shops                                    # 只拉店铺列表
```

## 浏览器模式用法

```
pip install playwright openpyxl
playwright install chromium
set MABANG_USER=你的马帮ERP账号
set MABANG_PASS=你的马帮ERP密码
python mabang_browser_pull.py --start 2026-11-01 --end 2026-11-13 --headed
```

首次手动登录一次，登录态存到 `auth_state.json`，下次复用。

## 输出

`output/` 里：
- `orders_raw_*.csv` 原始订单
- `sales_by_day_*.csv` 按天 / 店铺汇总：销量、销售额
- `sales_by_sku_*.csv` 按 SKU / 店铺汇总
- `sales_summary_*.xlsx` 三个 sheet 在一个文件里（装了 openpyxl 才有）

## 直说：v0.2 没实测过真实马帮账号

- 没用你的真实账号跑过，签名拼串、马帮网页按钮位置都可能要按官方文档 / 实际页面改一次。
- 签名在 `config.json` 的 `sign_method` 里选，`--test-sign` 对照官方文档示例。
- 浏览器模式的按钮选择器在 `mabang_browser_pull.py` 顶部 `PAGES` 里，只有
  listing 页按截图核对过，orders / inventory / fba_shipments 三页等你发截图。
- 还需要你提供的东西：
  1. 马帮 FBA订单页、库存页、FBA发货页截图（要看到筛选、下载按钮、列名）
  2. 首次在工作电脑上手动登录一次马帮 ERP（过验证后登录态存 `auth_state.json`）
  3. FBA 异常口径确认：70 天起算日是发货日吗？亚马逊“超时关闭”是指状态 Closed 吗？
  4. 一份真实导出的订单/Listing/库存样表，用来核对列名和数字准不准
- 密钥别发群里、别提交到仓库。`config.json` / `auth_state.json` 不要进 git。
- 这个程序先不放进 `jcf-workbench` 仓库，单独跑；完成一套每日流程、核对
  数据准确后，再谈对接。

## 直说：v0.1 没实测过

- 没用你的真实账号跑过，签名拼串、马帮网页按钮位置都可能要按官方文档 / 实际页面改一次。
- 签名在 `config.json` 的 `sign_method` 里选，`--test-sign` 对照官方文档示例。
- 浏览器模式的按钮选择器在 `mabang_browser_pull.py` 顶部 `SELECTORS` 里。
- 密钥别发群里、别提交到仓库。`config.json` / `auth_state.json` 不要进 git。
- Codex 现在正在改工作台，这个程序先不放进 `jcf-workbench` 仓库，单独跑。
