"""Backtest the moving-average crossover strategy on daily yfinance data. Places no orders.

    python backtest.py                      # AAPL + a sample of the stock universe, last 10 years
    python backtest.py --symbols AAPL MSFT  # only these
    python backtest.py --years 5 --sample 50 --out results.csv

Each symbol is traded on its own: all in on a buy crossover, all out on a sell crossover (or the stop-loss).
The portfolio gives every symbol the same share of the starting capital and adds up their equity curves,
so it measures the signal itself, not the live bot's order caps. Variants compared:

    base_next_open   20/50 crossover, order at the next day's open (the old 9:30 ET schedule)
    base_close       20/50 crossover, order at the close of the crossover day (the 15:50 ET schedule)
    trend            base_close + buy only above the 200-day average
    trend_stop       trend + sell when the price is STOP_LOSS_PCT below the entry price

Caveat: the sample comes from today's universe of liquid stocks, so it leaves out companies that were
delisted over the period (survivorship bias); real results would likely be somewhat worse.
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

import config
from bot import load_universe

log = logging.getLogger("backtest")
COST = 0.0005  # 0.05% slippage per trade side (Alpaca charges no commission)


@dataclass(frozen=True)
class Variant:
    name: str
    at_close: bool   # True: fill at the signal day's close; False: at the next day's open
    trend: int       # trend filter period (0 = off)
    stop_pct: float  # stop-loss below entry (0 = off)


VARIANTS = [
    Variant("base_next_open", False, 0, 0),
    Variant("base_close", True, 0, 0),
    Variant("trend", True, config.TREND_MA_PERIOD, 0),
    Variant("trend_stop", True, config.TREND_MA_PERIOD, config.STOP_LOSS_PCT),
]


def simulate(bars: pd.DataFrame, v: Variant, start: pd.Timestamp):
    """Daily equity (starting at 1.0 on start) and the list of closed trade returns for one symbol."""
    close, opn = bars["Close"].to_numpy(float), bars["Open"].to_numpy(float)
    fast = bars["Close"].rolling(config.FAST_MA_PERIOD).mean().to_numpy()
    slow = bars["Close"].rolling(config.SLOW_MA_PERIOD).mean().to_numpy()
    trend = bars["Close"].rolling(v.trend).mean().to_numpy() if v.trend else None
    first = int(np.searchsorted(bars.index, start))
    equity, invested = np.ones(len(bars)), np.zeros(len(bars), bool)
    cash, units, entry, pending, trades = 1.0, 0.0, 0.0, None, []

    def buy(price):
        nonlocal cash, units, entry
        units, entry, cash = cash * (1 - COST) / price, price, 0.0

    def sell(price):
        nonlocal cash, units
        cash, units = units * price * (1 - COST), 0.0
        trades.append(price * (1 - COST) ** 2 / entry - 1)

    for i in range(first, len(bars)):
        if pending == "buy":
            buy(opn[i])
        elif pending == "sell":
            sell(opn[i])
        pending = None
        crossed_up = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]
        crossed_down = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]
        action = None
        if units == 0 and crossed_up and (trend is None or close[i] > trend[i]):
            action = "buy"
        elif units > 0 and (crossed_down or (v.stop_pct and close[i] <= entry * (1 - v.stop_pct))):
            action = "sell"
        if action and v.at_close:
            buy(close[i]) if action == "buy" else sell(close[i])
        else:
            pending = action
        equity[i], invested[i] = cash + units * close[i], units > 0
    if units > 0:  # count an open position at the last close as a trade too
        trades.append(close[-1] / entry - 1)
    idx = bars.index[first:]
    return pd.Series(equity[first:], index=idx), trades, pd.Series(invested[first:], index=idx)


def metrics(equity: pd.Series, trades: list, exposure: float = 1.0) -> dict:
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    total = equity.iloc[-1] / equity.iloc[0] - 1
    drawdown = (equity / equity.cummax() - 1).min()
    daily = equity.pct_change().dropna()
    return {
        "total_return_%": round(total * 100, 1),
        "cagr_%": round(((1 + total) ** (1 / years) - 1) * 100, 2),
        "max_drawdown_%": round(drawdown * 100, 1),
        "sharpe": round(daily.mean() / daily.std() * np.sqrt(252), 2) if daily.std() > 0 else 0.0,
        "trades": len(trades),
        "win_rate_%": round(100 * np.mean([t > 0 for t in trades]), 1) if trades else 0.0,
        "avg_trade_%": round(100 * np.mean(trades), 2) if trades else 0.0,
        "time_invested_%": round(100 * exposure, 1),
    }


def sample_symbols(n: int) -> list[str]:
    """AAPL, SPY, plus n symbols spread evenly over the universe (most to least traded)."""
    universe = [m.data_symbol for m in load_universe()]
    step = max(1, len(universe) // n)
    picked = ["AAPL", "SPY"] + universe[::step][:n]
    return list(dict.fromkeys(picked))


def download(symbols: list[str], start: date) -> dict:
    data = yf.download(symbols, start=start.isoformat(), interval="1d", auto_adjust=True,
                       progress=False, group_by="ticker", threads=True)
    out = {}
    for s in symbols:
        if s in data.columns.get_level_values(0):
            bars = data[s].dropna(subset=["Open", "Close"])
            if len(bars) > config.TREND_MA_PERIOD:
                out[s] = bars
    return out


def run(symbols: list[str], years: int):
    end = date.today()
    start = pd.Timestamp(end - timedelta(days=round(365.25 * years)))
    warmup = start.date() - timedelta(days=round(config.TREND_MA_PERIOD * 1.6))
    bars = download(symbols, warmup)
    # only symbols that already traded when the test starts, so every one is in the market the whole period
    bars = {s: b for s, b in bars.items() if b.index[0].tz_localize(None) <= pd.Timestamp(warmup) + timedelta(days=10)}
    log.info("%d of %d symbols have data since %s", len(bars), len(symbols), warmup)

    rows, curves = [], {}
    for v in VARIANTS:
        per_symbol, all_trades, in_market = [], [], []
        for s, b in bars.items():
            b = b.tz_localize(None) if b.index.tz is not None else b
            eq, trades, invested = simulate(b, v, start)
            per_symbol.append(eq)
            all_trades += trades
            in_market.append(invested.mean())
            if s == "AAPL":
                rows.append({"variant": v.name, "scope": "AAPL", **metrics(eq, trades, invested.mean())})
        portfolio = pd.concat(per_symbol, axis=1).ffill().fillna(1.0).mean(axis=1)
        curves[v.name] = portfolio
        rows.append({"variant": v.name, "scope": f"portfolio ({len(bars)} symbols)", **metrics(portfolio, all_trades, np.mean(in_market))})

    hold = pd.concat([b.tz_localize(None)["Close"] if b.index.tz is not None else b["Close"]
                      for b in bars.values()], axis=1).loc[start:].ffill()
    hold = (hold / hold.iloc[0]).mean(axis=1)
    rows.append({"variant": "buy_and_hold", "scope": f"portfolio ({len(bars)} symbols)", **metrics(hold, [])})
    for s in ("SPY", "AAPL"):
        if s in bars:
            c = bars[s]["Close"]
            c = c.tz_localize(None) if c.index.tz is not None else c
            rows.append({"variant": "buy_and_hold", "scope": s, **metrics(c.loc[start:], [])})
    curves["buy_and_hold"] = hold
    return pd.DataFrame(rows), pd.DataFrame(curves)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", nargs="*", help="yfinance tickers (default: AAPL, SPY and a universe sample)")
    parser.add_argument("--sample", type=int, default=100, help="universe symbols to sample (default %(default)s)")
    parser.add_argument("--years", type=int, default=10, help="years to test (default %(default)s)")
    parser.add_argument("--out", help="write the results table to this CSV (and the equity curves next to it)")
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stdout, format="%(message)s", level=logging.INFO)

    results, curves = run(args.symbols or sample_symbols(args.sample), args.years)
    pd.set_option("display.width", 200)
    print(results.to_string(index=False))
    if args.out:
        results.to_csv(args.out, index=False)
        curves.to_csv(args.out.removesuffix(".csv") + "_equity.csv")


if __name__ == "__main__":
    main()
