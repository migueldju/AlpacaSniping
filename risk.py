"""Account-level risk limits, independent of any broker: stop-loss exits and caps on buy size."""

from dataclasses import dataclass

from strategy import stop_loss_hit


@dataclass(frozen=True)
class Position:
    symbol: str          # as the broker reports it (crypto without the slash, e.g. BTCUSD)
    qty: float
    avg_entry_price: float
    current_price: float
    asset_class: str     # "stock" or "crypto"

    @property
    def market_value(self) -> float:
        return self.qty * self.current_price

    @property
    def change_pct(self) -> float:
        return (self.current_price / self.avg_entry_price - 1) * 100 if self.avg_entry_price else 0.0


def stop_loss_exits(positions: list[Position], asset_class: str, stop_pct: float) -> list[Position]:
    """Long positions of this asset class that are stop_pct or more below their average entry price."""
    return [p for p in positions if p.asset_class == asset_class and p.qty > 0
            and stop_loss_hit(p.avg_entry_price, p.current_price, stop_pct)]


def cap_buys(buys: list, prices: dict, equity: float, held_value: dict, invested: float,
             max_position_pct: float, max_invested_pct: float):
    """Drop buys that would break a limit. Returns (kept, notes).

    buys: (market, qty) in priority order. prices: symbol -> price. held_value: position key -> dollars held.
    A buy is skipped if it would bring its position above max_position_pct of equity, or the total invested
    (positions plus the buys kept so far) above max_invested_pct of equity.
    """
    kept, notes = [], []
    position_cap, total_cap = equity * max_position_pct, equity * max_invested_pct
    for market, qty in buys:
        value = qty * prices[market.symbol]
        held = held_value.get(market.symbol.replace("/", ""), 0.0)
        if held + value > position_cap:
            notes.append(f"{market.symbol} BUY skipped: ${value:,.0f} would exceed the "
                         f"{max_position_pct:.0%} per-position limit (${position_cap:,.0f})")
        elif invested + value > total_cap:
            notes.append(f"{market.symbol} BUY skipped: total invested would exceed "
                         f"{max_invested_pct:.0%} of equity (${total_cap:,.0f})")
        else:
            kept.append((market, qty))
            invested += value
    return kept, notes
