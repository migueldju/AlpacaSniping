"""Export the paper account to JSON files for the results dashboard. Places no orders.

    python export_dashboard.py --out dashboard_data --log-dir /mnt/project-files/AlpacaSniping/logs

Writes account.json (one row), positions.json, orders.json (last 200), equity_daily.json (daily equity and
P&L for the last year) and runs.json (the RESULT line of every logged bot run).
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import config
from bot import NY, trading_client


def num(x):
    return None if x is None else float(x)


def account_row(acct, positions) -> dict:
    equity, last = float(acct.equity), float(acct.last_equity)
    invested = sum(float(p.market_value) for p in positions)
    return {
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "equity": equity, "cash": float(acct.cash), "last_equity": last,
        "day_pl": round(equity - last, 2), "day_pl_pct": round((equity / last - 1), 6) if last else 0.0,
        "invested": round(invested, 2), "invested_pct": round(invested / equity, 6) if equity else 0.0,
        "positions": len(positions),
        "max_invested_pct": config.MAX_INVESTED_PCT, "max_position_pct": config.MAX_POSITION_PCT,
        "stop_loss_pct": config.STOP_LOSS_PCT,
    }


def position_rows(positions, equity: float) -> list[dict]:
    return [{
        "symbol": p.symbol, "asset_class": p.asset_class.value, "qty": float(p.qty),
        "avg_entry_price": float(p.avg_entry_price), "current_price": float(p.current_price),
        "market_value": float(p.market_value), "unrealized_pl": float(p.unrealized_pl),
        "unrealized_plpc": float(p.unrealized_plpc),
        "pct_of_equity": round(float(p.market_value) / equity, 6) if equity else 0.0,
        "stop_price": round(float(p.avg_entry_price) * (1 - config.STOP_LOSS_PCT), 6),
    } for p in positions]


def order_rows(orders) -> list[dict]:
    return [{
        "submitted_at": o.submitted_at.isoformat(timespec="seconds") if o.submitted_at else None,
        "symbol": o.symbol, "side": o.side.value, "qty": num(o.qty), "notional": num(o.notional),
        "filled_qty": num(o.filled_qty), "filled_avg_price": num(o.filled_avg_price), "status": o.status.value,
    } for o in orders]


def equity_rows(history) -> list[dict]:
    rows = []
    for ts, eq, pl, plpc in zip(history.timestamp or [], history.equity or [], history.profit_loss or [],
                                history.profit_loss_pct or []):
        if not eq:  # days before the account existed
            continue
        rows.append({"date": datetime.fromtimestamp(ts, NY).strftime("%Y-%m-%d"), "equity": eq,
                     "pl": pl or 0.0, "pl_pct": plpc or 0.0})
    return rows


RESULT = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ET INFO\s+RESULT: (.*)$")


def run_rows(log_dir: Path) -> list[dict]:
    rows = []
    for f in sorted(log_dir.glob("bot_*.log")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = RESULT.match(line)
            if m:
                rows.append({"at": m[1], "result": m[2][:500], "error": m[2].startswith("ERROR")})
    return rows[::-1]


def main():
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest, GetPortfolioHistoryRequest

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="dashboard_data", help="folder for the JSON files")
    parser.add_argument("--log-dir", default="logs", help="folder with the bot's daily log files")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    client = trading_client()
    acct, positions = client.get_account(), client.get_all_positions()
    orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL, limit=200, direction="desc"))
    history = client.get_portfolio_history(GetPortfolioHistoryRequest(period="1A", timeframe="1D"))
    files = {
        "account.json": [account_row(acct, positions)],
        "positions.json": position_rows(positions, float(acct.equity)),
        "orders.json": order_rows(orders),
        "equity_daily.json": equity_rows(history),
        "runs.json": run_rows(Path(args.log_dir)),
    }
    for name, rows in files.items():
        (out / name).write_text(json.dumps(rows, indent=1))
        print(f"{name}: {len(rows)} rows")


if __name__ == "__main__":
    main()
