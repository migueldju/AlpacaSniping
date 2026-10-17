"""Bot settings. Edit these values to change what the bot trades."""

SYMBOL = "AAPL"        # stock to trade
FAST_MA_PERIOD = 20    # short moving average, in trading days
SLOW_MA_PERIOD = 50    # long moving average, in trading days
TRADE_SIZE = 1         # shares per order
LOOKBACK_DAYS = 100    # trading days of history to download from yfinance
