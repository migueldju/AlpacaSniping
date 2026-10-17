"""Bot settings. Edit these values to change what the bot trades."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    symbol: str        # Alpaca symbol (crypto uses a slash, e.g. BTC/USD)
    data_symbol: str   # yfinance ticker for the same asset (e.g. BTC-USD)
    asset_class: str   # "stock" or "crypto"
    trade_size: float  # units per order (shares, or coins for crypto)


# Pick one with `python bot.py --market btc` or the BOT_MARKET environment variable.
MARKETS = {
    "aapl": Market(symbol="AAPL", data_symbol="AAPL", asset_class="stock", trade_size=1),
    "btc": Market(symbol="BTC/USD", data_symbol="BTC-USD", asset_class="crypto", trade_size=0.001),
}
DEFAULT_MARKET = "aapl"

FAST_MA_PERIOD = 20    # short moving average, in daily bars
SLOW_MA_PERIOD = 50    # long moving average, in daily bars
LOOKBACK_DAYS = 100    # days of history to download from yfinance
