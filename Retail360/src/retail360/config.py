"""Central configuration for Retail360.

Values come from environment variables with safe local defaults. Nothing in here is a real
credential: secrets are always referenced (Key Vault / Databricks secret scope), never stored.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

SCHEMAS = ("bronze", "silver", "gold", "ops")

BRONZE_TABLES = (
    "customers_raw", "products_raw", "stores_raw", "promotions_raw", "pos_transactions_raw",
    "ecommerce_orders_raw", "inventory_snapshots_raw", "loyalty_accounts_raw", "loyalty_transactions_raw",
)


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Use ``Settings.from_env()``; tests construct it directly."""

    env: str = "dev"
    catalog: str | None = None  # None -> plain schema.table names (local/test mode)
    landing_path: str = "data/raw"
    checkpoint_path: str = "data/_checkpoints"
    warehouse_path: str = "data/_warehouse"
    late_data_days: int = 3
    eventhub_namespace: str = "<your-eventhubs-namespace>"
    eventhub_name: str = "pos-transactions"
    eventhub_secret_scope: str = "retail360"  # Databricks secret scope holding the connection string
    eventhub_secret_key: str = "eventhub-connection-string"
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.getenv("RETAIL360_ENV", "dev")
        return cls(
            env=env,
            catalog=os.getenv("RETAIL360_CATALOG") or None,
            landing_path=os.getenv("RETAIL360_LANDING_PATH", "data/raw"),
            checkpoint_path=os.getenv("RETAIL360_CHECKPOINT_PATH", "data/_checkpoints"),
            warehouse_path=os.getenv("RETAIL360_WAREHOUSE_PATH", "data/_warehouse"),
            late_data_days=int(os.getenv("RETAIL360_LATE_DATA_DAYS", "3")),
            eventhub_namespace=os.getenv("RETAIL360_EH_NAMESPACE", "<your-eventhubs-namespace>"),
            eventhub_name=os.getenv("RETAIL360_EH_NAME", "pos-transactions"),
            eventhub_secret_scope=os.getenv("RETAIL360_EH_SECRET_SCOPE", "retail360"),
            eventhub_secret_key=os.getenv("RETAIL360_EH_SECRET_KEY", "eventhub-connection-string"),
        )

    def fq_name(self, schema: str, table: str) -> str:
        """Fully-qualified table name: ``catalog.schema.table`` (or ``schema.table`` when no catalog)."""
        if schema not in SCHEMAS:
            raise ValueError(f"Unknown schema '{schema}', expected one of {SCHEMAS}")
        return f"{self.catalog}.{schema}.{table}" if self.catalog else f"{schema}.{table}"

    def landing(self, dataset: str) -> str:
        return f"{self.landing_path.rstrip('/')}/{dataset}"

    def checkpoint(self, name: str) -> str:
        return f"{self.checkpoint_path.rstrip('/')}/{name}"


def fq_name(schema: str, table: str, catalog: str | None = None) -> str:
    """Module-level helper mirroring :meth:`Settings.fq_name`."""
    return Settings(catalog=catalog).fq_name(schema, table)
