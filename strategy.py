"""Moving-average crossover signal, independent of any broker or data source."""

from enum import Enum

import pandas as pd


class Signal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


def add_moving_averages(close: pd.Series, fast: int, slow: int, trend: int = 0) -> pd.DataFrame:
    """Return a frame with close, fast_ma and slow_ma columns (simple moving averages).

    With trend > 0 it also adds trend_ma, the long-term average used by trend_allows_buy.
    """
    if fast >= slow:
        raise ValueError(f"fast period ({fast}) must be shorter than slow period ({slow})")
    df = pd.DataFrame({"close": close.astype(float)})
    df["fast_ma"] = df["close"].rolling(fast).mean()
    df["slow_ma"] = df["close"].rolling(slow).mean()
    if trend:
        df["trend_ma"] = df["close"].rolling(trend).mean()
    return df


def crossover_signal(df: pd.DataFrame) -> Signal:
    """Compare the last two days: a real crossover means the fast MA changed side of the slow MA.

    BUY  if fast <= slow yesterday and fast > slow today (crossed above).
    SELL if fast >= slow yesterday and fast < slow today (crossed below).
    """
    valid = df.dropna(subset=["fast_ma", "slow_ma"])
    if len(valid) < 2:
        raise ValueError("not enough data: need at least two days with both moving averages")
    prev, curr = valid.iloc[-2], valid.iloc[-1]
    if prev.fast_ma <= prev.slow_ma and curr.fast_ma > curr.slow_ma:
        return Signal.BUY
    if prev.fast_ma >= prev.slow_ma and curr.fast_ma < curr.slow_ma:
        return Signal.SELL
    return Signal.HOLD


def trend_allows_buy(df: pd.DataFrame) -> bool:
    """Trend filter: buy only while the last close is above the long-term average (trend_ma).

    Without a trend_ma column the filter is off. Without enough history for it, it blocks the buy.
    """
    if "trend_ma" not in df:
        return True
    last = df.iloc[-1]
    return bool(pd.notna(last.trend_ma) and last.close > last.trend_ma)


def stop_loss_hit(entry_price: float, price: float, stop_pct: float) -> bool:
    """True once price has fallen stop_pct (e.g. 0.08 = 8%) or more below the entry price."""
    return stop_pct > 0 and entry_price > 0 and price <= entry_price * (1 - stop_pct)
