"""SparkSession factory.

On Databricks the existing session is reused. Locally (tests, laptop runs) a small
Delta-enabled session is created so the same code paths run offline.
"""
from __future__ import annotations

import os
import sys

from pyspark.sql import SparkSession


def get_spark(app_name: str = "retail360", local: bool | None = None, warehouse_dir: str | None = None) -> SparkSession:
    """Return a SparkSession. ``local=None`` auto-detects (Databricks runtime sets DATABRICKS_RUNTIME_VERSION)."""
    if local is None:
        local = "DATABRICKS_RUNTIME_VERSION" not in os.environ
    if not local:
        return SparkSession.builder.getOrCreate()

    # Make workers use the same interpreter as the driver (important on Windows / venvs).
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

    from delta import configure_spark_with_delta_pip

    builder = (
        SparkSession.builder.appName(app_name)
        .master("local[2]")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.default.parallelism", "2")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.databricks.delta.retentionDurationCheck.enabled", "false")
    )
    if warehouse_dir:
        builder = builder.config("spark.sql.warehouse.dir", warehouse_dir)
    return configure_spark_with_delta_pip(builder).getOrCreate()
