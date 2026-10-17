"""Moving-average crossover bot for an Alpaca PAPER account.

Run once a day (e.g. at the market open):
    python bot.py            # places an order if a crossover happened
    python bot.py --dry-run  # shows what it would do, places nothing

Every run is logged to the console and appended to logs/bot_YYYY-MM-DD.log
(change the folder with --log-dir or the BOT_LOG_DIR environment variable).
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf
from dotenv import load_dotenv

import config
from strategy import Signal, add_moving_averages, crossover_signal

NY = ZoneInfo("America/New_York")
log = logging.getLogger("bot")


def setup_logging(log_dir: str) -> Path:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    log_file = path / f"bot_{datetime.now(NY):%Y-%m-%d}.log"
    fmt = logging.Formatter("%(asctime)s ET %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    fmt.converter = lambda ts: datetime.fromtimestamp(ts, NY).timetuple()
    for handler in (logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    return log_file


def fetch_closes(symbol: str, days: int):
    data = yf.Ticker(symbol).history(period=f"{days}d", interval="1d", auto_adjust=True)
    if data.empty:
        raise RuntimeError(f"yfinance returned no data for {symbol}")
    closes = data["Close"]
    # During market hours yfinance includes today's unfinished bar; only use completed days.
    now = datetime.now(NY)
    if now.hour < 16 and closes.index[-1].date() >= now.date():
        log.info("Dropping today's unfinished bar (%s); using completed days only", closes.index[-1].date())
        closes = closes.iloc[:-1]
    return closes


def trading_client():
    from alpaca.trading.client import TradingClient

    load_dotenv()  # values in .env; real environment variables win if already set
    key = os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("APCA_API_SECRET_KEY")
    base_url = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
    if not key or not secret:
        raise RuntimeError("Missing APCA_API_KEY_ID / APCA_API_SECRET_KEY. Copy .env.example to .env and fill it in.")
    if "paper-api" not in base_url:
        raise RuntimeError(f"Refusing to run: APCA_API_BASE_URL is not a paper trading URL ({base_url}).")
    return TradingClient(key, secret, paper=True)


def held_qty(client, symbol: str) -> float:
    from alpaca.common.exceptions import APIError

    try:
        return float(client.get_open_position(symbol).qty)
    except APIError:
        return 0.0


def has_open_order(client, symbol: str) -> bool:
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))
    return len(orders) > 0


def place_order(client, symbol: str, qty: float, side: str):
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    order = client.submit_order(MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    ))
    log.info("Order submitted: %s %g %s (id %s, status %s)", side, qty, symbol, order.id, order.status.value)
    return order


def run(dry_run: bool) -> str:
    """One bot run. Returns a one-line outcome."""
    closes = fetch_closes(config.SYMBOL, config.LOOKBACK_DAYS)
    log.info("Fetched %d daily closes for %s (%s to %s)", len(closes), config.SYMBOL,
             closes.index[0].date(), closes.index[-1].date())
    df = add_moving_averages(closes, config.FAST_MA_PERIOD, config.SLOW_MA_PERIOD)
    signal = crossover_signal(df)

    for date, row in df.dropna().iloc[-2:].iterrows():
        log.info("%s  close %.2f  MA%d %.2f  MA%d %.2f", date.date(), row.close,
                 config.FAST_MA_PERIOD, row.fast_ma, config.SLOW_MA_PERIOD, row.slow_ma)
    log.info("Signal: %s", signal.value.upper())

    if signal is Signal.HOLD:
        return f"{config.SYMBOL} HOLD: no crossover, no order"
    if dry_run:
        return f"{config.SYMBOL} {signal.value.upper()}: dry run, would {signal.value} {config.TRADE_SIZE}, no order placed"

    client = trading_client()
    if has_open_order(client, config.SYMBOL):
        return f"{config.SYMBOL} {signal.value.upper()}: an order is already open, not placing another"
    qty = held_qty(client, config.SYMBOL)
    log.info("Current %s position: %g shares", config.SYMBOL, qty)

    if signal is Signal.BUY:
        if qty > 0:
            return f"{config.SYMBOL} BUY: already holding {qty:g}, skipped"
        order = place_order(client, config.SYMBOL, config.TRADE_SIZE, "buy")
    else:
        if qty <= 0:
            return f"{config.SYMBOL} SELL: no position to sell, skipped (never sells short)"
        order = place_order(client, config.SYMBOL, min(config.TRADE_SIZE, qty), "sell")
    return f"{config.SYMBOL} {signal.value.upper()}: order {order.id} submitted ({order.status.value})"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="compute the signal but place no order")
    parser.add_argument("--log-dir", default=os.getenv("BOT_LOG_DIR", "logs"), help="folder for daily log files")
    args = parser.parse_args()

    log_file = setup_logging(args.log_dir)
    log.info("=== Run started (%s) ===", "dry run" if args.dry_run else "live, paper account")
    try:
        outcome = run(args.dry_run)
    except Exception as exc:
        log.exception("Run failed: %s", exc)
        log.info("RESULT: ERROR %s", exc)
        log.info("Log file: %s", log_file)
        sys.exit(1)
    log.info("RESULT: %s", outcome)
    log.info("Log file: %s", log_file)


if __name__ == "__main__":
    main()
