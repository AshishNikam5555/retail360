# Retail360 – Enterprise Retail Data Intelligence Platform

![Azure](https://img.shields.io/badge/Azure-Databricks-0078D4) ![Delta Lake](https://img.shields.io/badge/Delta-Lake-00ADD8) ![PySpark](https://img.shields.io/badge/PySpark-3.5-E25A1C) ![Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC) ![Status](https://img.shields.io/badge/status-architecture%20showcase-orange)

> A **fictional, independent portfolio project** with 100% synthetic data. It is not affiliated with any company.
> This repository is an **architecture showcase**: the design is complete, the implementation is partial (see [Status](#status)).

## 1. Business problem
A fictional retailer runs stores (POS), a web/app shop, a loyalty scheme and promotions, each with its own data. Teams cannot answer basic questions consistently: *What sold where? Who are our best customers? Which stock is at risk? Do promotions pay back?*

**Objective:** unify the data into one governed lakehouse and publish trusted, analytics-ready datasets.

## 2. Solution overview

```mermaid
flowchart LR
  subgraph Sources
    POS[POS events]:::src
    ECOM[E-commerce orders]:::src
    CRM[Customers / Loyalty]:::src
    MDM[Products / Stores / Promotions]:::src
    INV[Inventory snapshots]:::src
  end
  POS -->|stream| EH[Azure Event Hubs]
  ECOM & CRM & MDM & INV -->|files / exports| LAND[(ADLS Gen2 landing volume)]
  EH --> BRZ
  LAND -->|Auto Loader| BRZ[(Bronze: raw + audit cols)]
  BRZ -->|clean, dedupe, DQ| SLV[(Silver: conformed)]
  SLV -->|model, SCD2, aggregate| GLD[(Gold: star schema + marts)]
  GLD --> SQL[Databricks SQL dashboards]
  GLD --> ML[Data science / BI]
  UC{{Unity Catalog governance}} -.-> BRZ & SLV & GLD
  classDef src fill:#eef,stroke:#88a
```

## 3. Medallion architecture

```mermaid
flowchart TB
  B["BRONZE – append-only, raw as received<br/>_ingest_ts, _source_file, _batch_id"] --> S
  S["SILVER – typed, cleansed, deduplicated<br/>DQ rules, quarantine of bad rows, CDC applied (SCD1)"] --> G
  G["GOLD – dim_customer (SCD2), dim_product (SCD2), dim_store, dim_date<br/>fact_sales, fact_inventory, fact_loyalty + business marts"]
```

| Layer | Purpose | Key techniques |
|---|---|---|
| Bronze | Land data unchanged | Auto Loader, schema evolution, rescued data column, Event Hubs (Kafka endpoint) |
| Silver | Trusted entities | Dedup by latest, `MERGE` for CDC (I/U/D, out-of-order safe), DQ expectations + quarantine, late-arriving handling |
| Gold | Business-ready | Star schema, SCD Type 2 dimensions, surrogate keys, aggregates |

## 4. Orchestration (Lakeflow)

```mermaid
flowchart LR
  A[Auto Loader: landing → bronze] --> B[ingest_batch]
  B --> C[Lakeflow pipeline<br/>bronze→silver]
  C --> D[scd2_dimensions]
  D --> E[gold_marts]
  E --> F[dq_report]
  F --> G[optimize / vacuum]
  S[Streaming job: POS events] -.-> C
```

* **Lakeflow Spark Declarative Pipeline** for bronze→silver with expectations.
* **Lakeflow Jobs:** `retail360_daily`, `retail360_streaming_pos` (continuous), `retail360_backfill` (date range).
* Retries, timeouts and alerts on every task; failed rows go to `ops.dq_quarantine`, runs to `ops.audit_log`.

## 5. Data model (Gold)

```mermaid
erDiagram
  FACT_SALES }o--|| DIM_DATE : date_key
  FACT_SALES }o--|| DIM_CUSTOMER : customer_sk
  FACT_SALES }o--|| DIM_PRODUCT : product_sk
  FACT_SALES }o--|| DIM_STORE : store_sk
  FACT_SALES }o--o| DIM_PROMOTION : promo_key
  FACT_INVENTORY_SNAPSHOT }o--|| DIM_STORE : store_sk
  FACT_INVENTORY_SNAPSHOT }o--|| DIM_PRODUCT : product_sk
  FACT_LOYALTY_EVENTS }o--|| DIM_CUSTOMER : customer_sk
  DIM_CUSTOMER { bigint customer_sk string customer_id date valid_from date valid_to bool is_current }
  DIM_PRODUCT  { bigint product_sk string product_id decimal list_price bool is_current }
  FACT_SALES   { int date_key decimal net_amount decimal margin_amount string channel }
```

**Gold marts:** daily sales performance · store performance · product performance · customer 360 · customer lifetime value · inventory health · loyalty analytics.

## 6. CI/CD and infrastructure

```mermaid
flowchart LR
  PR[Pull request] --> CI[CI: ruff, pytest, terraform validate, bundle validate]
  CI --> M[Merge to main] --> DEV[Deploy dev] --> TST[Deploy test<br/>smoke run] --> APR{{Approval}} --> PRD[Deploy prod]
  TF[Terraform: RG, ADLS, Databricks, Event Hubs, Key Vault, Unity Catalog] -.-> DEV & TST & PRD
```

Environments `dev` / `test` / `prod` use separate catalogs (`retail360_<env>`) and are deployed with **Declarative Automation Bundles**; infrastructure is **Terraform**; pipelines run in **Azure DevOps**.

## 7. Technology stack
Azure Databricks · PySpark · Delta Lake · Auto Loader · Structured Streaming + Event Hubs · Unity Catalog · Lakeflow Pipelines & Jobs · Declarative Automation Bundles · ADLS Gen2 · Azure DevOps (CI/CD) · Terraform · Pytest + Chispa · Databricks SQL.

## 8. Repository structure
```
Retail360/
├── src/retail360/        # config, common utils, data generator (core library planned: dq, transforms, ingestion)
├── infra/terraform/      # Azure + Databricks infrastructure (draft)
├── tests/                # unit tests; Spark tests marked spark_integration
├── docs/design-contract.md   # table names, columns, conventions
├── pyproject.toml
└── (planned) pipelines/ resources/ sql/ azure-pipelines/ databricks.yml
```

## 9. Status
| Area | State |
|---|---|
| Architecture and design contract | Done (this README, `docs/design-contract.md`) |
| Config, Spark helper, test fixtures | Done |
| Synthetic data generator, Terraform draft | Started, not verified |
| Silver/Gold code, Lakeflow files, bundle, CI/CD | Planned |

**Testing note:** unit tests are pure-Python/mock-based. Real Spark/Delta tests (`@pytest.mark.spark_integration`) need Linux, macOS, WSL or a container; run with `RETAIL360_RUN_SPARK_TESTS=1`.

## 10. Why this design
* **Medallion** separates raw, trusted and business layers, so reprocessing is cheap and lineage is clear.
* **Delta MERGE + SCD2** gives idempotent loads and full history.
* **Unity Catalog** centralises governance across environments.
* **Bundles + Terraform** make environments reproducible and reviewable.
