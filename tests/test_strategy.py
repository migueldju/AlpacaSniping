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


def test_trend_filter_blocks_buy_below_long_average():
    from strategy import trend_allows_buy
    # long decline then a short bounce: fast crosses slow but price is still under the 200-day average
    prices = pd.Series([200 - i * 0.5 for i in range(250)] + [75 + i * 0.8 for i in range(30)])
    df = add_moving_averages(prices, 20, 50, 200)
    assert df.close.iloc[-1] < df.trend_ma.iloc[-1]
    assert not trend_allows_buy(df)


def test_trend_filter_allows_buy_above_long_average_and_is_off_without_column():
    from strategy import trend_allows_buy
    prices = pd.Series([100 + i * 0.5 for i in range(250)])
    assert trend_allows_buy(add_moving_averages(prices, 20, 50, 200))
    assert trend_allows_buy(add_moving_averages(prices, 20, 50))


def test_trend_filter_blocks_without_enough_history():
    from strategy import trend_allows_buy
    assert not trend_allows_buy(add_moving_averages(pd.Series(range(1, 100)), 20, 50, 200))


def test_stop_loss_hit():
    from strategy import stop_loss_hit
    assert stop_loss_hit(100, 90, 0.10)
    assert not stop_loss_hit(100, 90.01, 0.10)
    assert not stop_loss_hit(100, 50, 0)
