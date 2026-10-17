"""Bot settings. Edit these values to change what the bot trades."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Market:
    symbol: str        # Alpaca symbol (crypto uses a slash, e.g. BTC/USD)
    data_symbol: str   # yfinance ticker for the same asset (e.g. BTC-USD)
    asset_class: str   # "stock" or "crypto"
    trade_size: float  # units per order (shares, or coins for crypto)


# Pick one with `python bot.py --market btc` or the BOT_MARKET environment variable.
# `--market stocks` runs every symbol in UNIVERSE_FILE and `--market crypto` every coin in CRYPTO_UNIVERSE.
MARKETS = {
    "aapl": Market(symbol="AAPL", data_symbol="AAPL", asset_class="stock", trade_size=1),
    "btc": Market(symbol="BTC/USD", data_symbol="BTC-USD", asset_class="crypto", trade_size=0.001),
}
DEFAULT_MARKET = "stocks"

# The "stocks" universe: every liquid US stock/ETF on Alpaca, one symbol per line, most traded first.
# Rebuild it with `python build_universe.py` (it applies MIN_DOLLAR_VOLUME).
UNIVERSE_FILE = Path(__file__).resolve().parent / "universe_stocks.txt"
MIN_DOLLAR_VOLUME = 20_000_000  # average daily traded value over 20 days, in USD
STOCK_TRADE_SIZE = 1            # shares per order for universe symbols
MAX_BUYS_PER_RUN = 5            # at most this many new buys per run (most traded first); sells are not capped

# The "crypto" universe: every non-stablecoin USD pair on Alpaca, Alpaca symbol -> yfinance ticker.
# Left out: stablecoins (USDC, USDT, USDG) and BONK, SHIB, PEPE, whose Yahoo prices are rounded to $0.000001,
# which makes their moving averages meaningless.
CRYPTO_UNIVERSE = {
    "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "XRP/USD": "XRP-USD", "SOL/USD": "SOL-USD",
    "HYPE/USD": "HYPE32196-USD", "DOGE/USD": "DOGE-USD", "LINK/USD": "LINK-USD", "ADA/USD": "ADA-USD",
    "BCH/USD": "BCH-USD", "LTC/USD": "LTC-USD", "UNI/USD": "UNI7083-USD", "AVAX/USD": "AVAX-USD",
    "AAVE/USD": "AAVE-USD", "ONDO/USD": "ONDO-USD", "DOT/USD": "DOT-USD", "PAXG/USD": "PAXG-USD",
    "SKY/USD": "SKY33038-USD", "ARB/USD": "ARB11841-USD", "POL/USD": "POL28321-USD", "RENDER/USD": "RENDER-USD",
    "FIL/USD": "FIL-USD", "CRV/USD": "CRV-USD", "TRUMP/USD": "TRUMP35336-USD", "XTZ/USD": "XTZ-USD",
    "LDO/USD": "LDO-USD", "BAT/USD": "BAT-USD", "GRT/USD": "GRT6719-USD", "WIF/USD": "WIF-USD",
    "YFI/USD": "YFI-USD", "SUSHI/USD": "SUSHI-USD",
}
CRYPTO_ORDER_USD = 100       # dollars per crypto buy (coin prices differ too much for a fixed quantity)
MAX_CRYPTO_BUYS_PER_RUN = 3  # at most this many new crypto buys per run; sells are not capped

FAST_MA_PERIOD = 20    # short moving average, in daily bars
SLOW_MA_PERIOD = 50    # long moving average, in daily bars
LOOKBACK_DAYS = 100    # days of history to download from yfinance
