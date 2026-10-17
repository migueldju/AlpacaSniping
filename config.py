"""Bot settings. Edit these values to change what the bot trades."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Market:
    symbol: str        # Alpaca symbol (crypto uses a slash, e.g. BTC/USD)
    data_symbol: str   # ticker for price data: yfinance for stocks, Alpaca symbol for crypto
    asset_class: str   # "stock" or "crypto"
    trade_size: float  # units per order (shares, or coins for crypto)


# Pick one with `python bot.py --market btc` or the BOT_MARKET environment variable.
# `--market stocks` runs every symbol in UNIVERSE_FILE and `--market crypto` every coin in CRYPTO_UNIVERSE.
MARKETS = {
    "aapl": Market(symbol="AAPL", data_symbol="AAPL", asset_class="stock", trade_size=1),
    "btc": Market(symbol="BTC/USD", data_symbol="BTC/USD", asset_class="crypto", trade_size=0.001),
}
DEFAULT_MARKET = "stocks"

# The "stocks" universe: every liquid US stock/ETF on Alpaca, one symbol per line, most traded first.
# Rebuild it with `python build_universe.py` (it applies MIN_DOLLAR_VOLUME).
UNIVERSE_FILE = Path(__file__).resolve().parent / "universe_stocks.txt"
MIN_DOLLAR_VOLUME = 20_000_000  # average daily traded value over 20 days, in USD
STOCK_TRADE_SIZE = 1            # shares per order for universe symbols
MAX_BUYS_PER_RUN = 5            # at most this many new buys per run (most traded first); sells are not capped

# The "crypto" universe: every non-stablecoin USD pair on Alpaca. Crypto prices come from Alpaca's own
# market data (exact to the last decimal, unlike Yahoo, which rounds coins like PEPE to $0.000001).
CRYPTO_UNIVERSE = [
    "BTC/USD", "ETH/USD", "XRP/USD", "SOL/USD", "HYPE/USD", "DOGE/USD", "LINK/USD", "ADA/USD", "BCH/USD",
    "LTC/USD", "UNI/USD", "AVAX/USD", "AAVE/USD", "ONDO/USD", "DOT/USD", "PAXG/USD", "SKY/USD", "ARB/USD",
    "POL/USD", "RENDER/USD", "FIL/USD", "CRV/USD", "TRUMP/USD", "XTZ/USD", "LDO/USD", "BAT/USD", "GRT/USD",
    "WIF/USD", "YFI/USD", "SUSHI/USD", "SHIB/USD", "PEPE/USD", "BONK/USD",
]
CRYPTO_ORDER_USD = 100       # dollars per crypto buy (coin prices differ too much for a fixed quantity)
MAX_CRYPTO_BUYS_PER_RUN = 3  # at most this many new crypto buys per run; sells are not capped

FAST_MA_PERIOD = 20    # short moving average, in daily bars
SLOW_MA_PERIOD = 50    # long moving average, in daily bars
LOOKBACK_DAYS = 100    # days of history to download
