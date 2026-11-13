# output/ 说明（马帮拉数 v0.2）

这是单独拉数程序的输出目录，不是工作台仓库。

- `mabang_data.sqlite`：规范库，表结构见 `schema.sql`。后期对接时工作台只读这个库，
  关联钥匙 `store_id + date + sku + asin`。
- `schema.sql`：建表语句，与程序里 `SCHEMA_SQL` 同一份。
- `json/<date>/*.json`：每日原始 + 汇总 JSON（orders / daily_sales / listings /
  inventory / fba_shipments / replenishment）。
- `last_sync.json`：每个任务的上次同步时间，增量同步的依据。删了它下次会从头拉，
  订单仍按 `platformOrderId` 去重，不会重复计销量。
- `daily_report_YYYY-MM-DD.md`：每日汇总报告。
- `orders_raw_*.csv` / `sales_by_day_*.csv` 等：v0.1 的旧输出，v0.2 不再依赖，
  留着备查。
- `downloads/`：浏览器模式下载的原始导出表。

mock 数据：`--mock` 跑出来的数字是编来跑通流程的，不是真实经营数据，
不要当经营数据用。
