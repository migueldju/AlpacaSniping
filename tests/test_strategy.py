import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from strategy import Signal, add_moving_averages, crossover_signal  # noqa: E402


def frame(fast_prev, slow_prev, fast_now, slow_now):
    return pd.DataFrame({"fast_ma": [fast_prev, fast_now], "slow_ma": [slow_prev, slow_now]})


def test_cross_above_is_buy():
    assert crossover_signal(frame(9, 10, 11, 10)) is Signal.BUY


def test_cross_below_is_sell():
    assert crossover_signal(frame(11, 10, 9, 10)) is Signal.SELL


def test_touch_then_cross_counts():
    assert crossover_signal(frame(10, 10, 11, 10)) is Signal.BUY


def test_staying_above_is_hold():
    assert crossover_signal(frame(12, 10, 13, 10)) is Signal.HOLD


def test_staying_below_is_hold():
    assert crossover_signal(frame(8, 10, 7, 10)) is Signal.HOLD


def test_only_uses_last_two_days():
    df = pd.DataFrame({"fast_ma": [9, 11, 12, 13], "slow_ma": [10, 10, 10, 10]})
    assert crossover_signal(df) is Signal.HOLD


def test_price_series_downtrend_then_rally_buys():
    # 60 days falling, then a sharp rally; find the first day the 20MA crosses the 50MA.
    prices = pd.Series([100 - i * 0.5 for i in range(60)] + [70 + i * 3 for i in range(40)])
    df = add_moving_averages(prices, 20, 50)
    signals = [crossover_signal(df.iloc[: i + 1]) for i in range(50, len(df))]
    assert Signal.BUY in signals
    assert Signal.SELL not in signals
    assert sum(s is Signal.BUY for s in signals) == 1


def test_not_enough_data_raises():
    df = add_moving_averages(pd.Series(range(40)), 20, 50)
    with pytest.raises(ValueError):
        crossover_signal(df)


def test_fast_must_be_shorter():
    with pytest.raises(ValueError):
        add_moving_averages(pd.Series(range(100)), 50, 20)
