import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from bot import drop_unfinished_bar, time_in_force  # noqa: E402
from alpaca.trading.enums import TimeInForce  # noqa: E402

NY = ZoneInfo("America/New_York")


def closes(last_day, tz):
    idx = pd.date_range(end=last_day, periods=3, freq="D", tz=tz)
    return pd.Series([1.0, 2.0, 3.0], index=idx)


def test_aapl_market_unchanged():
    m = config.MARKETS[config.DEFAULT_MARKET]
    assert (m.symbol, m.data_symbol, m.asset_class, m.trade_size) == ("AAPL", "AAPL", "stock", 1)


def test_btc_market():
    m = config.MARKETS["btc"]
    assert (m.symbol, m.data_symbol, m.asset_class) == ("BTC/USD", "BTC-USD", "crypto")
    assert 0 < m.trade_size < 1


def test_time_in_force():
    assert time_in_force("stock") is TimeInForce.DAY
    assert time_in_force("crypto") is TimeInForce.GTC


def test_stock_drops_today_before_close():
    s = closes("2026-10-16", NY)
    assert len(drop_unfinished_bar(s, "stock", datetime(2026, 10, 16, 9, 30, tzinfo=NY))) == 2


def test_stock_keeps_today_after_close():
    s = closes("2026-10-16", NY)
    assert len(drop_unfinished_bar(s, "stock", datetime(2026, 10, 16, 16, 30, tzinfo=NY))) == 3


def test_crypto_drops_current_utc_day_even_in_evening():
    # 21:00 ET on Oct 16 is already Oct 17 in UTC; the Oct 17 bar is unfinished.
    s = closes("2026-10-17", timezone.utc)
    assert len(drop_unfinished_bar(s, "crypto", datetime(2026, 10, 16, 21, 0, tzinfo=NY))) == 2


def test_crypto_keeps_yesterdays_bar():
    s = closes("2026-10-16", timezone.utc)
    assert len(drop_unfinished_bar(s, "crypto", datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc))) == 3
