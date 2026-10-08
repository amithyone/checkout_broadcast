"""Show only tills in range of the phone (spec/ble-transport.md#proximity-filtering-optional-recommended).

Smooths RSSI per till and splits tills into *visible* (in range) and *hidden* (farther). It never
picks a till for the customer: the customer always taps one and confirms with PIN.

Android `TillProximity.kt`, iOS `TillProximity.swift` and the CheckoutNow app implement the same
rules; tests/fixtures/proximity_vectors.json keeps them in step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProximityConfig:
    alpha: float = 0.3
    in_range_dbm: float = -75.0
    window_db: float = 12.0
    hysteresis_db: float = 5.0
    hysteresis_ms: int = 3_000
    stale_ms: int = 10_000
    min_peek_dbm: float = -90.0


@dataclass
class TillSignal:
    device_id: str
    smoothed_rssi: float
    last_heard_ms: int
    terminal_id: Optional[str] = None
    shown: bool = False
    below_since_ms: Optional[int] = field(default=None, repr=False)

    @property
    def key(self) -> str:
        return self.terminal_id or self.device_id


@dataclass
class ProximityView:
    visible: list[TillSignal]
    hidden: list[TillSignal]


class TillProximityFilter:
    def __init__(self, config: Optional[ProximityConfig] = None) -> None:
        self.config = config or ProximityConfig()
        self._tills: dict[str, TillSignal] = {}

    def update_signal(
        self,
        device_id: str,
        rssi: int,
        now_ms: int,
        terminal_id: Optional[str] = None,
    ) -> Optional[float]:
        """Record one advert. Returns the smoothed RSSI, or None when `rssi` is unknown (>= 0)."""
        till = self._tills.get(device_id)
        if terminal_id and till:
            till.terminal_id = terminal_id
        if rssi >= 0:
            return till.smoothed_rssi if till else None
        if till is None:
            till = TillSignal(device_id=device_id, smoothed_rssi=float(rssi), last_heard_ms=now_ms,
                              terminal_id=terminal_id)
            self._tills[device_id] = till
        else:
            a = self.config.alpha
            till.smoothed_rssi = a * rssi + (1.0 - a) * till.smoothed_rssi
            till.last_heard_ms = now_ms
        return till.smoothed_rssi

    def set_terminal(self, device_id: str, terminal_id: str) -> None:
        till = self._tills.get(device_id)
        if till:
            till.terminal_id = terminal_id

    def should_peek(self, device_id: str) -> bool:
        """False when the till is clearly too far to be worth a GATT connection."""
        till = self._tills.get(device_id)
        return till is None or till.smoothed_rssi >= self.config.min_peek_dbm

    def evaluate(self, now_ms: int, preferred: Optional[str] = None) -> ProximityView:
        cfg = self.config
        for device_id in [d for d, t in self._tills.items() if now_ms - t.last_heard_ms > cfg.stale_ms]:
            del self._tills[device_id]
        if not self._tills:
            return ProximityView(visible=[], hidden=[])

        strongest = max(t.smoothed_rssi for t in self._tills.values())
        for till in self._tills.values():
            s = till.smoothed_rssi
            if s >= cfg.in_range_dbm and s >= strongest - cfg.window_db:
                till.shown = True
                till.below_since_ms = None
            elif till.shown:
                well_below = (
                    s < cfg.in_range_dbm - cfg.hysteresis_db
                    or s < strongest - cfg.window_db - cfg.hysteresis_db
                )
                if not well_below:
                    till.below_since_ms = None
                elif till.below_since_ms is None:
                    till.below_since_ms = now_ms
                elif now_ms - till.below_since_ms >= cfg.hysteresis_ms:
                    till.shown = False
                    till.below_since_ms = None

        pref = (preferred or "").strip().upper()

        def is_preferred(t: TillSignal) -> bool:
            return bool(pref) and pref in {(t.terminal_id or "").upper(), t.device_id.upper()}

        def sort_key(t: TillSignal):
            return (0 if is_preferred(t) else 1, -t.smoothed_rssi, t.key)

        visible = sorted((t for t in self._tills.values() if t.shown or is_preferred(t)), key=sort_key)
        visible_ids = {t.device_id for t in visible}
        hidden = sorted((t for t in self._tills.values() if t.device_id not in visible_ids), key=sort_key)
        return ProximityView(visible=visible, hidden=hidden)

    def visible_tills(self, now_ms: int, preferred: Optional[str] = None) -> list[TillSignal]:
        return self.evaluate(now_ms, preferred).visible

    def hidden_tills(self, now_ms: int, preferred: Optional[str] = None) -> list[TillSignal]:
        return self.evaluate(now_ms, preferred).hidden

    def clear(self) -> None:
        self._tills.clear()


def estimate_distance_m(rssi: float, tx_power_dbm: float = -59.0, path_loss_n: float = 2.5) -> float:
    """Log-distance path loss. For logs only — too noisy on phones to decide anything."""
    return math.pow(10.0, (tx_power_dbm - rssi) / (10.0 * path_loss_n))
