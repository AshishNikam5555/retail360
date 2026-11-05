"""Shared pytest fixtures.

Test tiers
----------
* default (``pytest``)            - pure-Python and mock-based unit tests. Run anywhere, no JVM/Hadoop needed.
* ``-m spark_integration``        - real local Spark + Delta tests. They need a Linux/macOS machine, WSL, a container
                                    or a Windows box with a proper Hadoop/winutils setup. Opt in with
                                    ``RETAIL360_RUN_SPARK_TESTS=1``; otherwise they are skipped with a clear reason.
See docs/testing.md.
"""
from __future__ import annotations

import os

import pytest

from retail360.common.spark import get_spark

SPARK_OPT_IN = os.getenv("RETAIL360_RUN_SPARK_TESTS") == "1"


def pytest_collection_modifyitems(config, items):
    if SPARK_OPT_IN:
        return
    skip = pytest.mark.skip(
        reason="Spark/Delta integration test: set RETAIL360_RUN_SPARK_TESTS=1 on Linux/macOS/WSL/container "
        "(or Windows with a proper Hadoop setup). See docs/testing.md"
    )
    for item in items:
        if "spark_integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    """Local Delta-enabled SparkSession. Only used by ``spark_integration`` tests."""
    session = get_spark("retail360-tests", local=True, warehouse_dir=str(tmp_path_factory.mktemp("warehouse")))
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
