import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("pyarrow")
from retail360.generators.generate_data import generate, main  # noqa: E402

COLS = {
    "customers": "customer_id first_name last_name email phone birth_date gender city region postcode loyalty_tier marketing_opt_in signup_date updated_at op",
    "products": "product_id sku product_name brand category subcategory unit_cost list_price is_active updated_at op",
    "stores": "store_id store_name store_type city region postcode open_date close_date floor_area_sqm manager_name updated_at",
    "promotions": "promo_id promo_name promo_type discount_pct start_date end_date channel category_scope",
    "pos_transactions": "txn_id line_no store_id register_id customer_id loyalty_id product_id quantity unit_price discount_amount promo_id payment_method txn_ts event_ts ingest_ts",
    "ecommerce_orders": "order_id line_no customer_id product_id quantity unit_price discount_amount promo_id order_status channel_device shipping_city shipping_region order_ts updated_at",
    "inventory_snapshots": "snapshot_date store_id product_id on_hand_qty on_order_qty reorder_point last_received_date",
    "loyalty_accounts": "loyalty_id customer_id tier points_balance enrolled_date status updated_at",
    "loyalty_transactions": "loyalty_txn_id loyalty_id event_type points related_txn_id event_ts",
}


def _hash(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _read(root: Path, ds: str) -> pd.DataFrame:
    files = sorted((root / ds).rglob("*.*"))
    if ds == "inventory_snapshots":
        return pd.concat([pd.read_parquet(f) for f in files])
    if files[0].suffix == ".json":
        return pd.concat([pd.read_json(f, lines=True, dtype=False) for f in files])
    return pd.concat([pd.read_csv(f, dtype=str) for f in files])


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    a, b = tmp_path_factory.mktemp("a"), tmp_path_factory.mktemp("b")
    ma = generate(a, seed=7, days=5)
    generate(b, seed=7, days=5)
    return a, b, ma


def test_deterministic(run):
    a, b, _ = run
    ha, hb = _hash(a), _hash(b)
    assert ha == hb and len(ha) > 20


def test_columns_and_manifest(run):
    a, _, m = run
    for ds, cols in COLS.items():
        df = _read(a, ds)
        assert list(df.columns) == cols.split(), ds
        assert len(df) == m["row_counts"][ds], ds
    assert json.loads((a / "_manifest.json").read_text())["row_counts"] == m["row_counts"]


def test_referential_integrity_and_returns(run):
    a, _, _ = run
    pos = _read(a, "pos_transactions")
    prods = set(_read(a, "products").product_id.dropna())
    ok = pos[pos.product_id != "P99999"]
    assert ok.product_id.isin(prods).all()
    assert (pos.quantity < 0).any()


def test_cli_main(tmp_path):
    assert main(["--out", str(tmp_path), "--seed", "1", "--days", "2"]) == 0
    assert (tmp_path / "_manifest.json").exists()
