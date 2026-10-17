"""Rebuild config.UNIVERSE_FILE: every liquid US stock/ETF tradable on Alpaca, most traded first.

    python build_universe.py

Takes Alpaca's active, tradable, fractionable and marginable assets on NYSE, NASDAQ, ARCA, AMEX and BATS,
downloads 100 days of yfinance data, and keeps symbols whose average daily traded value over the last
20 days is at least config.MIN_DOLLAR_VOLUME and that have enough history for the slow moving average.
Places no orders.
"""

import logging
import sys
from datetime import date

import config
from bot import fetch_history_batch, log, trading_client

EXCHANGES = {"NYSE", "NASDAQ", "ARCA", "AMEX", "BATS"}


def main():
    from alpaca.trading.enums import AssetClass, AssetStatus
    from alpaca.trading.requests import GetAssetsRequest

    logging.basicConfig(stream=sys.stdout, format="%(message)s")
    log.setLevel(logging.INFO)
    assets = trading_client().get_all_assets(GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status=AssetStatus.ACTIVE))
    symbols = sorted(a.symbol for a in assets
                     if a.tradable and a.fractionable and a.marginable and a.exchange.value in EXCHANGES)
    log.info("%d candidate symbols on Alpaca", len(symbols))
    tickers = {s: s.replace(".", "-") for s in symbols}
    bars = fetch_history_batch(list(tickers.values()), config.LOOKBACK_DAYS)

    liquid = []
    for s, t in tickers.items():
        b = bars.get(t)
        if b is None or len(b) < config.SLOW_MA_PERIOD + 2:
            continue
        dollar_volume = (b["Close"] * b["Volume"]).tail(20).mean()
        if dollar_volume >= config.MIN_DOLLAR_VOLUME:
            liquid.append((dollar_volume, s))
    liquid.sort(reverse=True)

    header = (f"# Built {date.today()} by build_universe.py: {len(liquid)} symbols with average daily traded value "
              f">= ${config.MIN_DOLLAR_VOLUME:,.0f}, most traded first.\n")
    config.UNIVERSE_FILE.write_text(header + "".join(f"{s}\n" for _, s in liquid))
    log.info("Wrote %d symbols to %s", len(liquid), config.UNIVERSE_FILE)


if __name__ == "__main__":
    main()
