"""Deterministic synthetic data generator for Retail360 (all data fictional).

Usage: python -m retail360.generators.generate_data --out data/raw --seed 42 --scale small --days 30
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SCALES = {"small": dict(customers=400, products=300, txns_per_day=60, orders_per_day=15, inv_pairs=60),
          "medium": dict(customers=2000, products=300, txns_per_day=300, orders_per_day=80, inv_pairs=300)}
DEFECT_RATE = 0.01

CITIES = [("Northbridge", "North East"), ("Eastvale", "East"), ("Westmoor", "West Midlands"),
          ("Southhaven", "South East"), ("Ashford Green", "South East"), ("Kingsmere", "London"),
          ("Redcliffe", "South West"), ("Ironton", "Yorkshire"), ("Lakeside", "North West"),
          ("Hartley", "Scotland"), ("Brookfield", "Wales"), ("Stonebridge", "East Midlands")]
FIRST = ["Alex", "Sam", "Jordan", "Priya", "Liam", "Olivia", "Noah", "Amelia", "Arjun", "Chloe", "Mohammed",
         "Grace", "Ethan", "Isla", "Lucas", "Sophie", "Ravi", "Emma", "Daniel", "Hannah"]
LAST = ["Smith", "Jones", "Patel", "Taylor", "Brown", "Khan", "Wilson", "Evans", "Thomas", "Roberts", "Walker",
        "Wright", "Green", "Hall", "Clarke", "Baker", "Turner", "Hughes", "Moore", "Ward"]
CATS = {"Grocery": ["Snacks", "Beverages", "Bakery"], "Electronics": ["Audio", "Accessories", "Wearables"],
        "Home": ["Kitchen", "Decor", "Storage"], "Apparel": ["Tops", "Outerwear", "Footwear"],
        "Beauty": ["Skincare", "Haircare", "Fragrance"], "Toys": ["Puzzles", "Outdoor", "Games"]}
BRANDS = ["Acmeo", "Brightly", "Crestline", "Dovetail", "Everly", "Fernhill", "Goldleaf", "Harbor&Co"]
TIERS = ["NONE", "BRONZE", "SILVER", "GOLD", "PLATINUM"]
TIER_MIN = [0, 1, 300, 800, 2000]  # cumulative spend (GBP) thresholds


def _tier_for(spend: float) -> str:
    t = 0
    for i, m in enumerate(TIER_MIN):
        if spend >= m:
            t = i
    return TIERS[t]


def _ts(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n")


def _write_jsonl(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df.astype(object).where(df.notna(), None)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for rec in df.to_dict("records"):
            rec = {k: (v.item() if hasattr(v, "item") else v) for k, v in rec.items()}
            fh.write(json.dumps(rec) + "\n")


def _write_partitioned_jsonl(df: pd.DataFrame, root: Path, col: str) -> None:
    day = df[col].astype(str).str[:10]
    for d, g in df.groupby(day, sort=True):
        _write_jsonl(g, root / f"dt={d}" / "part-0000.json")


def generate(out: str | Path, seed: int = 42, scale: str = "small", start_date: str = "2025-01-01",
             days: int = 30) -> dict:
    """Generate all datasets under ``out`` and return the manifest dict."""
    cfg = SCALES[scale]
    out = Path(out)
    rnd = random.Random(seed)
    rng = np.random.default_rng(seed)
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = start + timedelta(days=days)
    defects: dict[str, int] = {}

    def bump(k: str, n: int = 1) -> None:
        defects[k] = defects.get(k, 0) + n

    def hit() -> bool:
        return rnd.random() < DEFECT_RATE

    # ---- stores
    stores = []
    for i in range(25):
        city, region = CITIES[i % len(CITIES)]
        stores.append(dict(
            store_id=f"S{i + 1:03d}", store_name=f"{city} {rnd.choice(['Central', 'Retail Park', 'Square'])}",
            store_type=rnd.choice(["HIGH_STREET", "MALL", "OUTLET", "FLAGSHIP"]), city=city, region=region,
            postcode=f"{city[:2].upper()}{rnd.randint(1, 20)} {rnd.randint(1, 9)}AA",
            open_date=(date(2015, 1, 1) + timedelta(days=rnd.randint(0, 3000))).isoformat(),
            close_date=None, floor_area_sqm=rnd.randint(200, 5000),
            manager_name=f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", updated_at=_ts(start)))
    stores_df = pd.DataFrame(stores)
    stores_df.loc[stores_df.index[-1], "close_date"] = (start.date() + timedelta(days=days + 200)).isoformat()
    store_ids = stores_df.store_id.tolist()

    # ---- products (CDC)
    prods = []
    for i in range(cfg["products"]):
        cat = rnd.choice(list(CATS))
        cost = round(rnd.uniform(0.5, 80), 2)
        prods.append(dict(
            product_id=f"P{i + 1:05d}", sku=f"SKU-{rnd.randint(100000, 999999)}",
            product_name=f"{rnd.choice(BRANDS)} {rnd.choice(CATS[cat])} {i + 1}", brand=rnd.choice(BRANDS),
            category=cat, subcategory=rnd.choice(CATS[cat]), unit_cost=cost,
            list_price=round(cost * rnd.uniform(1.3, 2.2), 2), is_active=True,
            updated_at=_ts(start - timedelta(days=30)), op="I"))
    prod_cur = {p["product_id"]: dict(p) for p in prods}
    pchanges = [list(prods), [], []]
    for pid in rnd.sample(list(prod_cur), k=cfg["products"] // 5):
        r = dict(prod_cur[pid])
        r["list_price"] = round(r["list_price"] * rnd.uniform(0.85, 1.2), 2)
        r["updated_at"] = _ts(start + timedelta(days=rnd.randint(1, max(1, days - 1))))
        r["op"] = "U"
        pchanges[1].append(r)
    for r in pchanges[1][: max(1, len(pchanges[1]) // 4)]:  # stale (out-of-order) duplicate update in later batch
        s = dict(r)
        s["list_price"] = round(s["list_price"] * 1.5, 2)
        s["updated_at"] = _ts(start - timedelta(days=5))
        pchanges[2].append(s)
        bump("out_of_order_cdc_products")
    for pid in rnd.sample(list(prod_cur), k=3):
        r = dict(prod_cur[pid])
        r["is_active"] = False
        r["updated_at"] = _ts(end)
        r["op"] = "D"
        pchanges[2].append(r)
    for i, rows in enumerate(pchanges, 1):
        df = pd.DataFrame(rows, columns=list(prods[0]))
        for j in df.index:
            if hit():
                df.loc[j, "product_name"] = " " + str(df.loc[j, "product_name"]).upper() + "  "
                bump("whitespace_case_noise_products")
        _write_csv(df, out / "products" / f"products_batch_{i:04d}.csv")
    price = {p["product_id"]: p["list_price"] for p in prods}
    cost_of = {p["product_id"]: p["unit_cost"] for p in prods}
    pids = list(price)

    # ---- promotions
    promos = []
    for i in range(12):
        s = start + timedelta(days=rnd.randint(0, max(1, days - 5)))
        ptype = rnd.choice(["PERCENT_OFF", "BOGO", "BUNDLE", "LOYALTY_BONUS"])
        promos.append(dict(promo_id=f"PR{i + 1:03d}", promo_name=f"{ptype.title().replace('_', ' ')} {i + 1}",
                           promo_type=ptype, discount_pct=rnd.choice([5, 10, 15, 20, 25]),
                           start_date=s.date().isoformat(),
                           end_date=(s + timedelta(days=rnd.randint(3, 14))).date().isoformat(),
                           channel=rnd.choice(["STORE", "ONLINE", "BOTH"]),
                           category_scope=rnd.choice([None] + list(CATS))))
    promos_df = pd.DataFrame(promos)
    promo_ids = promos_df.promo_id.tolist()

    # ---- customers (CDC)
    ncust = cfg["customers"]
    cust = []
    for i in range(ncust):
        fn, ln = rnd.choice(FIRST), rnd.choice(LAST)
        city, region = rnd.choice(CITIES)
        cust.append(dict(
            customer_id=f"C{i + 1:06d}", first_name=fn, last_name=ln,
            email=f"{fn}.{ln}{i + 1}@example.com".lower(), phone=f"07{rnd.randint(100000000, 999999999)}",
            birth_date=(date(1950, 1, 1) + timedelta(days=rnd.randint(0, 18000))).isoformat(),
            gender=rnd.choice(["F", "M", "X"]), city=city, region=region,
            postcode=f"{city[:2].upper()}{rnd.randint(1, 20)} {rnd.randint(1, 9)}ZZ", loyalty_tier="NONE",
            marketing_opt_in=rnd.random() < 0.6,
            signup_date=(start - timedelta(days=rnd.randint(30, 700))).date().isoformat(),
            updated_at=_ts(start - timedelta(days=rnd.randint(1, 30))), op="I"))
    cust_ids = [c["customer_id"] for c in cust]
    loyal = {c["customer_id"]: f"L{i + 1:06d}" for i, c in enumerate(cust) if rnd.random() < 0.7}

    # ---- sales
    cal_start = start
    pos_rows, ord_rows = [], []
    spend: dict[str, float] = {}
    holidays = {(12, 24), (12, 26), (11, 29), (1, 1)}
    txn_n = ord_n = 0
    for d in range(days):
        day = cal_start + timedelta(days=d)
        f = (1.4 if day.weekday() >= 5 else 1.0) * (1.5 if day.month in (11, 12) else 1.0)
        f *= 1.3 if (day.month, day.day) in holidays else 1.0
        for _ in range(int(rng.poisson(cfg["txns_per_day"] * f))):
            txn_n += 1
            is_return = rnd.random() < 0.03
            store = rnd.choice(store_ids)
            cid = rnd.choice(cust_ids) if rnd.random() < 0.6 else None
            lid = loyal.get(cid) if cid else None
            ts = day + timedelta(seconds=rnd.randint(8 * 3600, 21 * 3600))
            pay = rnd.choice(["CARD", "CARD", "CASH", "MOBILE", "GIFT_CARD"])
            promo = rnd.choice(promo_ids) if rnd.random() < 0.2 else None
            net_total = 0.0
            lines = []
            for ln in range(1, rnd.randint(1, 8) + 1):
                pid = rnd.choice(pids)
                q = rnd.randint(1, 4) * (-1 if is_return else 1)
                disc = round(price[pid] * abs(q) * 0.1, 2) * (-1 if q < 0 else 1) if promo else 0.0
                net_total += price[pid] * q - disc
                lines.append(dict(
                    txn_id=f"T{txn_n:08d}", line_no=ln, store_id=store, register_id=f"R{rnd.randint(1, 6)}",
                    customer_id=cid, loyalty_id=lid, product_id=pid, quantity=q, unit_price=price[pid],
                    discount_amount=disc, promo_id=promo, payment_method=pay, txn_ts=_ts(ts),
                    event_ts=_ts(ts), ingest_ts=_ts(ts + timedelta(seconds=rnd.randint(1, 120)))))
            if cid:
                spend[cid] = spend.get(cid, 0.0) + net_total
            pos_rows.extend(lines)
        for _ in range(int(rng.poisson(cfg["orders_per_day"] * f))):
            ord_n += 1
            cid = rnd.choice(cust_ids)
            ts = day + timedelta(seconds=rnd.randint(0, 86399))
            promo = rnd.choice(promo_ids) if rnd.random() < 0.2 else None
            c, r = rnd.choice(CITIES)
            device = rnd.choice(["WEB", "IOS", "ANDROID"])
            # status lifecycle: one row per line, final status as of updated_at
            life = rnd.choices([["PLACED"], ["PLACED", "SHIPPED"], ["PLACED", "SHIPPED", "DELIVERED"],
                                ["PLACED", "CANCELLED"], ["PLACED", "SHIPPED", "DELIVERED", "RETURNED"]],
                               [1, 2, 6, 1, 1])[0]
            for ln in range(1, rnd.randint(1, 5) + 1):
                pid = rnd.choice(pids)
                q = rnd.randint(1, 3)
                ord_rows.append(dict(
                    order_id=f"O{ord_n:08d}", line_no=ln, customer_id=cid, product_id=pid, quantity=q,
                    unit_price=price[pid], discount_amount=round(price[pid] * q * 0.1, 2) if promo else 0.0,
                    promo_id=promo, order_status=life[-1], channel_device=device, shipping_city=c,
                    shipping_region=r, order_ts=_ts(ts),
                    updated_at=_ts(ts + timedelta(days=len(life) - 1, hours=2))))
            if life[-1] in ("PLACED", "SHIPPED", "DELIVERED"):
                spend[cid] = spend.get(cid, 0.0) + sum(
                    x["unit_price"] * x["quantity"] - x["discount_amount"] for x in ord_rows if x["order_id"] == f"O{ord_n:08d}")

    # customers: tier changes + city moves (updates), deletes, out-of-order
    cchanges = [cust, [], []]
    for c in cust:
        cid = c["customer_id"]
        new_tier = _tier_for(spend.get(cid, 0.0))
        moved = rnd.random() < 0.08
        if new_tier != "NONE" and cid in loyal or moved:
            r = dict(c)
            r["loyalty_tier"] = new_tier if cid in loyal else "NONE"
            if moved:
                r["city"], r["region"] = rnd.choice(CITIES)
            r["updated_at"] = _ts(start + timedelta(days=rnd.randint(1, max(1, days - 1)), hours=3))
            r["op"] = "U"
            cchanges[1].append(r)
    for r in cchanges[1][:: max(1, len(cchanges[1]) // 10)]:
        s = dict(r)
        s["city"] = "Staleton"
        s["updated_at"] = _ts(start - timedelta(days=10))
        cchanges[2].append(s)
        bump("out_of_order_cdc_customers")
    for cid in rnd.sample(cust_ids, k=3):
        r = dict(next(c for c in cust if c["customer_id"] == cid))
        r["updated_at"] = _ts(end)
        r["op"] = "D"
        cchanges[2].append(r)
    cols = list(cust[0])
    for i, rows in enumerate(cchanges, 1):
        df = pd.DataFrame(rows, columns=cols)
        for j in df.index:
            if hit():
                df.loc[j, "email"] = str(df.loc[j, "email"]).replace("@", "")
                bump("malformed_email")
            if hit():
                df.loc[j, "city"] = " " + str(df.loc[j, "city"]).upper() + " "
                bump("whitespace_case_noise_customers")
            if hit():
                df.loc[j, "customer_id"] = None
                bump("null_key_customers")
        _write_csv(df, out / "customers" / f"customers_batch_{i:04d}.csv")

    # ---- POS defects
    pos = pd.DataFrame(pos_rows)
    pos["ingest_ts"] = pos["ingest_ts"].astype(object)
    for j in pos.index:
        if hit():
            pos.loc[j, "unit_price"] = -abs(pos.loc[j, "unit_price"]); bump("negative_price_pos")
        if hit():
            pos.loc[j, "product_id"] = "P99999"; bump("orphan_product_pos")
        if hit():
            pos.loc[j, "event_ts"] = _ts(end + timedelta(days=365)); bump("future_ts_pos")
        if hit():
            old = datetime.strptime(pos.loc[j, "event_ts"], "%Y-%m-%dT%H:%M:%SZ") - timedelta(days=rnd.randint(3, 10))
            pos.loc[j, "event_ts"] = _ts(old); bump("late_arriving_pos")
        if hit():
            pos.loc[j, "txn_id"] = None; bump("null_key_pos")
    dups = pos.sample(frac=DEFECT_RATE, random_state=seed)
    bump("duplicate_rows_pos", len(dups))
    pos = pd.concat([pos, dups], ignore_index=True)
    pos["_dt"] = pos["txn_ts"].str[:10]
    for dt, g in pos.groupby("_dt", sort=True):
        _write_jsonl(g.drop(columns="_dt"), out / "pos_transactions" / f"dt={dt}" / "part-0000.json")

    orders = pd.DataFrame(ord_rows)
    for j in orders.index:
        if hit():
            orders.loc[j, "customer_id"] = "C999999"; bump("orphan_customer_orders")
        if hit():
            orders.loc[j, "order_status"] = str(orders.loc[j, "order_status"]).title(); bump("case_noise_orders")
    _write_partitioned_jsonl(orders.assign(_k=orders.order_ts).drop(columns="_k"), out / "ecommerce_orders", "order_ts")

    # ---- inventory (parquet)
    pairs = [(rnd.choice(store_ids), rnd.choice(pids)) for _ in range(cfg["inv_pairs"])]
    pairs = sorted(set(pairs))
    state = {p: dict(on_hand=rnd.randint(10, 200), on_order=0, rp=rnd.randint(10, 40),
                     lr=(start - timedelta(days=rnd.randint(1, 20))).date().isoformat()) for p in pairs}
    for d in range(days):
        day = (start + timedelta(days=d)).date()
        rows = []
        for (s, p), st in state.items():
            st["on_hand"] = max(0, st["on_hand"] - int(rng.poisson(3)))
            if st["on_hand"] < st["rp"] and st["on_order"] == 0:
                st["on_order"] = 100
            elif st["on_order"] and rnd.random() < 0.3:
                st["on_hand"] += st["on_order"]; st["on_order"] = 0; st["lr"] = day.isoformat()
            rows.append(dict(snapshot_date=day.isoformat(), store_id=s, product_id=p, on_hand_qty=st["on_hand"],
                             on_order_qty=st["on_order"], reorder_point=st["rp"], last_received_date=st["lr"]))
        p_out = out / "inventory_snapshots" / f"dt={day.isoformat()}" / "part-0000.parquet"
        p_out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(p_out, index=False)

    # ---- loyalty
    accts = []
    for cid, lid in loyal.items():
        accts.append(dict(loyalty_id=lid, customer_id=cid, tier=_tier_for(spend.get(cid, 0.0)),
                          points_balance=0, enrolled_date=(start - timedelta(days=rnd.randint(1, 300))).date().isoformat(),
                          status=rnd.choices(["ACTIVE", "SUSPENDED", "CLOSED"], [90, 5, 5])[0],
                          updated_at=_ts(end)))
    lt = []
    earned: dict[str, int] = {}
    n = 0
    for txn_id, g in pos[pos.loyalty_id.notna() & pos.txn_id.notna()].groupby("txn_id", sort=True):
        net = float((g.unit_price.clip(lower=0) * g.quantity - g.discount_amount).sum())
        pts = int(net)
        if pts == 0:
            continue
        n += 1
        lid = g.loyalty_id.iloc[0]
        lt.append(dict(loyalty_txn_id=f"LT{n:08d}", loyalty_id=lid, event_type="EARN" if pts > 0 else "ADJUST",
                       points=pts, related_txn_id=txn_id, event_ts=g.txn_ts.iloc[0]))
        earned[lid] = earned.get(lid, 0) + pts
    for lid, tot in sorted(earned.items()):
        if tot > 200 and rnd.random() < 0.4:
            n += 1
            lt.append(dict(loyalty_txn_id=f"LT{n:08d}", loyalty_id=lid, event_type="REDEEM", points=-100,
                           related_txn_id=None, event_ts=_ts(end - timedelta(days=1))))
            earned[lid] -= 100
        if rnd.random() < 0.03:
            n += 1
            lt.append(dict(loyalty_txn_id=f"LT{n:08d}", loyalty_id=lid, event_type="EXPIRE", points=-10,
                           related_txn_id=None, event_ts=_ts(end - timedelta(days=1))))
            earned[lid] -= 10
    accts_df = pd.DataFrame(accts)
    accts_df["points_balance"] = accts_df.loyalty_id.map(earned).fillna(0).astype(int)
    lt_df = pd.DataFrame(lt)
    ndup = int(len(lt_df) * DEFECT_RATE)
    lt_df = pd.concat([lt_df, lt_df.head(ndup)], ignore_index=True)
    bump("duplicate_rows_loyalty_txn", ndup)
    _write_csv(accts_df, out / "loyalty_accounts" / "loyalty_accounts_0001.csv")
    _write_partitioned_jsonl(lt_df, out / "loyalty_transactions", "event_ts")
    _write_csv(stores_df, out / "stores" / "stores_0001.csv")
    _write_csv(promos_df, out / "promotions" / "promotions_0001.csv")

    manifest = {
        "seed": seed, "scale": scale, "start_date": start_date, "days": days, "defect_rate": DEFECT_RATE,
        "row_counts": {
            "customers": sum(len(r) for r in cchanges), "products": sum(len(r) for r in pchanges),
            "stores": len(stores_df), "promotions": len(promos_df), "pos_transactions": len(pos),
            "ecommerce_orders": len(orders),
            "inventory_snapshots": len(state) * days, "loyalty_accounts": len(accts_df),
            "loyalty_transactions": len(lt_df)},
        "defects": dict(sorted(defects.items())),
    }
    (out / "_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scale", choices=list(SCALES), default="small")
    ap.add_argument("--start-date", default="2025-01-01")
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args(argv)
    m = generate(a.out, a.seed, a.scale, a.start_date, a.days)
    print(json.dumps(m["row_counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
