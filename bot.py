"""Moving-average crossover bot for an Alpaca PAPER account.

Run once a day (e.g. at the market open):
    python bot.py            # places an order if a crossover happened
    python bot.py --dry-run  # shows what it would do, places nothing
    python bot.py --market btc --dry-run  # same strategy on BTC/USD (crypto trades 24/7)

    python bot.py --market stocks         # every symbol in config.UNIVERSE_FILE (the default)
    python bot.py --market crypto         # every coin in config.CRYPTO_UNIVERSE

Every run is logged to the console and appended to logs/bot_YYYY-MM-DD.log
(change the folder with --log-dir or the BOT_LOG_DIR environment variable).
"""

import argparse
import logging
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf
from dotenv import load_dotenv

import config
from config import Market
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


def drop_unfinished_bar(closes, asset_class: str, now: datetime):
    """Only use completed daily bars.

    Stocks: today's bar is unfinished until the 16:00 ET close.
    Crypto: yfinance daily bars are UTC days, so today's bar is unfinished until UTC midnight.
    """
    last_day = closes.index[-1].date()
    if asset_class == "crypto":
        unfinished = last_day >= now.astimezone(timezone.utc).date()
    else:
        now_ny = now.astimezone(NY)
        unfinished = now_ny.hour < 16 and last_day >= now_ny.date()
    return closes.iloc[:-1] if unfinished else closes


def fetch_closes(market: Market, days: int):
    if market.asset_class == "crypto":
        data = fetch_crypto_batch([market.data_symbol], days).get(market.data_symbol)
        if data is None:
            raise RuntimeError(f"Alpaca returned no data for {market.data_symbol}")
    else:
        data = yf.Ticker(market.data_symbol).history(period=f"{days}d", interval="1d", auto_adjust=True)
        if data.empty:
            raise RuntimeError(f"yfinance returned no data for {market.data_symbol}")
    closes = drop_unfinished_bar(data["Close"], market.asset_class, datetime.now(NY))
    if len(closes) < len(data):
        log.info("Dropping today's unfinished bar (%s); using completed days only", data.index[-1].date())
    return closes


def fetch_history_batch(tickers: list[str], days: int, chunk: int = 200) -> dict:
    """Daily bars for many yfinance tickers at once: {ticker: DataFrame with Close and Volume}."""
    out = {}
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        data = yf.download(part, period=f"{days}d", interval="1d", auto_adjust=True,
                           progress=False, group_by="ticker", threads=True)
        for t in part:
            if t in data.columns.get_level_values(0):
                bars = data[t].dropna(subset=["Close"])
                if not bars.empty:
                    out[t] = bars
        log.info("Downloaded %d/%d tickers", min(i + chunk, len(tickers)), len(tickers))
    return out


def fetch_crypto_batch(symbols: list[str], days: int) -> dict:
    """Daily crypto bars from Alpaca market data (UTC days): {symbol: DataFrame with Close and Volume}."""
    from datetime import timedelta

    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame

    request = CryptoBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Day,
                                start=datetime.now(timezone.utc) - timedelta(days=days))
    df = CryptoHistoricalDataClient().get_crypto_bars(request).df
    if df.empty:
        return {}
    df = df.rename(columns={"close": "Close", "volume": "Volume"})
    return {s: df.xs(s)[["Close", "Volume"]] for s in df.index.get_level_values(0).unique()}


def load_universe(path=None) -> list[Market]:
    path = Path(path or config.UNIVERSE_FILE)
    symbols = [line.split("#")[0].strip() for line in path.read_text().splitlines()]
    return [Market(s, s.replace(".", "-"), "stock", config.STOCK_TRADE_SIZE) for s in symbols if s]


def crypto_universe() -> list[Market]:
    # trade_size is set per run from the price and CRYPTO_ORDER_USD
    return [Market(s, s, "crypto", 0) for s in config.CRYPTO_UNIVERSE]


UNIVERSES = {
    "stocks": (load_universe, "MAX_BUYS_PER_RUN"),
    "crypto": (crypto_universe, "MAX_CRYPTO_BUYS_PER_RUN"),
}


def position_key(symbol: str) -> str:
    """Alpaca reports crypto positions without the slash (BTC/USD -> BTCUSD); compare symbols this way."""
    return symbol.replace("/", "")


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
        # Positions use the symbol without the slash (BTC/USD -> BTCUSD).
        return float(client.get_open_position(symbol.replace("/", "")).qty)
    except APIError:
        return 0.0


def has_open_order(client, symbol: str) -> bool:
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))
    return len(orders) > 0


def time_in_force(asset_class: str):
    from alpaca.trading.enums import TimeInForce

    # Alpaca crypto orders accept only GTC or IOC, not DAY.
    return TimeInForce.GTC if asset_class == "crypto" else TimeInForce.DAY


def place_order(client, market: Market, qty: float, side: str):
    from alpaca.trading.enums import OrderSide
    from alpaca.trading.requests import MarketOrderRequest

    order = client.submit_order(MarketOrderRequest(
        symbol=market.symbol,
        qty=qty,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=time_in_force(market.asset_class),
    ))
    log.info("Order submitted: %s %g %s (id %s, status %s)", side, qty, market.symbol, order.id, order.status.value)
    return order


def run(market: Market, dry_run: bool) -> str:
    """One bot run. Returns a one-line outcome."""
    sym = market.symbol
    closes = fetch_closes(market, config.LOOKBACK_DAYS)
    log.info("Fetched %d daily closes for %s (%s to %s)", len(closes), market.data_symbol,
             closes.index[0].date(), closes.index[-1].date())
    df = add_moving_averages(closes, config.FAST_MA_PERIOD, config.SLOW_MA_PERIOD)
    signal = crossover_signal(df)

    for date, row in df.dropna().iloc[-2:].iterrows():
        log.info("%s  close %.2f  MA%d %.2f  MA%d %.2f", date.date(), row.close,
                 config.FAST_MA_PERIOD, row.fast_ma, config.SLOW_MA_PERIOD, row.slow_ma)
    log.info("Signal: %s", signal.value.upper())

    if signal is Signal.HOLD:
        return f"{sym} HOLD: no crossover, no order"
    if dry_run:
        return f"{sym} {signal.value.upper()}: dry run, would {signal.value} {market.trade_size:g}, no order placed"

    client = trading_client()
    if has_open_order(client, sym):
        return f"{sym} {signal.value.upper()}: an order is already open, not placing another"
    qty = held_qty(client, sym)
    log.info("Current %s position: %g", sym, qty)

    if signal is Signal.BUY:
        if qty > 0:
            return f"{sym} BUY: already holding {qty:g}, skipped"
        order = place_order(client, market, market.trade_size, "buy")
    else:
        if qty <= 0:
            return f"{sym} SELL: no position to sell, skipped (never sells short)"
        order = place_order(client, market, min(market.trade_size, qty), "sell")
    return f"{sym} {signal.value.upper()}: order {order.id} submitted ({order.status.value})"


def plan_orders(buys: list[Market], sells: list[Market], positions: dict, open_symbols: set, max_buys: int):
    """Decide which signals become orders. Returns (orders, notes), orders as (market, side, qty).

    Sells first, only for symbols held (never short). Buys in the given order (most traded first),
    skipping symbols already held, and at most max_buys of them. Symbols with an open order are skipped.
    """
    positions = {position_key(k): v for k, v in positions.items()}
    open_symbols = {position_key(k) for k in open_symbols}
    orders, notes = [], []
    for m in sells:
        qty = positions.get(position_key(m.symbol), 0.0)
        if position_key(m.symbol) in open_symbols:
            notes.append(f"{m.symbol} SELL skipped: order already open")
        elif qty <= 0:
            notes.append(f"{m.symbol} SELL skipped: not held")
        else:
            orders.append((m, "sell", min(m.trade_size, qty)))
    n_buys = 0
    for m in buys:
        if position_key(m.symbol) in open_symbols:
            notes.append(f"{m.symbol} BUY skipped: order already open")
        elif positions.get(position_key(m.symbol), 0.0) > 0:
            notes.append(f"{m.symbol} BUY skipped: already held")
        elif n_buys >= max_buys:
            notes.append(f"{m.symbol} BUY skipped: limit of {max_buys} buys per run reached")
        else:
            orders.append((m, "buy", m.trade_size))
            n_buys += 1
    return orders, notes


def run_universe(markets: list[Market], dry_run: bool, max_buys: int) -> str:
    """One run over many symbols: batch download, one log line per symbol, then capped orders."""
    log.info("Universe: %d symbols", len(markets))
    stock_tickers = [m.data_symbol for m in markets if m.asset_class != "crypto"]
    crypto_symbols = [m.data_symbol for m in markets if m.asset_class == "crypto"]
    bars = fetch_history_batch(stock_tickers, config.LOOKBACK_DAYS) if stock_tickers else {}
    if crypto_symbols:
        bars.update(fetch_crypto_batch(crypto_symbols, config.LOOKBACK_DAYS))
    now = datetime.now(NY)
    buys, sells, n_hold, n_skipped = [], [], 0, 0
    for m in markets:
        if m.data_symbol not in bars:
            log.info("%-6s no price data, skipped", m.symbol)
            n_skipped += 1
            continue
        closes = drop_unfinished_bar(bars[m.data_symbol]["Close"], m.asset_class, now)
        try:
            df = add_moving_averages(closes, config.FAST_MA_PERIOD, config.SLOW_MA_PERIOD)
            signal = crossover_signal(df)
        except ValueError as exc:
            log.info("%-6s skipped: %s", m.symbol, exc)
            n_skipped += 1
            continue
        r = df.iloc[-1]
        if m.asset_class == "crypto":
            m = replace(m, trade_size=round(config.CRYPTO_ORDER_USD / r.close, 9))
        log.info("%-6s %s  close %.6g  MA%d %.6g  MA%d %.6g  %s", m.symbol, df.index[-1].date(), r.close,
                 config.FAST_MA_PERIOD, r.fast_ma, config.SLOW_MA_PERIOD, r.slow_ma, signal.value.upper())
        if signal is Signal.BUY:
            buys.append(m)
        elif signal is Signal.SELL:
            sells.append(m)
        else:
            n_hold += 1
    summary = (f"{len(markets)} symbols: {len(buys)} BUY [{' '.join(m.symbol for m in buys)}], "
               f"{len(sells)} SELL [{' '.join(m.symbol for m in sells)}], {n_hold} HOLD, {n_skipped} skipped")
    log.info("Signals: %s", summary)
    if dry_run:
        return f"{summary}; dry run, no orders placed"

    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    client = trading_client()
    positions = {p.symbol: float(p.qty) for p in client.get_all_positions()}
    open_symbols = {o.symbol for o in client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500))}
    orders, notes = plan_orders(buys, sells, positions, open_symbols, max_buys)
    for note in notes:
        log.info(note)
    placed, failed = [], []
    for m, side, qty in orders:
        try:
            place_order(client, m, qty, side)
            placed.append(f"{side} {qty:g} {m.symbol}")
        except Exception as exc:
            log.error("%s %s failed: %s", side, m.symbol, exc)
            failed.append(m.symbol)
    result = f"{summary}; orders placed: {', '.join(placed) or 'none'}"
    if failed:
        result += f"; failed: {' '.join(failed)}"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="compute the signal but place no order")
    parser.add_argument("--market", choices=sorted(config.MARKETS) + sorted(UNIVERSES), default=os.getenv("BOT_MARKET", config.DEFAULT_MARKET),
                        help="what to trade, from config.MARKETS (default: %(default)s)")
    parser.add_argument("--log-dir", default=os.getenv("BOT_LOG_DIR", "logs"), help="folder for daily log files")
    args = parser.parse_args()
    if args.market not in UNIVERSES and args.market not in config.MARKETS:
        parser.error(f"unknown market {args.market!r}; choose from {', '.join(sorted(UNIVERSES) + sorted(config.MARKETS))}")

    log_file = setup_logging(args.log_dir)
    mode = "dry run" if args.dry_run else "live, paper account"
    try:
        if args.market in UNIVERSES:
            load, cap_setting = UNIVERSES[args.market]
            log.info("=== Run started: %s universe (%s) ===", args.market, mode)
            outcome = run_universe(load(), args.dry_run, getattr(config, cap_setting))
        else:
            market = config.MARKETS[args.market]
            log.info("=== Run started: %s (%s) ===", market.symbol, mode)
            outcome = run(market, args.dry_run)
    except Exception as exc:
        log.exception("Run failed: %s", exc)
        log.info("RESULT: ERROR %s", exc)
        log.info("Log file: %s", log_file)
        sys.exit(1)
    log.info("RESULT: %s", outcome)
    log.info("Log file: %s", log_file)


if __name__ == "__main__":
    main()
