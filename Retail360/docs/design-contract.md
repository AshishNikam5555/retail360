# Retail360 – Design Contract

Single source of truth for names, schemas and conventions. Every module, notebook,
SQL file, pipeline and doc in this repository must follow it.

> Retail360 is an entirely fictional, independent portfolio project. All data is synthetic.

## 1. Conventions

* Python package: `retail360` under `src/` (python >= 3.10, PySpark 3.5.x, delta-spark 3.2.x).
* Unity Catalog three-level names. Catalog = `retail360_<env>` (`dev`, `test`, `prod`); local tests use
  no catalog (plain schema/db names or temp views). Schemas: `bronze`, `silver`, `gold`, `ops`.
* Config is resolved by `retail360.config.Settings` (env vars `RETAIL360_ENV`, `RETAIL360_CATALOG`,
  `RETAIL360_LANDING_PATH`, `RETAIL360_CHECKPOINT_PATH`, ...), with YAML defaults in `config/`.
  **No real credentials anywhere** – only placeholders (`<your-...>`), `.env.example`, Key Vault / secret-scope references.
* Pure transformation functions: `fn(df: DataFrame, ...) -> DataFrame`. No hidden global state.
  IO (reads/writes) lives in thin wrappers so the logic is unit-testable with a local SparkSession.
* Every Bronze table carries audit columns: `_ingest_ts` (timestamp), `_source_file` (string),
  `_batch_id` (string), `_source_system` (string). Silver/Gold carry `_processed_ts`, `_batch_id`.
* Surrogate keys: `<entity>_sk` (bigint, generated via deterministic hash or monotonically assigned in dim loaders).
  Natural/business keys keep their source name (`customer_id`, `product_id`, `store_id`, ...).
* Timestamps UTC. Dates `yyyy-MM-dd`. Money `decimal(18,2)`. Currency single (`GBP`).
* Type hints and docstrings on public functions. Logging via `retail360.common.logging_utils.get_logger`.

## 2. Source datasets (landing, CSV/JSON/Parquet under `<landing>/<dataset>/...`)

| dataset | format | grain | columns |
|---|---|---|---|
| `customers` | csv | one row per customer **change event** | customer_id, first_name, last_name, email, phone, birth_date, gender, city, region, postcode, loyalty_tier (`NONE/BRONZE/SILVER/GOLD/PLATINUM`), marketing_opt_in (bool), signup_date, updated_at, op (`I/U/D`) |
| `products` | csv | one row per product **change event** | product_id, sku, product_name, brand, category, subcategory, unit_cost, list_price, is_active (bool), updated_at, op |
| `stores` | csv | one row per store | store_id, store_name, store_type (`HIGH_STREET/MALL/OUTLET/FLAGSHIP`), city, region, postcode, open_date, close_date (nullable), floor_area_sqm, manager_name, updated_at |
| `promotions` | csv | one row per promo | promo_id, promo_name, promo_type (`PERCENT_OFF/BOGO/BUNDLE/LOYALTY_BONUS`), discount_pct, start_date, end_date, channel (`STORE/ONLINE/BOTH`), category_scope (nullable) |
| `pos_transactions` | json (JSON lines; also streamed) | one row per **POS line** | txn_id, line_no, store_id, register_id, customer_id (nullable), loyalty_id (nullable), product_id, quantity (int, may be negative for returns), unit_price, discount_amount, promo_id (nullable), payment_method (`CARD/CASH/MOBILE/GIFT_CARD`), txn_ts, event_ts, ingest_ts (nullable) |
| `ecommerce_orders` | json | one row per **order line** | order_id, line_no, customer_id, product_id, quantity, unit_price, discount_amount, promo_id (nullable), order_status (`PLACED/SHIPPED/DELIVERED/CANCELLED/RETURNED`), channel_device (`WEB/IOS/ANDROID`), shipping_city, shipping_region, order_ts, updated_at |
| `inventory_snapshots` | parquet | store x product x day | snapshot_date, store_id, product_id, on_hand_qty, on_order_qty, reorder_point, last_received_date (nullable) |
| `loyalty_accounts` | csv | one row per account | loyalty_id, customer_id, tier, points_balance, enrolled_date, status (`ACTIVE/SUSPENDED/CLOSED`), updated_at |
| `loyalty_transactions` | json | one row per points event | loyalty_txn_id, loyalty_id, event_type (`EARN/REDEEM/EXPIRE/ADJUST`), points (int, negative for redeem/expire), related_txn_id (nullable), event_ts |

Deliberate data-quality problems injected by the generator (so DQ/cleansing code has real work to do):
duplicate rows, null keys, malformed emails, negative prices, future timestamps, orphan FKs,
late-arriving events (event_ts days older than arrival), out-of-order CDC updates, trailing whitespace / mixed case.

## 3. Tables

Bronze (`bronze.*`, append-only, raw typed-as-read + audit columns): `customers_raw`, `products_raw`, `stores_raw`,
`promotions_raw`, `pos_transactions_raw`, `ecommerce_orders_raw`, `inventory_snapshots_raw`, `loyalty_accounts_raw`,
`loyalty_transactions_raw`.

Silver (`silver.*`, cleansed, deduplicated, conformed, quarantine for rejects):
`customers` (current state, SCD1), `products` (current), `stores`, `promotions`, `pos_sales_lines`, `ecommerce_order_lines`,
`inventory_daily`, `loyalty_accounts`, `loyalty_events`, plus `ops.dq_quarantine` and `ops.dq_results`.

Gold (`gold.*`, star schema + marts):
* Dimensions: `dim_date` (generated), `dim_customer` (**SCD2**: customer_sk, customer_id, attributes, valid_from, valid_to, is_current),
  `dim_product` (**SCD2**), `dim_store` (SCD1), `dim_promotion` (SCD1), `dim_unknown` rows (sk = -1) for orphans.
* Facts: `fact_sales` (unified POS + e-commerce lines; channel `STORE/ONLINE`; measures quantity, gross_amount,
  discount_amount, net_amount, cost_amount, margin_amount; keys date_key(int yyyyMMdd), customer_sk, product_sk, store_sk (nullable for online -> -1), promo_key),
  `fact_inventory_snapshot`, `fact_loyalty_events`.
* Marts (all `gold.`): `daily_sales_performance`, `store_performance`, `product_performance`, `customer_360`,
  `customer_lifetime_value`, `inventory_health`, `loyalty_program_analytics`.

Ops (`ops.*`): `audit_log` (run_id, pipeline, stage, table_name, status, rows_in, rows_out, rows_rejected, started_at, ended_at, error_message),
`dq_results` (run_id, table_name, rule_name, severity, passed_count, failed_count, checked_at), `dq_quarantine` (table_name, record_json, failed_rules, quarantined_at, run_id), `watermarks` (table_name, watermark_ts, updated_at).

## 4. Module map (what lives where)

```
src/retail360/
  config.py                       Settings, table-name helpers (fq_name(schema, table))
  common/spark.py                 get_spark(local=True) with Delta enabled for tests
  common/logging_utils.py         get_logger
  common/audit.py                 AuditLogger: start/finish/fail -> ops.audit_log (works on delta path or table)
  dq/rules.py                     Rule dataclasses: NotNull, Unique, Range, Regex, AllowedValues, ReferentialIntegrity, Custom(sql)
  dq/runner.py                    run_rules(df, rules) -> (valid_df, quarantine_df, results_df); severity ERROR quarantines, WARN logs
  transforms/cleansing.py         trim_strings, normalize_email, standardize_case, parse_timestamps, ...
  transforms/dedup.py             dedupe_latest(df, keys, order_col)
  transforms/cdc.py               apply_cdc_scd1(target, changes, key, op_col, order_col)  (Delta MERGE, handles I/U/D + out-of-order)
  transforms/scd2.py              scd2_merge(spark, target_path_or_table, source_df, key, tracked_cols, ts_col)
  transforms/late_arriving.py     split_late_events(df, event_col, watermark_days), reprocess window helpers, late dimension handling
  ingestion/batch.py              Auto Loader (cloudFiles) reader/writer builders + local fallback (spark.read) for tests
  ingestion/streaming.py          Event Hubs (Kafka-compatible endpoint) stream reader + foreachBatch idempotent Delta writer
  silver/*.py                     one module per entity: build_<entity>(bronze_df) -> DataFrame (pure)
  gold/*.py                       build_fact_sales, build_dim_*, build_marts
  generators/generate_data.py     CLI: python -m retail360.generators.generate_data --out data/raw --seed 42 --scale small
```

## 5. Orchestration (Lakeflow)

* Lakeflow Spark Declarative Pipeline `retail360_medallion` (files in `pipelines/`), continuous-optional, expectations for DQ.
* Lakeflow Job `retail360_daily` (tasks): ingest_batch -> dlt_pipeline -> scd2_dimensions -> gold_marts -> dq_report -> optimize_maintenance; plus
  `retail360_streaming_pos` job (always-on) and `retail360_backfill` (parameterised date range).
* Declarative Automation Bundles root `databricks.yml` with targets `dev`, `test`, `prod`; resources in `resources/*.yml`.
* Ingestion is Databricks-native: source extracts land in an ADLS/Unity Catalog landing volume and Auto Loader loads them; POS events stream via Event Hubs. No Azure Data Factory.
* Azure DevOps: `azure-pipelines/ci.yml` (lint, unit tests, bundle validate, terraform fmt/validate) and `cd.yml` (dev -> test -> prod with approvals).
* Terraform (infra/terraform): resource group, ADLS Gen2 (+containers landing/bronze/silver/gold/checkpoints), Databricks workspace,
  Event Hubs namespace + hub, Key Vault, Unity Catalog metastore assignment, catalogs/schemas/external locations/grants, access connector.

## 6. Testing

The project must stay **portable**: no custom Windows compatibility binaries (no winutils stand-ins, no HADOOP_HOME hacks).
Local Windows development cannot start a JVM Spark session reliably, so testing is tiered:

1. **Default tier (runs everywhere, offline, no JVM):** `.venv\Scripts\python -m pytest -q`
   * Pure-Python logic: config, rule definitions -> SQL expression strings, SCD2/CDC/MERGE SQL builders, late-data window maths,
     audit record builders, data generator (pandas/numpy/Faker), YAML/JSON/Terraform/SQL static validation.
   * **Design rule: "SQL-expression-first".** Business logic that decides *what* to compute is expressed as SQL strings / dataclasses
     (testable without Spark) and executed by thin wrappers via `F.expr`, `selectExpr`, `spark.sql`, or Delta `merge(...)`.
     Do NOT build `pyspark.sql.Column` objects at import time or in code paths the default tier exercises (they need a live JVM).
   * Orchestration code (audit logger, runner, merge helpers) is tested with `unittest.mock` fakes of `SparkSession`/`DataFrame`/`DeltaTable`
     (assert the right SQL / merge condition / write mode is requested).
2. **Spark/Delta integration tier:** tests decorated `@pytest.mark.spark_integration` (+ `chispa` assertions) that use the `spark` fixture.
   They are skipped by default and run with `RETAIL360_RUN_SPARK_TESTS=1` on Linux/macOS/WSL/container (or Windows with a proper Hadoop).
   Keep them in `tests/spark_integration/`. Document them in `docs/testing.md`.
3. Importing `pyspark`/`delta` modules at top level is fine (imports work without a JVM); *calling* Spark APIs is what needs the JVM.
   Import `delta.tables.DeltaTable` lazily inside functions that use it if the default tier imports that module.
* One test module per module under test; the generator has a determinism test (same seed -> same output).

## 7. Hard restrictions (applies to every contributor)

* Work only inside this `Retail360` folder. Do not read, copy or reference any other local project or employer code/data.
* No Azure CLI, no real subscriptions/workspaces/credentials, no `terraform apply`, no `databricks bundle deploy`, no git push.
* Placeholders only. No affiliation claims with any real company.
