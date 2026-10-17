import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from bot import drop_unfinished_bar, load_universe, order_usd, plan_orders, time_in_force  # noqa: E402
from alpaca.trading.enums import TimeInForce  # noqa: E402

NY = ZoneInfo("America/New_York")


def closes(last_day, tz):
    idx = pd.date_range(end=last_day, periods=3, freq="D", tz=tz)
    return pd.Series([1.0, 2.0, 3.0], index=idx)


def test_aapl_market_unchanged():
    m = config.MARKETS["aapl"]
    assert (m.symbol, m.data_symbol, m.asset_class, m.trade_size) == ("AAPL", "AAPL", "stock", 1)


def test_btc_market():
    m = config.MARKETS["btc"]
    assert (m.symbol, m.data_symbol, m.asset_class) == ("BTC/USD", "BTC/USD", "crypto")
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


def stock(symbol):
    return config.Market(symbol, symbol, "stock", 1)


def test_order_size_grows_with_the_gap():
    assert order_usd(0.1) == 100
    assert order_usd(1.5) == 1500
    assert order_usd(-0.5) == 500  # sells use the size of the gap, not its sign
    assert order_usd(0.001) == config.MIN_ORDER_USD


def test_plan_orders_buys_every_signal_sized_by_gap():
    signals = [(stock(s), "buy", gap, 100.0) for s, gap in [("KO", 0.01), ("LIN", 0.2), ("CBRL", 1.6)]]
    orders, _ = plan_orders(signals, {}, set())
    assert [(m.symbol, side, qty, notional) for m, side, qty, notional, _ in orders] == [
        ("KO", "buy", None, 10), ("LIN", "buy", None, 200), ("CBRL", "buy", None, 1600)]


def test_plan_orders_buys_more_of_held_but_skips_symbols_ordered_today():
    signals = [(stock("KO"), "buy", 0.5, 60.0), (stock("LIN"), "buy", 0.5, 500.0)]
    orders, notes = plan_orders(signals, {"KO": 1.0}, {"LIN"})
    assert [m.symbol for m, *_ in orders] == ["KO"]
    assert any("LIN" in n and "today" in n for n in notes)


def test_plan_orders_sells_gap_sized_amount_never_more_than_held():
    signals = [(stock("STX"), "sell", -0.2, 100.0), (stock("GLW"), "sell", -5.0, 100.0), (stock("COHR"), "sell", -1.0, 100.0)]
    orders, notes = plan_orders(signals, {"STX": 10.0, "GLW": 3.0}, set())
    assert [(m.symbol, side, qty) for m, side, qty, *_ in orders] == [("STX", "sell", 2.0), ("GLW", "sell", 3.0)]
    assert any("COHR" in n and "not held" in n for n in notes)


def test_load_universe_ignores_comments_and_maps_class_shares(tmp_path):
    f = tmp_path / "u.txt"
    f.write_text("# header\nAAPL\nBRK.B\n\n")
    markets = load_universe(f)
    assert [(m.symbol, m.data_symbol, m.asset_class) for m in markets] == [("AAPL", "AAPL", "stock"), ("BRK.B", "BRK-B", "stock")]


def test_plan_orders_matches_crypto_positions_without_slash():
    eth = config.Market("ETH/USD", "ETH/USD", "crypto", 0)
    orders, _ = plan_orders([(eth, "sell", -1.0, 2500.0)], {"ETHUSD": 0.0399}, set())
    assert [(m.symbol, side, qty) for m, side, qty, *_ in orders] == [("ETH/USD", "sell", 0.0399)]


def test_crypto_universe_has_no_stablecoins():
    symbols = set(config.CRYPTO_UNIVERSE)
    assert {"BTC/USD", "PEPE/USD", "SHIB/USD", "BONK/USD"} <= symbols
    assert not symbols & {"USDC/USD", "USDT/USD", "USDG/USD"}
    assert all(s.endswith("/USD") for s in symbols)
