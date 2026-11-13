# 工作台 × 马帮 数据对照表（v0.2）

> 依据：`WORKBENCH_DATA_REQUIREMENTS.md`（仓库 d3a1598 只读审计）。
> 店铺写死 3 家：`one` ONE-XY（AE/AED/Asia/Dubai）、`home` STARRY BOX（AE/AED/Asia/Dubai）、
> `sa` BIGO-SA（SA/SAR/Asia/Riyadh）。币种必须与店铺一致，否则工作台导入报错。
> 商品身份钥匙：`sku`（亚马逊 SKU）+ `asin`，马帮 SKU 是 `localSku`，三者必须先对齐，
> 报表才能匹配；无档案 = `unmatched`。
>
> 更新频率分清三档，不要混成“一次性”：
> - **每日增量**：订单/销量。每天只拉新增/变更的订单，`last_sync_time` 往前推，订单按
>   `platformOrderId` 去重，销量按天汇总不重复。
> - **每日快照**：库存、Listing、FBA 货件状态。每天取一张当日快照，同一天重复跑是覆盖，
>   不是叠加；缺哪天快照，那天的库存/周转就对不齐。
> - **每月 / 每批 / 人工**：费用、汇率、采购批次、头程运价。马帮没有或不拆这些，
>   仍要靠 Seller Central 原表或人工填，不能编数。

## 1. 经营首页（home）— 营业额、订单数、库存周转

| 需要字段 | 马帮来源页面 / API | 更新频率 | 必填 | 备注 |
|---|---|---|---|---|
| `store_id, date, sales, units, orders, currency`（逐日） | 销售 / FBA订单页、订单列表；API `order-get-order-list-new`（`updateTimeStart/End`，`status=[6,7]`，`maxRows=1000` 分页） | 每日增量 | 必填 | 首页逐日口径要求期间**每一天都有记录**，缺一天就退回月度或空白，不补零。订单数按 `amazon-order-id` 去重、取消单不计、按店铺时区换算日期 |
| 订单明细 `platformOrderId, purchase-date, order-status, quantity, item-price, sku, asin` | 同上，订单列表明细 | 每日增量 | 必填 | 金额不完整的行不计入完整口径 |
| 库存总量 / 近30天销量（周转） | 库存快照 + 销量汇总（见 §2） | 每日快照 + 每日增量 | 必填 | 周转 = 库存总量 / 近30天销量（件数）；满格按周转 30 折算 |
| 广告花费 / ACOS / TACOS | **马帮没有**；LinkFox / 亚马逊广告后台 SP 报告 | 每月 / 报告期 31 天内 | 可缺（留空） | LinkFox 只留广告；无报告时 ACOS 留空，不估算 |

## 2. 库存与补货（procurement）

| 需要字段 | 马帮来源页面 / API | 更新频率 | 必填 | 备注 |
|---|---|---|---|---|
| `date, sku, fnsku, asin, available, inbound, fba_stock, currency`（快照） | 库存 / FBA 库存页；API `stock-do-search-sku-list-new` + `stock-get-stock-quantity` | 每日快照 | `available` 必填 | 缺 `available` 不能写零；快照日要与销量期间对齐 |
| 近30天销量 `monthSales`（按 SKU） | 订单历史汇总（`orders_daily` 任务算出） | 每日增量（滚动30天） | 必填 | 补货公式：`daily=monthSales/30`，目标 AE 90 天 / SA 110 天，`need=ceil(目标×daily − (available+inbound+extraPurchased))`，建议量 `min(need, ceil(daily×30))` |
| 已购未到 `extraPurchased` + 不重复确认 | 采购管理 / 商品采购页；工作台人工确认 | 每批 / 每次补货核对 | 必填 | 须确认与 `inbound` 不重复，否则 `complete:false` |
| 六段实测 lead time（建计划→下单→备货→到货→装箱→发运→首条轨迹→在途/清关/入库） | FBA 货件 + 物流轨迹（见 §4）+ 采购到货登记 | 每批实测 | 必填 | 安全值取实测 75 分位，样本 <3 加 2 天；**按单 SKU / 单品具体算**，不共用一个统一天数；预计日（`arrivalEta/fbaAvailableEta`）不是实测日 |
| 采购批次 `{quantity, unitCostCny, source}` | 采购管理页；工作台人工登记 | 每批 | 必填（利润 COGS 用） | 已售 > 已知批次总量时缺口待补，禁止跨 SKU 混算 |

## 3. 产品利润中心（finance）— 算法不动，换马帮数据

利润公式（工作台原样，不改）：
`经营利润 = (销售额−退款)×汇率 − (佣金+FBA履约费+其他+仓储+广告)×汇率 − COGS − 已售头程 + 人民币调整`
`净利润 = 经营利润 − 税额费用`，`利润率 = 净利润 / 净销售额`

| 需要字段 | 马帮来源页面 / API | 更新频率 | 必填 | 备注 |
|---|---|---|---|---|
| `sku, period(YYYY-MM), currency` | 商品档案 + 订单汇总 | 每月 | 必填 | 禁止跨商品混算；币种须与店铺一致 |
| `soldUnits, sales, refund`（按月按 SKU） | 订单历史（马帮订单） | 每日增量 → 按月汇总 | 必填 | 这就是 LinkFox 不准要换掉的部分：马帮是实际订单，LinkFox 是广告归因汇总 |
| `commission, fba, storage, other`（按 SKU） | 马帮财务 / 费用页（如有）；如无，按 SKU 拆不开 | 每月 | 必填 | 如马帮没有按 SKU 拆的费用，仍需 Seller Central SKU Economics 原表；结算汇总不拆配送/销售/仓储/广告费，留空 |
| `costBatches[]` 采购批次 | 采购管理页 | 每批 | 必填 | COGS = 加权平均单价 × 已售件数 |
| `soldFreightCny` 已售头程 | 头程分摊（货件体积 × 分段运价，见 §4） | 每批 / 每月 | 必填 | STARRY BOX 无初始运价表，须人工保存 |
| `ads, adsCoveredSales` | **马帮没有**；LinkFox SP 报告 | 每月 | 可缺 | 缺了按未覆盖销售额 5% 暂估，状态标 `estimated_5_percent`，不是实际花费 |
| `taxExpense` 或税已含声明 | 人工 | 每月 | 必填其一 | 税口径未核时利润为 `null`，显示待补 |
| `cnyPerCurrency` 汇率（有来源） | 人工填 | 每月 | 必填 | **无自动汇率**；单件测算写死 1.8 不是实际汇率 |
| 售价 `priceLocal` | 在售 Listing 页（真实店铺现有链接）+ 人工价 | 每日 | 必填（测算用） | 当前售价优先人工价，其次 LinkFox Listing 价，再产品表历史价 |

## 4. FBA 货件中心（fba）

| 需要字段 | 马帮来源页面 / API | 更新频率 | 必填 | 备注 |
|---|---|---|---|---|
| `fba_id`（`^FBA[A-Z0-9-]{3,40}$`）、`amazonReference`、仓库、来源 | 马帮 FBA 发货 / 仓储页（待截图确认字段名）；工作台人工创建货件时登记 | 每批创建时 + 每日核对 | 必填 | 现有工作台**抓不到** FBA 货件信息，只能手动登记；马帮应能补上这一块 |
| `sea_waybill` 海运单号、轨迹事件 `eventTime/eventInfo`、发货日 `shippingDate`、装箱日 `packedAt` | 物流 / 海运公司网站（`provider: nextsls / choicexp-manual / manual`，只有 nextsls 能自动查） | 每日 | 运单必填 | 物流轨迹单独抓海运公司，不走亚马逊 |
| 收货量 / 可售量、`amazonReceiptVerified, sellableVerified` | 马帮 FBA 货件页 / FBA 库存页核对 | 每日 | 必填 | 按 `fba_id` 匹配跟踪 |
| 异常：发货后 **>70 天未入库** | 由发货日 + 入库/可售状态算出 | 每日检查 | 必填（新规则） | 起算日待确认：建议按 `shippingDate`（发货日）；代码里原来没有 70 天这个数 |
| 异常：亚马逊货件**超时关闭但 0 入库/0 上架** | 亚马逊货件状态 + 入库量 | 每日检查 | 必填（新规则） | 关闭定义待确认：建议指亚马逊后台状态 Closed/已完成；不能自动移到已完成 |
| 真实箱 `physicalId, items[sku,quantity,fnsku,unitDeclaredUsd], weightKg, 长宽高` | 工作台人工登记 | 每批 | 必填 | 沙特店缺 FNSKU/申报值不能导出 |

## 5. SKU 中心 / 商品档案（sku）

| 需要字段 | 马帮来源页面 / API | 更新频率 | 必填 | 备注 |
|---|---|---|---|---|
| `localSku`（马帮SKU）、`sku`、ASIN、FNSKU、产品名、上架时间、类目、状态 | 商品管理 / 在售 Listing 页（已见截图：MSKU/FNSKU、ASIN、品名/SKU、日均销量、上架时间、库龄，529 条，有“下载”按钮） | 每日快照 | 必填 | Listing 口径，不是订单口径；日均销量、库龄 1~180/181~330/331~365/365天以上、总 rating 都在这页 |
| 包装尺寸、重量、每套数量、供应商链接 | 产品表 / 商品详情页 | 有新品/改动时 | 必填（头程/成本用） | 体积 = 长×宽×高，用于头程分摊 |

## 6. 不从马帮拿的数据（不要硬凑）

| 数据 | 正确来源 | 备注 |
|---|---|---|
| 广告花费、ACOS、广告带来的销售额 | LinkFox / 亚马逊广告后台 SP 报告 | 马帮没有广告数据 |
| SKU Economics 原表费用拆分（佣金/FBA/仓储/其他按 SKU） | Seller Central 业务报告 → SKU Economics | 马帮如无按 SKU 拆分，仍需这张原表 |
| 汇率 `cnyPerCurrency` | 人工（银行/换汇，有来源） | 无自动汇率接口 |
| 采购单价、供应商、仓库、税费口径 | 人工登记 / 采购管理页核对 | 导出马帮采购表即默认已下单 |

## 7. 同步任务一览（对应 `sync_jobs.json`）

| 任务 | 来源 | 频率 | 增量字段 | 输出表 |
|---|---|---|---|---|
| `orders_daily` | 马帮订单列表 / `order-get-order-list-new` | 每日增量 | `last_sync_time`（更新时间） | `orders`, `daily_sales` |
| `listing_daily` | 马帮在售 Listing 页 | 每日快照 | `snapshot_date`（覆盖当日） | `listings` |
| `inventory_daily` | 马帮库存 / FBA 库存页 / `stock-do-search-sku-list-new` | 每日快照 | `snapshot_date` | `inventory_snapshots` |
| `fba_shipments_daily` | 马帮 FBA 发货页 + 海运轨迹 | 每日核对 | `fba_id`（upsert）+ 状态变更 | `fba_shipments`, `lead_times` |
| `replenishment_daily`（派生，非拉取） | 由上面 4 个任务算出 | 每日 | — | `replenishment`（建议量，按单 SKU） |

> 对接口径：完成一套流程后才能对接工作台。**现在绝对不接进 `jcf-workbench` 仓库。**
> v0.2 只做单独程序，输出 `output/mabang_data.sqlite` + JSON，字段名尽量对齐工作台
> audit 里的字段名，后期对接时工作台按 `store_id + date + sku + asin` 读，不改马帮程序的表结构。
