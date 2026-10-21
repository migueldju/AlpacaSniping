"""Bot settings. Edit these values to change what the bot trades."""

from dataclasses import dataclass
from datetime import time
from pathlib import Path


@dataclass(frozen=True)
class Market:
    symbol: str        # Alpaca symbol (crypto uses a slash, e.g. BTC/USD)
    data_symbol: str   # yfinance ticker for the same asset (e.g. BTC-USD)
    asset_class: str   # "stock" or "crypto"


# Pick one with `python bot.py --market btc` or the BOT_MARKET environment variable.
# `--market stocks` runs every symbol in UNIVERSE_FILE and `--market crypto` every coin in CRYPTO_UNIVERSE.
MARKETS = {
    "aapl": Market(symbol="AAPL", data_symbol="AAPL", asset_class="stock"),
    "btc": Market(symbol="BTC/USD", data_symbol="BTC-USD", asset_class="crypto"),
}
DEFAULT_MARKET = "stocks"

# The "stocks" universe: every liquid US stock/ETF on Alpaca, one symbol per line, most traded first.
# Rebuild it with `python build_universe.py` (it applies MIN_DOLLAR_VOLUME).
UNIVERSE_FILE = Path(__file__).resolve().parent / "universe_stocks.txt"
MIN_DOLLAR_VOLUME = 20_000_000  # average daily traded value over 20 days, in USD
MAX_BUYS_PER_RUN = None         # at most this many new buys per run (most traded first), None = no cap; sells are not capped

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
MAX_CRYPTO_BUYS_PER_RUN = 3  # at most this many new crypto buys per run; sells are not capped

FAST_MA_PERIOD = 20    # short moving average, in daily bars
SLOW_MA_PERIOD = 50    # long moving average, in daily bars
TREND_MA_PERIOD = 200  # trend filter: buy only if the close is above this moving average (0 turns it off)
LOOKBACK_DAYS = 400    # calendar days of history to download from yfinance (enough for TREND_MA_PERIOD bars)

# Order size: every buy is a dollar amount (fractional shares or coins), BUY_PCT_OF_EQUITY of account equity,
# rounded down to the cent and at least MIN_ORDER_USD. Sells always sell the whole position.
BUY_PCT_OF_EQUITY = 0.025  # 2.5% of equity per buy: $25 on a $1,000 account (variant "PR5 2.5%")
MIN_ORDER_USD = 1         # Alpaca's smallest fractional order

# Risk limits, checked on every live universe run (stocks and crypto alike).
MAX_POSITION_PCT = 0.05  # one buy may not bring a position above 5% of account equity
MAX_INVESTED_PCT = 1.00  # all positions together (plus today's buys) may not exceed 100% of equity: no margin
STOP_LOSS_PCT = 0.10     # sell a whole position once it is 10% below its average entry price (8% tested worse)

# Stocks: the bot runs at 15:50 ET, so from STOCK_BAR_CUTOFF on it treats today's bar as the day's close
# (the price is a few minutes from final) and can act on the crossover day itself. Earlier, today's bar is dropped.
STOCK_BAR_CUTOFF = time(15, 30)
