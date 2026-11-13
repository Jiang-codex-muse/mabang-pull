# 星辰科技-JCF（NEXORA）工作台完整运行需要哪些数据

> 只读核查，2026-11-13。仓库 `Jiang-codex-muse/jcf-workbench`，分支 main，最新提交
> `d3a1598`（2026-11-13，“Streamline shipment editing and attachments”），上一版
> `c1c1abe`（0.5.0-test.16）。未改仓库、未 push。本文只记录仓库代码里能找到的证据；
> 没有证据的字段一律标“未验证”，不猜。
>
> 另：本文不涉及马帮 API 本身。马帮拉数程序在同一目录的 `mabang_pull.py` /
> `mabang_browser_pull.py`，两者是独立工具。

## 0. 总结论（先看这 8 条）

1. **工作台是离线桌面应用，不是联网 ERP。** `package.json`：`name: nexora-commerce-os`，
   `version: 0.5.0-test.16`，`main: electron/main.cjs`，Electron 45.1.0 + React 19。
   `AGENTS.md` 原文：离线桌面、私有本地 Electron 会话、进程内 IPC、**所有外部请求被拒绝**；
   演示与实际工作区是分开的 SQLite 库。不要加云托管、网络监听、店铺连接器。
2. **主数据源是“手动上传报表文件”，不是接口自动同步。**
   `src/DataCenter.tsx` 顶部统计条写明数据方式是“手动上传”；首页空态写“没有来源的日期
   不填补数值”。没有数据的字段显示“—”，不编假数。
3. **唯一的一键自动拉数是 LinkFox（经 LinkFox 网关代理 Amazon SP-API 报表），而且
   只覆盖部分店铺、部分报表。** 见 §4.3。LinkFox 拉的销量/销售额拉不全、不准，
   与此直接相关：它只对沙特店（BIGO-SA）有销售/库存两类报表的“当前报表”快捷入口，
   且销售是 `GET_SALES_AND_TRAFFIC_REPORT` 逐日汇总，不是逐单订单明细。
4. **仓库里没有任何马帮（Mabang）API / 爬虫代码。** 全仓库检索 `mabang / 马帮` 只出现在：
   采购导出（“选择本店马帮买货数量模板”“保存已审核买马帮导入表”）、商品档案字段
   `localSku`（界面叫“马帮SKU”）、采购行 `erpSku / erpType`（1=库存SKU，2=组合SKU）。
   也就是说：**马帮目前在工作台里只是“采购导出目的地 + 商品身份字段”，不是销售/
   库存数据的来源。** 要把马帮订单/库存接进来，是新需求，不是现有功能。
5. **店铺只有 3 家，写死在 `electron/fixtures.cjs` 的 `storeProfiles`：**
   `one` = ONE-XY（AE，AED，Asia/Dubai，erpName `bilabuy-ae`）；
   `home` = STARRY BOX（AE，AED，Asia/Dubai，erpName `STARRY BOX-ae`）；
   `sa` = BIGO-SA（SA，SAR，Asia/Riyadh，erpName `BIGO-sa`）。
   所有报表都必须币种与店铺一致，否则导入时报错。
6. **利润不是报表直接给的，是按月、按 SKU、人工逐项核对后算出来的。**
   公式见 §5.3。缺任何一项（采购批次、头程、汇率、税费口径等）利润就是 `null`，
   显示“待补”，不会用模板价或估算价冒充。
7. **汇率没有自动来源。** 实际利润要求每期人工填 `cnyPerCurrency`（有来源的 CNY 兑换率）；
   单件测算（forecast）界面写死 `汇率1.8`；演示 fixture 的汇率是 AED 1.9 / SAR 1.8，
   明确标注“演示汇率（非市场汇率）”。
8. **FBA 发货、采购、补货的大量字段是人工录入的**（货件号、箱规、运单、采购单价、
   供应商、仓库等），报表只能提供其中一部分，不能全自动。

## 1. 仓库结构（d3a1598）

| 位置 | 内容 |
|---|---|
| 根目录 | `AGENTS.md`（实施约束）、`RELEASE_POLICY.md`、`package.json`、`pnpm-lock.yaml`、`pnpm-workspace.yaml`、`.gitignore` |
| `src/` | 约 50 个前端文件。主入口 `src/App.tsx`（39,338 字节）、`src/main.tsx`、`src/types.ts`；页面见 §2 |
| `electron/` | 约 60 个后端模块（`.cjs`）。主进程 `electron/main.cjs`（41,636 字节）；数据/导入/利润/发货/补货见 §3–§5 |
| `electron/native-python-libs/`、`electron/native-scripts/` | 内嵌 Python（xlrd/xlwt/xlutils）+ 脚本：`read_product_table.py`、`build_choicexp.py`、`export_profit.py`、`export_purchase.py`、`match_shipment_history.py`、`read_shipment_history.py`、`shipment_documents.py` |
| `electron/skill-bundles/` | 技能包：`amazon-ae-choicexp-shipment`、`amazon-sa-yite-shipment`、`amazon-listing-workflow`、`amazon-product-images`、`amazon-product-research`、`artifact-template-amazon-replenishment`，`registry.json` |
| `distribution/` | 分发/更新脚本（`server.cjs`、`pack.cjs`、`release.cjs`、`updates.cjs` 等） |
| `scripts/` | `build.mjs`、`package.mjs`、`set-exe-icon.mjs` |
| `tests/` | 约 40 个测试：`store.test.cjs`、`imports.test.cjs`、`linkfox-import.test.cjs`、`profit-center.test.cjs`、`replenishment.test.cjs`、`shipment-workflow.test.cjs`、`purchase-flow.test.cjs` 等 |
| `public/assets/` | logo、Claude 参考图（`claude-approved-portrait.png` 等） |
| 无 `README.md` | 根目录没有 README；说明在 `AGENTS.md` + 各页面文案里 |

## 2. 页面 / 模块（`src/App.tsx` 第 21 行 `nav`）

| 路由 id | 页面名 | 前端文件 | 显示什么 / 算什么 |
|---|---|---|---|
| `home` | 经营首页 | `src/ReferenceHome.tsx`、`src/LocalSalesTrend.tsx`、`src/WorkbenchWidgets.tsx` | 见 §5.1：整店 KPI（销售额、利润、利润率、订单数、ACOS/TACOS、库存周转）、趋势图、亏损 SKU、库存风险、待办。期间可选今天/昨天/近7/14/30/90天/本月/自定义；店铺、KPI、趋势图用同一期间 |
| `sku` | SKU中心 | `src/CatalogGrid.tsx`、`src/ProductWorkspace.tsx`、`src/ProductSalesDetail.tsx` | 商品档案：产品名称、马帮SKU（`localSku`）、亚马逊SKU（`sku`）、ASIN、FNSKU、上架时间、类目、产品状态（`pending_listing / listed / source_imported / archived`）；每款的经营总览、利润分析、库存与在途、采购发货、Listing与图片、历史记录 |
| `procurement` | 补货与库存 | `src/PurchasingCenter.tsx`、`src/ReplenishmentOverview.tsx`、`src/ReplenishmentPlan2.tsx`、`src/BusinessBoards.tsx`（`ProcurementBoard`） | 见 §5.2：近7/30/90天销量、FBA可售、已购未到、程序建议量、人工批准量、资料状态；补货计划2的六段实测 lead time（建计划→下单、备货、到货→装箱、装箱→发运、发货→首条轨迹、在途/清关/入库），安全值取实测天数 75 分位，样本 <3 条再加 2 天 |
| `fba` | FBA货件中心 | `src/FbaCenter.tsx`、`src/ShipmentFiles.tsx`、`src/NativeShipment.tsx` | 见 §5.4：FBA 货件、真实箱、装箱分配、海运单号、发货文件、完成规则、退回原点 |
| `finance` | 产品利润中心 | `src/ProfitCenter.tsx`、`src/ActualProfitBoard.tsx`、`src/CalculationDraftBox.tsx` | 见 §5.3：按月、按 SKU 的实际利润；单件测算（forecast）；售价版本、成本核对、生命周期利润（需完整期间覆盖） |
| `sourcing` | AI选品中心 | `src/App.tsx` 内联 + `src/CalculationDraftBox.tsx` | **暂缓**。原文：“现有候选、技能和历史来源继续保留，待你的选品工作流定稿后再启用。” |
| `new-products` | AI 新品中心 | `src/NewProductCenter.tsx`（22,334 字节） | 新品 intake、Listing 生成；后端 `electron/new-product-intakes.cjs`（39,391 字节） |
| `agents` | Agent中心 | `src/AgentCenter.tsx`、`src/ModuleAgentPanel.tsx` | 板块助手 / 任务路由；`electron/agents.cjs`、`agent-modules.cjs` |
| `data-sync` | 数据与导入 | `src/DataCenter.tsx`、`src/ImportedData.tsx`、`src/ReportUpload.tsx`、`src/NativeReportUpload.tsx`、`src/ProductImport.tsx`、`src/CandidateImport.tsx` | 见 §4：全部导入入口、报表状态、文件管理、删除已导入报表 |
| `settings` | 系统设置 | `src/WorkbenchSettings.tsx` | 外观、本地资料、安全（本地密码，8–128 字符；数据库文件本身未加密）、备份/恢复、运行边界 |

另：`src/Operations.tsx` 等是各模块下的“模板工具与历史核对”；`src/Colleague.tsx`
是同事版店铺（`distribution==='colleague'` 时店铺改为从库里读）。

## 3. 数据存在哪里

- **本地 SQLite，Node 内置 `node:sqlite`（`DatabaseSync`）。**
  `electron/store.cjs`：数据库文件是数据目录下的 `commerce.sqlite`，
  `PRAGMA journal_mode=WAL`，`user_version=1`。演示（`demo`）与实际（`real`）是
  **两个独立的库**，不互通。备份是整个 `commerce.sqlite` + `authorization.json` +
  `assets/` 下按 sha256 命名的附件（`xlsx/xls/csv/txt/tsv/gz/json/png/jpg/webp/pdf`）。
- **没有 IndexedDB / localStorage 存业务数据，没有云端数据库。**
  前端 `window.nexora` 只通过 IPC 调主进程（`src/types.ts` 的 `rpc()`）。
- 主要表（`CREATE TABLE IF NOT EXISTS … STRICT`，payload 多为 JSON 字符串）：

| 表 | 所在文件 | 关键列 |
|---|---|---|
| `meta`、`settings`、`stores`、`notes`、`audit`、`attachments` | `electron/store.cjs` | `stores(id, payload)`；`notes(id, store_id, title, body, due_date, status open/done/archived, sort_order, version, updated_at)` |
| `business_records` | `electron/domain.cjs` | `(id, store_id, kind, version, state, payload, created_at)`；`kind` 仅 `finance / replenishment / purchase` |
| `sourcing_candidates` | `electron/domain.cjs` | `(id, store_id, version, state, payload, updated_at)` |
| `import_batches`、`import_sources`、`import_media`、`catalog_products`、`import_records` | `electron/imports.cjs` | `catalog_products(id, store_id, seller_sku, payload, UNIQUE(store_id, seller_sku))`；`import_records(id, kind, source_id, sheet, source_row, store_id, title, payload)`；`kind` ∈ `source_row / issue / pairing / purchase_input / template_schema / shipment_block` |
| `catalog_revisions`、`source_resolutions` | `electron/catalog.cjs` | 产品人工修改留痕；来源冲突裁决 |
| `offline_reports`、`report_observations`、`report_observation_history`、`report_sync_logs` | `electron/offline-reports.cjs` | `offline_reports(id, store_id, report_type, source_sha, payload, created_at)`；`report_observations(natural_key, store_id, report_type, product_id, report_date, report_id, value_hash, payload)` |
| `product_ingestions`、`product_import_conflicts` | `electron/product-data.cjs` | 产品表导入批次与冲突 |
| `product_price_versions` | `electron/profit-center.cjs` | `(id, product_id, store_id, version, amount_minor, currency, source, created_at)` |
| `purchasing_plans`、`purchasing_receipts`、`shipment_groups`、`purchasing_reservations`、`purchasing_operations` | `electron/purchase-flow.cjs` | 采购计划/到货登记/货件组/预留；`purchasing_reservations.state` ∈ `reserved / packed / shipped / released` |
| `fba_shipments`、`fba_cartons`、`fba_allocations`、`fba_waybill_links` | `electron/shipments.cjs` | `fba_shipments(id, store_id, fba_id, version, payload, updated_at, UNIQUE(store_id, fba_id))`；`fba_cartons(…, physical_id, …, UNIQUE(store_id, physical_id))` |
| `tracking_waybills`、`tracking_events`、`tracking_pending`、`tracking_runs` | `electron/tracking.cjs` | `tracking_waybills(id, store_id, provider, tracking_no, state, payload, updated_at, UNIQUE(store_id, provider, tracking_no))`；`provider` ∈ `nextsls / choicexp-manual / manual` |
| `accounts`、`releases` | `electron/authorization-backup.cjs` | 授权库（`<数据目录>/authorization`），与主库分开备份 |
| 设置键（`settings` 表） | 多模块 | `freightRates:<storeId>`（头程运价）、`unitEstimateCosts:<productId>`、`actualReportCosts:<reportId>:<productId>`、`reportSchedule:<storeId>`、`manualStoreUpdate:<storeId>`、`storeReportQueue:<storeId>`、`freightOpening:<productId>`、`freightAvailability:<groupId>`、`replenishment:<id>` 等 |

- **商品身份是所有数据关联的钥匙。** 匹配规则（`electron/native-report-matching.cjs`
  的 `match()`、`electron/offline-reports.cjs` 的 `identity()`）：按 `sku`（含
  `previousSellerSkus`）+ `asin` 唯一匹配；一对多 = `ambiguous`，SKU 相同但 ASIN
  不同 = `identity_conflict`，无对应商品 = `unmatched`，同一商品在报告中多行 =
  `duplicate_product`。**必须先建商品档案（产品表导入），报表才能匹配。**

## 4. 数据导入入口

### 4.1 手动上传：亚马逊原生报表（`src/DataCenter.tsx` 的 `types` / `uploadHints`，`electron/amazon-native-reports.cjs` 的 `TYPES`）

| 报表类型 | 界面名 | 亚马逊后台下载路径（界面原文） | 后端解析 |
|---|---|---|---|
| `inventory` | FBA 库存 | 报告 → 配送 → 库存 → FBA 库存（补货报告），下载 `.txt` | 必含列 `snapshot-date / sku / fnsku / asin / available / inbound-quantity`；站点列 `marketplace`、币种列 `currency` 必须与店铺一致 |
| `economics` | 销售成本与费用 | 报告 → 业务报告 → SKU Economics（SKU 经济效益） | 多层表头：第 1 行首列必须是 `商品`，第 2 行第 2 列是 `SKU`；分组列 `净收入 / 销售额 / 配送费用 / 入库成本 / 销售费用 / 仓储成本 / 仓储成本 - AWD / 退货与回收操作 / 销售广告成本 / 其他费用和赔偿 / 所售商品成本（卖家提供）`；销售额分组内必有 `总销售额（收入） / 售出的商品总数 / 退款商品数量` |
| `traffic` | 销售与流量（按子商品） | 报告 → 业务报告 → 按子商品的详情页面销售和流量，下载 `.csv` | 必含含“子”+“ASIN”的列、`已订购商品数量`、`已订购商品销售额`；另取 `会话数…`、`页面浏览量…` |
| `sales-dashboard` | 销售控制面板（月度） | 报告 → 业务报告 → 销售控制面板，按月下载 | 必须是“商城汇总、本年至今”的 CSV；含 `销售快照`、`对比销售额 - 图表视图`、`对比销售额 - 表格视图`、`日期 … 本年至今 - …月 …日 …年`；按月取销售额/销量/上年同期 |
| `fees` | FBA 费用预估 | 亚马逊后台费用预览（Fee Preview）下载的 `.txt` | 宽松匹配：`sku` 列 + `asin` 列 + 费用列（优先含 `fba`+`fee`，其次 `estimated`+`fee`，再任意含 `fee` 的列）；费用是店铺原币/件 |
| `ads` | 广告商品报告（SP） | 亚马逊广告后台 SP 商品广告报告（Advertised Product），下载 JSON 或 CSV 后上传；ACOS=花费/广告带来的销售额（7 天点击归因） | 列别名：花费 `spend / cost / 花费 / 广告花费 / 广告费 / 总花费`；广告销售额 `sales7d / attributedSalesSameSku7d / sales / attributedSales / 广告带来的销售额 / 广告销售额 / 销售额`；SKU `advertisedSku / sku`，ASIN `advertisedAsin / asin`；报告最大跨度 31 天、保留 95 天 |

文件格式：XLSX / CSV / TSV / TXT / GZ。源表含公式时只读缓存值，需用户先核对并确认
（`confirmCachedFormulas`）。

### 4.2 手动上传：通用离线报表（`electron/offline-reports.cjs` 的 `TYPES` / `FIELDS`，`src/reportMapping.ts` 的 `fieldsByType`）

| 类别 `type` | 中文 | 统计口径 `basis`（必选其一） | 关键字段（`FIELDS`，见表后） |
|---|---|---|---|
| `inventory` | 库存 | `snapshot_sku_total`（快照 SKU 合计）或 `raw_archive` | `sku, fnsku, asin, date, available, inbound, fbaStock, currency` |
| `sales` | 销售 | `daily_sku_total`（逐日 SKU 合计）或 `period_sku_total`（期间 SKU 合计）或 `raw_archive` | `sku, fnsku, asin, date, sold, sales, refund, ads, commission, fba, storage, other, taxExpense, currency` |
| `logistics` | 物流/FBA | `event_id` 或 `raw_archive` | `sku, fnsku, asin, date, eventId, fbaId, status, currency` |
| `returns` | 退货 | `event_id` 或 `raw_archive` | `sku, fnsku, asin, date, eventId, returned, refund, currency` |
| `product` | 产品 | `event_id` 或 `raw_archive` | `sku, fnsku, asin, name, currency` |

字段中文名（`FIELDS` 原文）：`sku`=Seller SKU，`fnsku`=FNSKU，`asin`=ASIN，
`date`=报表日期 YYYY-MM-DD，`available`=FBA可售件数，`inbound`=Amazon在途件数，
`fbaStock`=FBA在库件数（平均库存口径需核实），`sold`=已售件数，`sales`=本币销售额，
`refund`=本币退款折扣，`ads`=本币实际广告费，`commission`=本币佣金，`fba`=本币FBA履约费，
`storage`=本币SKU仓储费，`other`=本币其他归属费用，`taxExpense`=本币税额费用，
`eventId`=事件/订单行唯一ID，`fbaId`=FBA货件号，`status`=源状态，`currency`=源报表币种（如有），
`returned`=退货件数，`name`=产品名称。

列名别名（`src/reportMapping.ts` 的 `aliases`）：`sku` 认 `sku / seller-sku /
seller sku / merchant sku / msku / 亚马逊sku`；`date` 认 `date / 报表日期 / 日期 /
snapshot-date / snapshot date`；`available` 认 `available / afn-fulfillable-quantity /
FBA可售 / FBA可售件数 / 可售数量`；`sold` 认 `sold / units ordered / units-ordered /
销量 / 已售件数`；`sales` 认 `sales / 销售额 / 本币销售额`；其余 `refund / ads /
commission / fba / storage / other / taxExpense / returned` 各认“本币…”中文列名。
**规则：** 库存快照必须明确 `available` 列，缺了不能写成零；日销量必须明确 `sold` 列；
期间汇总必须明确起止日期，不能摊成每日值；事件类去重必须有唯一 `eventId`；
单次业务导入最多 20,000 行；同一业务键重复 = `duplicate_in_file`，不能直接叠加；
报表币种必须与所选店铺一致；日期必须是真实 YYYY-MM-DD。

### 4.3 一键自动拉数：LinkFox（“一键更新” / `manual-store-update`）

- 入口：`electron/manual-store-update.cjs` 的 `ManualStoreUpdate`，`tasks(today, months=12)`。
  任务清单（按月 12 个月，默认 `months=12`，范围 1–24 个月）：

| kind | SP-API 报表类型 | 范围 / 口径 |
|---|---|---|
| `products` | `GET_MERCHANT_LISTINGS_ALL_DATA` | 当天；商品清单（SKU、ASIN、售价 `price`、数量 `quantity`、状态 `status`、上架时间 `listedAt`） |
| `inventory` | `GET_FBA_INVENTORY_PLANNING_DATA` | 当天快照；还会补档案的 `fnsku / asin`（缺失时才补） |
| `orders` | `GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL` | 近 90 天，分 3 段、每段 30 天（单次请求上限 30 天）；字段见 §5.1 |
| `returns` | `GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA` | 近 90 天 |
| `fees` | `GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA` | 当天快照，无日期范围 |
| `sales` | `GET_SALES_AND_TRAFFIC_REPORT` | 每月 1 个，自然月；`dateGranularity: DAY`，`asinGranularity: SKU`（老版沙特入口是 `CHILD`） |
| `economics` | `GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE` | 每月 1 个；**不是 SKU Economics 原表**，是结算报告按 SKU 汇总（见 §5.3 末尾） |

- 覆盖店铺：`electron/store-sync-client.cjs` 的 `stores`：`one`（ONE-XY，marketplaceId
  `A2VIGQ35RCS4UG`，AED）、`home`（STARRY BOX，同上）、`sa`（BIGO-SA，marketplaceId
  `A17E79C6D8DWNP`，SAR）。三家都能一键更新（`identify()` 按 `aliases` 匹配授权：
  ONE-XY 认 `ONEXY / BILABUYAE`，STARRY BOX 认 `STARRYBOX`，BIGO-SA 认 `BIGOSA`，region 须为 `EU`）。
- **但注意：** `electron/linkfox-reports.cjs` 的 `ReadOnlyReports` 是**只对沙特店**的
  快捷入口（`store = {id:'sa', name:'BIGO-SA', marketplaceId:'A17E79C6D8DWNP', currency:'SAR'}`，
  只认 `inventory` + `sales` 两类）。首页/数据中心的一键更新按钮走的是它；
  三店全量一键更新走 `manual-store-update.cjs` + `store-sync-client.cjs`。
  两者都经 LinkFox 网关 `https://tool-gateway.linkfox.com`（`linkfox.cjs` 的
  `endpoint()` 只允许这个地址），`/spApi/authorizedStores` 核对授权 +
  `/spApi/developerProxy` 代理 `reports/2021-06-30/reports`。密钥存在
  `linkfox-connection.json`（Windows 安全存储加密），或环境变量
  `LINKFOX_AGENT_API_KEY / LINKFOXAGENT_API_KEY`。`AGENTS.md` 提醒：LinkFox
  实时店铺/账号/报表操作“未验证”，不要在通用“继续”下执行。
- 节流：报表创建间隔 110 秒（`createSlot`），3 次/305 秒内最多建 3 个；轮询最多
  40 次、每次 30 秒；下载只认 `*.amazonaws.com` 的 https 地址，最大 64 MB。
- **自动更新计划：** `electron/offline-reports.cjs` 的 `schedule()` 默认
  `{time:'09:00', enabled:false, catchUp:'unverified_not_enabled', backendAuthorized:false}`；
  `requestUpdate()` 直接返回 `state:'blocked_by_policy'`，理由是“当前未专项授权本店
  店铺经营接口；没有发起后台、LinkFox经营接口或网络请求。可使用离线报表导入。”
  也就是说：**定时自动同步没有开通，实际能用的自动拉数只有用户手动点的“一键更新”。**

### 4.4 产品档案导入（必须先于报表）

- 入口：数据与导入 → 01 产品资料 → “使用你现在的工作SKU表”导入产品表（XLSX），
  或手动添加产品。`electron/product-data.cjs` 的 `TEXT` 字段与长度上限：
  `name` 500、`localSku`（马帮SKU）200、`sku`（亚马逊SKU）200、`asin` 10、`fnsku` 10、
  `category` 200、`listingTitle` 10000、`description` 120000、`keywordsA` 50000、
  `roots` 50000、`backendKeywords` 50000、`bulletsChinese` 120000、
  `supplierUrl` 8000、`sameSiteCompetitorUrl` 8000、`otherSiteReferenceUrl` 8000、
  `listedAt` 10、`weightNote` 500、`material` 2000、`color` 2000、`accessories` 10000、
  `features` 10000；数值：`productL/W/H`、`packageL/W/H`、`weightKg`、`quantityPerSet`。
  五点描述（`bullets`）必须是 5 段。
- 产品表源列（`product-data.cjs` 的 `profile()` / `profit-center.cjs` 的 `sourceQuote()`，
  按 Excel 列字母）：`A`=上架时间、`H`=重量、`I/J/K`=包装长/宽/高、`L`=体积、
  `M`=头程、`N`=进价 CNY、`O`=售价（原币）、`P`=FBA 原币费、`Q`=税、`R`=缓存利润 CNY、
  `S`=缓存利润率、`T`=Listing 标题、`U`=五点描述、`V`=五点中文、`W`=供应商链接、
  `X`=描述、`Y`=关键词 A、`Z`=roots、`AA`=同站竞品链接、`AB`=其他站参考链接（仅 home 店）。
  **注意：源表里的 `R/S` 缓存利润、以及 `O/P/Q/N/M` 等模板价/历史价，只作参考，
  不直接作为实际期间账务导入。** `catalog.cjs` 的 `save()` 只允许改
  `name / asin / fnsku / category / components / componentStatus / safetyDays / moq / cartonUnits`，
  不允许改商品身份或来源字段；`componentStatus==='verified'` 时必须逐项给 ERP 单品
  SKU + 实际数量（`components[].erpSku / quantity`）。

### 4.5 其他手动入口（不靠报表）

- 采购计划：`electron/purchase-flow.cjs` 的 `createPlan()`。每行必填：本店产品
  （已补齐亚马逊 SKU）、人工批准数量 `quantity`、马帮导入单价 `unitPrice`、
  供应商 `supplier`、实际采购仓库 `warehouse`、币种 `currency`（默认 CNY）、
  ERP 商品类型 `erpType`（1=库存SKU，2=组合SKU）、ERP SKU `erpSku`（默认取
  `localSku`）。导出马帮采购表即默认“马帮已下单”（`plan.orderSource`）。
- 利润核对：`electron/domain.cjs` 的 `commit()`，`kind` 为 `finance / replenishment /
  purchase` 时必须填资料来源 `source` 并确认 `confirmed===true`；`finance` 还要求
  币种与店铺一致、SKU 已建档、期间格式 `YYYY-MM`。
- FBA 发货：见 §5.4，全部人工登记（货件号、箱、分配、运单）。
- 物流轨迹：`electron/tracking.cjs`，运单 `provider` ∈ `nextsls / choicexp-manual /
  manual`；`nextsls` 可查轨迹，其余人工补录；预计到港/可售日（`arrivalEta /
  fbaAvailableEta`）是人工估计，需填依据。

## 5. 各业务的数据需求（字段级）

### 5.1 销量、销售额、订单（首页 / SKU中心）

首页 `Day` 类型（`src/types.ts`）：`{storeId, date, sales, profit, ads, orders, currency}`。
`sales-dashboard.cjs` 的 `computeForRange()` 逻辑：

- **逐日销售额/销量**优先用 `sales-dashboard` 类型报表的 `dashboard.daily[]`
 （`{date, sales, units, orderItems}`，金额是**分**，即原币 ×100 的整数）。
  只有当所选期间的**每一天都有记录**（`daily.length === expected` 天数）时才用逐日口径；
  否则回退到月度汇总（`dashboard.monthly[]`：`{month, sales, units, priorSales, priorUnits}`），
  且要求期间是整月（`start` 为某月 1 日，`end` 为月末或报表期末）。
- **订单数**不用 `totalOrderItems`，用去重订单数（`home-metrics.cjs` 的
  `distinctOrderCount()`）：同一 `amazon-order-id` 只计一次；只计 `purchaseDate`
  落在期间内、状态不含 `cancel` 的订单行；按店铺时区（AE `Asia/Dubai`，SA `Asia/Riyadh`）
  把 UTC 时间戳换算成本地日期。没有订单报告时才退回行项目数。
- **订单明细**（一键更新 `orders`，`store-sync-import.cjs`）：列名原样——
  `amazon-order-id`、`purchase-date`、`last-updated-date`、`order-status`、
  `quantity`、`item-price`、`currency`、`sales-channel`、`fulfillment-channel`、
  `sku`、`asin`。金额不完整时该日不计入完整口径（`complete` 标志）。
- **LinkFox 沙特销售报告**（`linkfox-import.cjs` 的 `saleDashboard()`）：
  必须是 `reportType === GET_SALES_AND_TRAFFIC_REPORT`、`marketplaceIds === [A17E79C6D8DWNP]`、
  `dateGranularity === 'DAY'`；逐日行 `salesAndTrafficByDate[].salesByDate`：
  `orderedProductSales.amount / currencyCode`（须为 SAR）、`unitsOrdered`、
  `totalOrderItems`；按 ASIN 行 `salesAndTrafficByAsin[]`：`salesByAsin.unitsOrdered`、
  `orderedProductSales.amount`、`trafficByAsin.sessions`，父体标记 `isParent`
 （有 `parentAsin` 且无 `childAsin`）。
- **销售控制面板月度报告**（`sales-dashboard.cjs` 的 `parse()`）：必须是“商城汇总、
  本年至今”的 CSV；`periodStart` 固定为当年 1 月 1 日；月度行含销售额/销量/上年同期。
- **风险：** LinkFox 销售只认沙特店、只认逐日口径；AE 两店没有这个快捷入口，
  要靠手动上传 SalesDashboard / Economics / 订单报告，或三店一键更新。
  期间缺一天，首页就退回月度口径或显示空白，不会自动补零。

### 5.2 库存、补货（补货与库存）

- 库存快照（`inventory`）：`date`（快照日 YYYY-MM-DD）、`sku / fnsku / asin`、
  `available`（FBA可售件数，必填）、`inbound`（Amazon在途件数）、`fbaStock`
  （FBA在库件数）。`offline-reports.cjs` 的 `preview()`：快照口径
  `snapshot_sku_total` 必须明确 `available` 列。
- 补货核对（`domain.cjs` 的 `replenish(input)`），输入字段原样：
  `sku`（必填）、`monthSales`（近30天销量）或 `adjustedMonthSales`（调整月销）、
  `available`（FBA可售）、`inbound`（Amazon未入库货）、`extraPurchased`
  （报告外已购未到）、`distinctBatches===true`（确认未入库货与额外采购不重复）、
  `mode==='template90_110'`、`storeId`。
  公式：`daily = monthSales/30`；`total = available+inbound+extraPurchased`；
  目标天数 AE 90 天、SA 110 天（`isSaudi(storeId)`）；`need = ceil(目标天数×daily − total)`；
  `recommendedQuantity = min(need, ceil(daily×30))`。缺任一项或模式不对，
  返回 `complete:false`，`recommendedQuantity:null`，只给 `missing` 清单。
  注意：覆盖天数包含已购未到，不额外叠加运输周期；建议值需人工审批。
- 补货计划2（`electron/replenishment.cjs`）：六段实测 lead time 的时间戳来源——
  建计划→下单（计划 `createdAt` → 计划行/计划 `orderedAt`）、备货（`orderedAt` →
  该行最后到货登记 `purchasing_receipts.recordedAt`，分批到货以后几批为准）、
  到货→装箱完成（最后到货 → 货件组 `packedAt`）、装箱→发运（`packedAt` →
  `shipment_groups.shippingDate`）、发货→首条轨迹（`shippingDate` → 海运单号最早
  物流轨迹 `eventTime`）、在途/清关/入库（首条轨迹 → 批次实际可售日；无轨迹时为
  发货日→可售日）。实际可售日优先用核对登记的 `config.actualDate`，其次用轨迹里
  “签收/入仓”事件日，两者都没有就待补，不编数字。运输方式统一是普船，不分物流商/线路。
  清关没有独立时间戳，只在轨迹原文出现清关/签收/入仓字样时才拆分段参考值。
  `fbaAvailableEta / arrivalEta` 是预计值，不作实测。
- 首页库存周转：`home-metrics.cjs`，环满格按周转 30 折算（2026-11-11 已定，原来是 2）；
  周转 = 库存总量 / 近30天销量（件数口径）；演示区无件数口径。

### 5.3 利润（产品利润中心）

两套并行实现，口径一致（`electron/domain.cjs` 的 `finance()` 与
`electron/profit-center.cjs` 的 `actual()`；后者是利润中心当前用的）：

**利润公式（原币分 / CNY 分，视函数而定）：**

```
经营利润 = (销售额 − 退款与折扣) × 汇率
           − (佣金 + FBA履约费 + 其他费用 + 仓储费 + 广告费) × 汇率
           − 已售采购成本 COGS − 已售头程
           + 人民币调整
净利润 = 经营利润 − 税额费用
利润率 = 净利润 / 净销售额（(销售额−退款)×汇率）
```

**必填输入（`actual(input)` / `finance(input)` 的字段名原样）：**

| 字段 | 中文 | 来源 | 必填？ |
|---|---|---|---|
| `sku` | 本店 SKU | 商品档案 | 必填，禁止跨商品混算 |
| `period` | 核算年月 `YYYY-MM` | 用户选 | 必填 |
| `currency` | 店铺原币（AED/SAR） | 店铺 | 必填，须与店铺一致 |
| `cnyPerCurrency` | CNY 兑换率（有来源） | 人工填，有来源 | 必填；缺了利润为 null |
| `soldUnits` | 已售数量（件，整数） | 销售报表 | 必填 |
| `sales` | 销售额（原币） | 销售/Economics 报表 | 必填 |
| `refund` | 退款与折扣（原币） | 同上 | 必填 |
| `commission` | 佣金（原币） | 同上 | 必填 |
| `fba` | FBA履约费（原币） | 同上 | 必填 |
| `storage` | 仓储费用（原币） | 同上；或用分摊：`storageBillCny`（仓储账单 CNY）+ `skuVolumeDays`（本 SKU 体积×存储时间）+ `totalVolumeDays`（全部体积×存储时间）+ `storageAllocationSource` | 必填（二选一） |
| `other` | 其他费用（原币） | 同上 | 必填 |
| `costBatches[]` | 采购批次：`{quantity, unitCostCny, source}`（同 SKU，数量≥1，单价 CNY，最多两位小数） | 采购计划/到货/期初（`batch-costing.cjs` 的 `shipmentLots` / `freightOpening`） | 必填；COGS = 加权平均单价 × 已售件数；已售 > 已知批次总量时缺口待补 |
| `soldFreightCny` | 已售对应头程 CNY | 头程分摊（见下） | 必填 |
| `ads` | 实际广告费（原币） | 广告报告 | 可缺，缺了按 5% 暂估（见下） |
| `adsCoveredSales` | 实际广告费覆盖销售额（原币） | 广告报告 | 有 `ads` 且部分覆盖时必填，且 ≤ 总销售额 |
| `taxExpense` | 已核实计入费用的税费（原币） | 人工 | 必填其一：要么填税费，要么声明 `taxIncludedInNetSales===true`（税已含在净销售额里） |
| `adjustmentsCny` | 人民币调整（有符号，最多两位小数） | 人工 | 可选；非零时必须填 `adjustmentSource`（凭据 + 退款不重复扣除依据） |

**广告暂估规则（两处一致）：** 未覆盖销售额 = 有覆盖额时 `销售额 − adsCoveredSales`，
无广告费时 = 全部销售额；暂估广告 = 未覆盖 × 5%。`ads` 缺失时状态为
`estimated_5_percent`，部分覆盖时为 `partial_estimate_5_percent`，
全覆盖时为 `actual` / `source_entered`。

**采购成本 COGS：** 加权平均（`cost/quantity × sold`），按已售结转；
期初成本在 `batch-costing.cjs` 的 `saveOpening()`：`{date, units, unitHeadCny, source}`，
每 SKU 只登记一次。**模板价/历史价不作实际成本。**

**头程：** `shipment-freight.cjs`，运价是 CNY/立方米，按店铺、按生效日期分段。
初始值（2026-11-12 用户给的表，`initialByStore`）：
ONE-XY（`one`）：680（起）→1320（2026-03-01）→1200（2026-06-28）→1370（2026-08-08）
→1530（2026-08-18）→1450（2026-09-20）→1500（2026-10-22）；
BIGO-SA（`sa`）：1100（起）→1340（2026-02-01）→1540（2026-05-15）→1690（2026-07-28）
→1800（2026-08-14）。**STARRY BOX（`home`）没有初始运价表**，须人工保存后才有。
期间运价 = 期间内每天的当日生效运价按天数加权平均；期间内任何一天无适用运价则返回 null。
单件头程 = 包装体积（`packageL×packageW×packageH`，单位换算）× 运价；
实际利润用 `actualReportCosts` 里按批次核对的单件头程。

**Economics 原表 vs 结算汇总：** 利润中心优先用手工上传的 SKU Economics 原表
（`sales-dashboard.cjs` 的 `pickEconomics()`：同期间有原表就选原表）。
一键更新的 `economics` 是结算报告 `GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE`
按 SKU 汇总（`store-sync-import.cjs` 的 `settlementEconomics()`）：必填列
`transaction-type / sku / currency / amount`；`units / grossSales` 是 Order/Refund
行净额（退款件数为负），`净收入` 是该 SKU 全部结算行 `amount` 之和，
`returned` 是退款件数；**配送费/销售费/仓储费/广告费不在结算文件里按 SKU 拆分，
留空**；无 SKU 的行（如订阅服务费）只计 `summary.unassignedAmount`，不归属商品。
`actual-profit.cjs` 的 `calculate()` 用的是结算口径：`units / netIncome / grossSales /
purchaseCny（单件进价）/ headCny（单件头程）`。

**售价：** `product_price_versions` 表，人工改价需填来源 `source`，版本号递增；
当前售价优先取人工价，其次取 LinkFox Listing 价（`linkfoxListing.price`），
再取产品表历史价（列 O）。单件测算（`estimate()`）输入：`priceLocal / purchaseCny /
firstLegCny / fbaLocal`，缺一不可；收入 CNY 按 `priceLocal × 1.8` 粗算（界面写明
“单件测算 · 汇率1.8”，不是实际汇率）。

**生命周期利润：** 需起售月至截止月的每个月都有完整 `finance` 记录，缺一个月
就返回 `needs_period_sources` 并列出缺失月份，不估算。

### 5.4 FBA 发货（FBA货件中心）

- 货件（`shipments.cjs` 的 `saveShipment()`）：`fbaId`（必填，正则
  `^FBA[A-Z0-9-]{3,40}$`，不区分大小写）、`source`（必填，来源）、
  `amazonReference`（Amazon 货件追踪编号，单独填，最长 150 字符；预检缺了会提示）、
  `warehouse`（仓库）。状态初始 `local_record`，`amazonReceiptVerified=false`，
  `sellableVerified=false`。
- 真实箱（`saveCarton()`）：`physicalId`（必填，唯一）、`source`（必填）、
  箱内明细 `items[]`（每项 `sku` 必填且不重复、`quantity` 正整数、`fnsku` 10 位、
  `name`、`unitDeclaredUsd` 单件申报 USD + `declaredSource`——沙特店必填）、
  实测 `weightKg` + `lengthCm / widthCm / heightCm`（均 >0，必填），
  体积 `volumeM3 = 长×宽×高 / 1e6`。
- 分配（`allocate()`）：货件 + 箱 + SKU + `quantity`；分配总量不得超过箱内数量；
  同箱关联多个 FBA 货件时须补真实内箱与箱贴关系，不能重复导出整箱。
- 运单（`linkWaybill()` + `tracking.cjs`）：海运单号 `seaWaybill`（`shipment_groups`
  表，`UNIQUE(store_id, sea_waybill)`）、`provider`（`nextsls / choicexp-manual /
  manual`）、`trackingNo`、轨迹事件（`eventTime / eventInfo`）、预计到港
  `arrivalEta` / 预计可售 `fbaAvailableEta`（人工估计，需填依据；可售日不得早于到港日）。
  货件组字段：`state`、`packedAt`（装箱确认日）、`shippingDate`（发物流日）、
  `freightRateLock.rateCnyM3`（锁定的头程运价）、`freightAllocation[]`（按 FBA 货件/
  商品的头程分摊：`unitHeadCny / volumeM3 / quantity`）。
- 发货文件：`src/ShipmentFiles.tsx`（28,706 字节）、`electron/shipment-workflow.cjs`
  （23,920 字节）、`electron/native-scripts/shipment_documents.py`（22,401 字节）；
  技能包里有 AE-Choicexp 与 SA-义特两套发货模板/校验脚本
  （`amazon-ae-choicexp-shipment`、`amazon-sa-yite-shipment`，含 `FBA-Order-Template.xls` /
  `义特物流.xls` 与 `batch-schema.md / file-contract.md / validate_batch.py`）。
  **FBA 发货报告在 Seller Central 的下载路径，仍待用户核实**（此前待办）。

### 5.5 广告

- 首页 ACOS = SP 商品广告报告的广告花费 / 广告带来的销售额（7 天点击归因，
  `sales7d`，无时用 `attributedSalesSameSku7d`）；没有广告报告时 ACOS 留空。
  TACOS = 费用报告的广告花费 / 总销售额，仍用总销售额另算。
- 广告报告只解析已下载的文件，不发起广告接口调用（`electron/ads-reports.cjs`
  原文：“LinkFox 广告报告的 developerProxy 信封未包含在已导入的技能文件里，
  实时抓取需另行核对接口后接入，当前以手工上传为准。”）。
- 利润里的广告费见 §5.3：实际广告费 + 未覆盖销售额 5% 暂估。

### 5.6 商品目录 / 新品 / 选品

- 商品档案字段见 §4.4。另有 `safetyDays`（安全天数）、`moq`、`*cartonUnits*`（箱规）、
  `components` / `componentStatus`（`pending / unverified / verified`）、
  `previousSellerSkus`（曾用 SKU，用于匹配）。
- 新品中心（`electron/new-product-intakes.cjs`）：intake、关键词表（XLSX/CSV）、
  产品图片（jpg/jpeg/png/webp，≤12 MB）；`main.cjs` 明确拒绝读取含
  `ziniao / zclaw / 紫鸟 / superbrowser` 的文件路径。
- 选品中心暂缓（见 §2），候选在 `sourcing_candidates` 表。

### 5.7 汇率、币种、时区

- 店铺币种：AE 两店 AED，SA 店 SAR；报表币种必须与店铺一致，否则报错。
- 时区：AE `Asia/Dubai`（UTC+4），SA `Asia/Riyadh`（UTC+3）；首页/订单去重按店铺
  时区换算；工作台界面时间用 `Asia/Shanghai` 显示。
- 汇率：实际利润每期人工填 `cnyPerCurrency`（有来源）；单件测算写死 1.8；
  演示 fixture AED 1.9 / SAR 1.8（非市场汇率，仅演示）。
  **仓库里没有汇率接口、没有自动汇率更新。**

## 6. 完整运行数据清单表

“必填”指缺了该模块就显示空白/待补/算不出，不是“程序会报错退出”。
“更新频率”是代码要求的最小口径，不是建议值。

| 模块 | 字段 | 来源 | 必填/可选 | 更新频率 | 备注（不准/缺失风险） |
|---|---|---|---|---|---|
| 店铺 | 店铺 id/名称/站点/币种/时区 | 内置 `storeProfiles`（one/home/sa） | 必填（内置） | 一次 | 新增店铺要改代码/加档案；LinkFox 授权名须与 `aliases` 匹配 |
| 商品档案 | 马帮SKU `localSku`、亚马逊SKU `sku`、ASIN、FNSKU、产品名称、类目、上架时间、包装尺寸、重量、每套数量、五点描述、供应商链接 | 产品表 XLSX 导入 / 手动添加 | 必填（`name`、`sku` 核心） | 有新品/改身份时 | 报表匹配全靠它；ASIN/FNSKU 须 10 位大写字母数字；组件未核验不能按普通单品导出采购 |
| 商品档案 | 售价（列 O）、FBA费（列 P）、税（列 Q）、进价 CNY（列 N）、头程（列 M）、体积（列 L）、缓存利润（列 R/S） | 产品表源列 | 可选/参考 | 同上 | 只作参考，不作实际账务；实际售价以 `product_price_versions` 为准 |
| 库存 | 快照日期、SKU、FNSKU、ASIN、FBA可售 `available`、在途 `inbound`、在库 `fbaStock`、币种 | FBA 库存报告（手动 `.txt` / LinkFox 一键） | `available` 必填，其余可选 | 每次看库存时（快照日） | 缺 `available` 不能写零；快照日与销量期间要对齐，否则周转/覆盖天数不准 |
| 销量/销售额 | 日期、SKU、已售件数 `sold`、销售额 `sales`、币种 | 销售报表（`daily_sku_total` / `period_sku_total`）、SalesDashboard、LinkFox 销售报告 | 必填 | 每日（逐日）或每月（月度） | 逐日口径要求期间每一天都有记录，缺一天就退回月度或空白；LinkFox 只认沙特逐日报告 |
| 销量/销售额 | 订单明细 `amazon-order-id / purchase-date / order-status / quantity / item-price` | All Orders 报告（一键更新，90 天/3 段） | 可选（用于去重订单数） | 90 天滚动 | 金额不完整的行不计入完整口径；取消单不计 |
| 退货 | 退货件数 `returned`、退款 `refund`、订单 id、退货日期、原因、处置 | FBA 退货报告（一键更新 90 天）/ 通用 `returns` 报表 / Economics 分组 `退货与回收操作` | 退款必填（利润用），退货件数可选 | 每月 | 结算汇总里退款件数为负，要与 Economics 原表口径区分 |
| 费用（利润） | 佣金、FBA履约费、仓储费、其他费用、退款折扣（均为原币） | SKU Economics 原表（优先）/ 结算汇总（缺口） | 必填 | 每月（按 `YYYY-MM`） | 结算汇总不拆配送/销售/仓储/广告费，留空；原表优先 |
| 费用（利润） | 税额费用 `taxExpense` 或税已含声明 | 人工 | 必填其一 | 每月 | 税口径未核时利润为 null |
| 采购成本 | 采购批次 `{quantity, unitCostCny, source}`、期初 `{date, units, unitHeadCny, source}` | 采购计划/到货登记/期初登记 | 必填 | 每批 | 已售 > 已知批次时缺口待补；禁止跨 SKU 混算 |
| 头程 | 运价 CNY/m³（按店、按生效日分段）、包装体积、单件头程 | 人工保存运价表（初始值见 §5.3）+ 批次分摊 | 必填 | 运价变时 / 每批 | STARRY BOX 无初始运价；期间内任一天无运价则整段为 null |
| 广告 | 实际广告费、覆盖销售额、广告带来的销售额（7 天归因）、花费 | SP 广告报告（手动上传；实时抓取未接入） | 广告费可缺（5% 暂估） | 每月 / 报告期 31 天内 | 无广告报告时 ACOS 留空；暂估 5% 不是实际花费 |
| 汇率 | `cnyPerCurrency`（有来源） | 人工填 | 必填（实际利润） | 每月 | 无自动汇率；单件测算写死 1.8 |
| FBA发货 | FBA货件号、Amazon 追踪编号、仓库、来源 | 人工登记 | 必填 | 每批 | 货件号格式 `FBA…`；缺追踪编号预检会提示 |
| FBA发货 | 真实箱：箱标识、SKU/数量/FNSKU/单件申报 USD+来源、实测毛重与三边尺寸 | 人工登记 | 必填 | 每批 | 沙特店缺 FNSKU/申报值不能导出 |
| FBA发货 | 海运单号、物流轨迹事件、预计到港/可售日 | 人工登记 + 物流查询（`nextsls`）/人工补录 | 运单必填，轨迹可选 | 每批 | 预计日不是实测日；清关无独立时间戳 |
| 采购 | 批准数量、马帮导入单价、供应商、仓库、币种、ERP 类型/ERP SKU、批准依据 | 人工（采购计划） | 必填 | 每批 | 导出马帮表即默认已下单；单价标注“未核验成本” |
| 补货 | 近30天销量、FBA可售、在途、已购未到、不重复确认 | 销售+库存报表 + 人工确认 | 必填 | 每次补货核对 | 目标 AE 90 天 / SA 110 天；建议量上限为 30 天销量 |
| 首页 KPI | 上述销量/利润/广告/订单/库存的汇总 | 各报表汇总 | — | 与报表同频 | 任一来源缺失，该 KPI 留空，不补零 |

## 7. 马帮能对应上哪些工作台数据（对应建议，未在仓库验证）

> 本节是“马帮页面 → 工作台字段”的对应建议，**仓库里没有马帮接口，无法验证**，
> 需江逐项确认。马帮 ERP 里数据分散在多个页面（江已确认“不止这一个地方”），
> 不能只拉一个页面。

| 工作台需要 | 马帮里可能的对应位置（待确认） | 备注 |
|---|---|---|
| 商品档案（马帮SKU、ASIN、FNSKU、产品名、上架时间） | 商品管理 / 在售 Listing 页（截图已见：MSKU/FNSKU、ASIN、品名/SKU、日均销量、上架时间、库龄） | 截图页有“下载”按钮，529 条；但那是 Listing 口径，不是订单口径 |
| 销量、销售额（按天/按 SKU） | 销售 / FBA订单页、订单列表 | 要订单明细（订单号、下单时间、SKU、件数、金额、状态），不要只拉汇总 |
| 库存（FBA可售、在途、在库） | 库存 / FBA 库存页 | 要快照日期，缺快照日无法对齐销量期间 |
| 采购成本、供应商、仓库 | 采购管理 / 商品采购页 | 工作台采购行要 `erpSku / supplier / warehouse / unitPrice / currency` |
| 头程运费 | 物流 / 头程费用页（或手工运价表） | 工作台已有分段运价表（§5.3），马帮数据只能作核对，不能直接覆盖 |
| 利润费用（佣金、FBA费、仓储、广告、税） | 马帮财务 / 费用页（如有） | 如马帮没有按 SKU 拆的费用，仍需 Seller Central 的 SKU Economics 原表 |
| 广告花费 | 马帮没有；用 LinkFox / 亚马逊广告后台 SP 报告 | 见 §5.5 |

**关键缺口：** 马帮订单 API（`order-get-order-list-new`）需要主账号 AppKey，
江已确认拿不到；开放平台登录也提示“无管理权限”。因此现阶段可行的马帮路线
是浏览器自动导出（`mabang_browser_pull.py`），按页面逐个下载再汇总，
而不是 API 一次拉全。先做哪几个页面，等江按 §6 的清单排优先级。

## 8. 不确定的地方（需江 / Codex 确认）

1. **LinkFox 一键更新的实际覆盖**：代码上三店都能更新，但 `linkfox-reports.cjs`
   的快捷入口只写了沙特店。实际在用的按钮走哪条路、AE 两店的一键更新是否真的
   跑通过，需要真机核对（此前待办：Codex 真机验证 37–43 项）。
2. **旧月销售记录**：此前待办写“删除后用 LinkFox 一键更新重建”。按 §5.1，
   LinkFox 销售是逐日报告 + 月度报告，删除后能否完整重建、期间是否对得上，
   未在代码里看到保证。
3. **FBA 发货报告在 Seller Central 的下载路径**：此前待办“待用户核实”，
   代码里没有写死路径。
4. **汇率来源**：实际利润每期都要人工填 `cnyPerCurrency`，江现在用的是哪个
   汇率（银行/换汇/固定值）、按天还是按月，未在仓库里找到。
5. **STARRY BOX 的头程运价**：初始表只有 ONE-XY 和 BIGO-SA，没有 `home` 店，
   需确认现在用的是人工保存的哪份运价。
6. **同事版（`colleague` distribution）**：店铺改为从库里读、授权地址未定
   （A/B 方案待定），本文按管理员版核查，同事版的数据需求可能不同。
7. **马帮各页面的字段名**：本文 §7 只是对应建议，马帮在售 Listing / FBA订单 /
   库存等页面的实际列名、导出文件名、筛选条件，需江发截图或导出样表后才能定。
8. **演示数据**：`makeDemo()` 的 6 个虚构商品、60 天虚构销量、汇率 AED 1.9 /
   SAR 1.8 均为演示，与实际数据隔离；不要把演示数字当经营数据。

## 9. 证据索引（关键文件路径与函数名，原样）

- 导航：`src/App.tsx:21` `nav`；`src/App.tsx:49` `route=ui.route??'home'`。
- 店铺：`electron/fixtures.cjs` `storeProfiles`（`one / home / sa`）、`isSaudi`。
- 存储：`electron/store.cjs` `schema()` / `Vault`（`commerce.sqlite`，`node:sqlite`）；
  `electron/domain.cjs` `ensure()`（`business_records`）；`electron/imports.cjs`
  `ensure()`（`import_batches / import_sources / catalog_products / import_records`）；
  `electron/offline-reports.cjs` `ensure()`（`offline_reports / report_observations`）。
- 报表类型：`electron/offline-reports.cjs` `TYPES={inventory, logistics, sales, product, returns}`、
  `FIELDS`；`electron/amazon-native-reports.cjs` `TYPES={inventory, economics, traffic,
  sales-dashboard, fees, ads}`；`src/DataCenter.tsx` `types / uploadHints / autoOnlyHints`；
  `src/reportMapping.ts` `aliases / fieldsByType / suggestMapping()`。
- 利润：`electron/domain.cjs` `finance(input)`；`electron/profit-center.cjs`
  `actual(input)`、`estimate(input)`、`sourceQuote(p)`、`price()`、`savePrice()`、
  `productRow()`、`list()`；`electron/actual-profit.cjs` `calculate(x)` / `list()` / `costs()`；
  `electron/batch-costing.cjs` `saveOpening()` / `saveAvailability()` / `shipmentLots()`。
- 补货：`electron/domain.cjs` `replenish(input)`（目标 AE 90 / SA 110）；
  `electron/replenishment.cjs` 六段 lead time、`safeLead()`（75 分位，样本 <3 加 2 天）。
- 销售/首页：`electron/sales-dashboard.cjs` `parse()` / `inspect()` / `forRange()` /
  `computeForRange()` / `pickEconomics()` / `pickAds()` / `reportFinancial()`；
  `electron/home-metrics.cjs` `distinctOrderCount()` / `turnoverRingFraction()`（满格 30）。
- LinkFox：`electron/linkfox.cjs` `LinkFox` / `endpoint()` / `TARGETS`（`sa` BIGO-SA、
  `home` STARRY BOX）；`electron/linkfox-reports.cjs` `ReadOnlyReports`（只认 `sa`，
  `kinds={inventory: GET_FBA_INVENTORY_PLANNING_DATA, sales: GET_SALES_AND_TRAFFIC_REPORT}`，
  `marketplaceId: A17E79C6D8DWNP`）；`electron/store-sync-client.cjs` `stores` /
  `kinds`（7 类报表）/`StoreReports`；`electron/store-sync-import.cjs`
  `sales() / settlementEconomics() / commit()`；`electron/linkfox-import.cjs`
  `saleDashboard()`；`electron/manual-store-update.cjs` `ManualStoreUpdate` /
  `tasks()` / `orderChunks()`（30 天分段）。
- 采购/马帮出口：`electron/purchase-flow.cjs` `createPlan()` / `prepareExport()`
  （`erpSku / erpType / unitPrice / supplier / warehouse`，`priceMeaning:
  'import_value_not_verified_cost'`）；`electron/main.cjs` `purchase.template.export`
  （“选择本店马帮买货数量模板”，输出 `马帮买货数量-已审核-<storeId>.xlsx`）。
- FBA：`electron/shipments.cjs` `saveShipment() / saveCarton() / allocate() / linkWaybill() /
  preview()`；`electron/shipment-freight.cjs` `initialByStore` / `rates() / rateOn() /
  periodRate()`；`electron/tracking.cjs` `create() / sync() / manual() / eta()`。
- 广告：`electron/ads-reports.cjs` `parseAdsTable()`（ACOS，7 天归因）；
  `electron/fba-fees.cjs` `parseFeePreview()`。
- 商品：`electron/product-data.cjs` `profile()` / `validate()`（`TEXT` 长度上限、
  列字母 A–AB）；`electron/catalog.cjs` `save()`（只允许改 9 个字段）。
- 约束：`AGENTS.md`（离线、外部请求拒绝、不碰紫鸟/店铺环境/凭证、不调 SP-API/Ads API）；
  `electron/offline-reports.cjs` `requestUpdate()`（`blocked_by_policy`）、
  `schedule()`（09:00，默认未启用）。
