import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from bot import drop_unfinished_bar, load_universe, plan_orders, time_in_force  # noqa: E402
from strategy import Signal, add_moving_averages, crossover_signal  # noqa: E402
from alpaca.trading.enums import TimeInForce  # noqa: E402

NY = ZoneInfo("America/New_York")


def closes(last_day, tz):
    idx = pd.date_range(end=last_day, periods=3, freq="D", tz=tz)
    return pd.Series([1.0, 2.0, 3.0], index=idx)


def test_aapl_market_unchanged():
    m = config.MARKETS["aapl"]
    assert (m.symbol, m.data_symbol, m.asset_class) == ("AAPL", "AAPL", "stock")


def test_btc_market():
    m = config.MARKETS["btc"]
    assert (m.symbol, m.data_symbol, m.asset_class) == ("BTC/USD", "BTC-USD", "crypto")


def test_time_in_force():
    assert time_in_force("stock") is TimeInForce.DAY
    assert time_in_force("crypto") is TimeInForce.GTC


def test_stock_drops_today_before_close():
    s = closes("2026-10-16", NY)
    assert len(drop_unfinished_bar(s, "stock", datetime(2026, 10, 16, 9, 30, tzinfo=NY))) == 2


def test_stock_keeps_today_after_close():
    s = closes("2026-10-16", NY)
    assert len(drop_unfinished_bar(s, "stock", datetime(2026, 10, 16, 16, 30, tzinfo=NY))) == 3


def test_stock_keeps_today_at_the_1550_run():
    # the scheduled run is at 15:50 ET: today's bar is minutes from final and counts as the close
    s = closes("2026-10-16", NY)
    assert len(drop_unfinished_bar(s, "stock", datetime(2026, 10, 16, 15, 50, tzinfo=NY))) == 3


def test_crypto_drops_current_utc_day_even_in_evening():
    # 21:00 ET on Oct 16 is already Oct 17 in UTC; the Oct 17 bar is unfinished.
    s = closes("2026-10-17", timezone.utc)
    assert len(drop_unfinished_bar(s, "crypto", datetime(2026, 10, 16, 21, 0, tzinfo=NY))) == 2


def test_crypto_keeps_yesterdays_bar():
    s = closes("2026-10-16", timezone.utc)
    assert len(drop_unfinished_bar(s, "crypto", datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc))) == 3


def stock(symbol):
    return config.Market(symbol, symbol, "stock")


def test_plan_orders_caps_buys_in_order():
    buys = [stock(s) for s in ["KO", "LIN", "SAP", "AIG"]]
    orders, notes = plan_orders(buys, [], {}, set(), max_buys=2)
    assert [(m.symbol, side) for m, side, _ in orders] == [("KO", "buy"), ("LIN", "buy")]
    assert any("SAP" in n and "limit" in n for n in notes)


def test_plan_orders_skips_held_and_open_without_using_the_cap():
    buys = [stock(s) for s in ["KO", "LIN", "SAP"]]
    orders, _ = plan_orders(buys, [], {"KO": 1.0}, {"LIN"}, max_buys=1)
    assert [m.symbol for m, _, _ in orders] == ["SAP"]


def test_plan_orders_sells_only_held_and_never_more_than_held():
    sells = [stock("STX"), stock("GLW")]
    orders, notes = plan_orders([], sells, {"STX": 0.5}, set(), max_buys=0)
    assert [(m.symbol, side, qty) for m, side, qty in orders] == [("STX", "sell", 0.5)]
    assert any("GLW" in n and "not held" in n for n in notes)


def test_load_universe_ignores_comments_and_maps_class_shares(tmp_path):
    f = tmp_path / "u.txt"
    f.write_text("# header\nAAPL\nBRK.B\n\n")
    markets = load_universe(f)
    assert [(m.symbol, m.data_symbol, m.asset_class) for m in markets] == [("AAPL", "AAPL", "stock"), ("BRK.B", "BRK-B", "stock")]


def test_buy_usd_is_5pct_of_equity_rounded_down_and_skips_tiny_accounts():
    from bot import buy_usd
    assert buy_usd(1000) == 50
    assert buy_usd(1234.56) == 61.72
    assert buy_usd(10) is None


def test_plan_orders_matches_crypto_positions_without_slash():
    btc, eth = config.Market("BTC/USD", "BTC-USD", "crypto"), config.Market("ETH/USD", "ETH-USD", "crypto")
    orders, notes = plan_orders([btc], [eth], {"BTCUSD": 0.001, "ETHUSD": 0.0399}, set(), max_buys=3)
    assert [(m.symbol, side, qty) for m, side, qty in orders] == [("ETH/USD", "sell", 0.0399)]
    assert any("BTC/USD" in n and "already held" in n for n in notes)


def test_crypto_universe_has_no_stablecoins_or_rounded_coins():
    symbols = set(config.CRYPTO_UNIVERSE)
    assert "BTC/USD" in symbols
    assert not symbols & {"USDC/USD", "USDT/USD", "USDG/USD", "BONK/USD", "SHIB/USD", "PEPE/USD"}
    assert all(s.endswith("/USD") for s in symbols)


class FakeClient:
    """Stands in for alpaca's TradingClient in run_universe: records orders instead of sending them."""

    def __init__(self, equity, positions):
        from types import SimpleNamespace as NS
        self.account = NS(equity=str(equity))
        self.positions = [NS(symbol=s, qty=str(q), avg_entry_price=str(e), current_price=str(c),
                             asset_class=NS(value="us_equity")) for s, q, e, c in positions]
        self.orders = []

    def get_account(self):
        return self.account

    def get_all_positions(self):
        return self.positions

    def get_orders(self, request):
        return []

    def submit_order(self, req):
        from types import SimpleNamespace as NS
        self.orders.append((req.symbol, req.side.value, req.qty, req.notional))
        return NS(id="x", status=NS(value="accepted"))


def bars(prices):
    idx = pd.date_range(end="2026-10-15", periods=len(prices), freq="B", tz=NY)
    return pd.DataFrame({"Close": prices}, index=idx)


def up_to_first_buy(prices):
    """The series cut on the first day the 20-day average crosses above the 50-day one."""
    df = add_moving_averages(pd.Series(prices), 20, 50)
    day = next(i for i in range(51, len(df)) if crossover_signal(df.iloc[: i + 1]) is Signal.BUY)
    return prices[: day + 1]


def test_run_universe_applies_trend_filter_stop_loss_and_position_limit(monkeypatch):
    import bot
    uptrend_cross = up_to_first_buy([100 + i * 0.2 for i in range(260)] + [152 - i for i in range(25)]
                                    + [127 + i * 3 for i in range(30)])
    downtrend_cross = up_to_first_buy([300 - i * 0.6 for i in range(270)] + [138 + i * 0.6 for i in range(40)])
    data = {"UP": bars(uptrend_cross), "DOWN": bars(downtrend_cross), "PRICY": bars([p * 100 for p in uptrend_cross]),
            "MU": bars([100.0] * 300)}
    monkeypatch.setattr(bot, "fetch_history_batch", lambda tickers, days: data)
    monkeypatch.setattr(bot.config, "MAX_INVESTED_PCT", 0.50)
    # MU is 15% under its entry (stop-loss); BIG brings the account to 44% invested
    client = FakeClient(100_000, [("MU", 2, 100, 85), ("BIG", 1, 44_000, 44_000)])
    monkeypatch.setattr(bot, "trading_client", lambda: client)

    result = bot.run_universe([stock(s) for s in ["UP", "DOWN", "PRICY", "MU"]], dry_run=False, max_buys=5)
    # DOWN crossed up below its 200-day average (trend filter). Each buy is 5% of equity ($5,000): UP takes the
    # account to 49% invested, so PRICY would pass the 50% limit.
    assert client.orders == [("MU", "sell", 2.0, None), ("UP", "buy", None, 5000.0)]
    assert "1 BUY blocked by trend filter" in result
