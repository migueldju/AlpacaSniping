import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from risk import Position, cap_buys, stop_loss_exits  # noqa: E402


def stock(symbol):
    return config.Market(symbol, symbol, "stock")


def test_stop_loss_exits_only_this_asset_class_below_the_stop():
    held = [Position("MU", 1, 100, 89, "stock"), Position("KO", 1, 100, 95, "stock"),
            Position("BTCUSD", 0.01, 100, 50, "crypto")]
    assert [p.symbol for p in stop_loss_exits(held, "stock", 0.10)] == ["MU"]
    assert [p.symbol for p in stop_loss_exits(held, "crypto", 0.10)] == ["BTCUSD"]


def test_cap_buys_per_position_limit_counts_what_is_already_held():
    kept, notes = cap_buys([(stock("NVR"), 6000), (stock("KO"), 60)], equity=100_000,
                           held_value={"KO": 4950}, invested=4950, max_position_pct=0.05, max_invested_pct=0.5)
    assert kept == []
    assert any("NVR" in n and "5%" in n for n in notes) and any("KO" in n for n in notes)


def test_cap_buys_total_limit_keeps_priority_order():
    buys = [(stock("A"), 4000), (stock("B"), 4000), (stock("C"), 100)]
    kept, notes = cap_buys(buys, equity=100_000, held_value={},
                           invested=44_000, max_position_pct=0.05, max_invested_pct=0.5)
    assert [m.symbol for m, _ in kept] == ["A", "C"]
    assert any("B" in n and "total" in n for n in notes)


def test_cap_buys_matches_crypto_positions_without_slash():
    btc = config.Market("BTC/USD", "BTC-USD", "crypto")
    kept, _ = cap_buys([(btc, 100)], equity=100_000, held_value={"BTCUSD": 4950},
                       invested=0, max_position_pct=0.05, max_invested_pct=0.5)
    assert kept == []
