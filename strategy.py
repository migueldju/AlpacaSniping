"""Moving-average crossover signal, independent of any broker or data source."""

from enum import Enum

import pandas as pd


class Signal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


def add_moving_averages(close: pd.Series, fast: int, slow: int) -> pd.DataFrame:
    """Return a frame with close, fast_ma and slow_ma columns (simple moving averages)."""
    if fast >= slow:
        raise ValueError(f"fast period ({fast}) must be shorter than slow period ({slow})")
    df = pd.DataFrame({"close": close.astype(float)})
    df["fast_ma"] = df["close"].rolling(fast).mean()
    df["slow_ma"] = df["close"].rolling(slow).mean()
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
