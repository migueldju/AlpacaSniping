"""Moving-average crossover bot for an Alpaca PAPER account.

Run once a day after the market closes (or before it opens):
    python bot.py            # places an order if a crossover happened
    python bot.py --dry-run  # shows what it would do, places nothing
"""

import argparse
import os
import sys

import yfinance as yf
from dotenv import load_dotenv

import config
from strategy import Signal, add_moving_averages, crossover_signal


def fetch_closes(symbol: str, days: int):
    data = yf.Ticker(symbol).history(period=f"{days}d", interval="1d", auto_adjust=True)
    if data.empty:
        raise RuntimeError(f"yfinance returned no data for {symbol}")
    return data["Close"]


def trading_client():
    from alpaca.trading.client import TradingClient

    load_dotenv()  # values in .env; real environment variables win if already set
    key = os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("APCA_API_SECRET_KEY")
    base_url = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
    if not key or not secret:
        sys.exit("Missing APCA_API_KEY_ID / APCA_API_SECRET_KEY. Copy .env.example to .env and fill it in.")
    if "paper-api" not in base_url:
        sys.exit(f"Refusing to run: APCA_API_BASE_URL is not a paper trading URL ({base_url}).")
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
    print(f"Order submitted: {side} {qty} {symbol} (id {order.id}, status {order.status})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="compute the signal but place no order")
    args = parser.parse_args()

    closes = fetch_closes(config.SYMBOL, config.LOOKBACK_DAYS)
    df = add_moving_averages(closes, config.FAST_MA_PERIOD, config.SLOW_MA_PERIOD)
    signal = crossover_signal(df)

    last = df.dropna().iloc[-2:]
    print(f"{config.SYMBOL}: {len(closes)} days of data")
    for date, row in last.iterrows():
        print(f"  {date.date()}  close {row.close:8.2f}  MA{config.FAST_MA_PERIOD} {row.fast_ma:8.2f}"
              f"  MA{config.SLOW_MA_PERIOD} {row.slow_ma:8.2f}")
    print(f"Signal: {signal.value.upper()}")

    if signal is Signal.HOLD:
        return
    if args.dry_run:
        print(f"Dry run: would {signal.value} {config.TRADE_SIZE} {config.SYMBOL}. No order placed.")
        return

    client = trading_client()
    if has_open_order(client, config.SYMBOL):
        print("An order for this symbol is already open; not placing another.")
        return
    qty = held_qty(client, config.SYMBOL)

    if signal is Signal.BUY:
        if qty > 0:
            print(f"Already holding {qty:g} {config.SYMBOL}; skipping buy.")
            return
        place_order(client, config.SYMBOL, config.TRADE_SIZE, "buy")
    else:
        if qty <= 0:
            print(f"No {config.SYMBOL} position to sell; skipping (the bot never sells short).")
            return
        place_order(client, config.SYMBOL, min(config.TRADE_SIZE, qty), "sell")


if __name__ == "__main__":
    main()
