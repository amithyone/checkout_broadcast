import json
from pathlib import Path

import pytest

from checkout_broadcast.proximity import (
    ProximityConfig,
    TillProximityFilter,
    estimate_distance_m,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "proximity_vectors.json").read_text())


def _filter() -> TillProximityFilter:
    c = FIXTURE["config"]
    return TillProximityFilter(ProximityConfig(
        alpha=c["alpha"],
        in_range_dbm=c["in_range_dbm"],
        window_db=c["window_db"],
        hysteresis_db=c["hysteresis_db"],
        hysteresis_ms=c["hysteresis_ms"],
        stale_ms=c["stale_ms"],
        min_peek_dbm=c["min_peek_dbm"],
    ))


def test_defaults_match_fixture_config():
    c = FIXTURE["config"]
    d = ProximityConfig()
    assert (d.alpha, d.in_range_dbm, d.window_db, d.hysteresis_db, d.hysteresis_ms, d.stale_ms, d.min_peek_dbm) == (
        c["alpha"], c["in_range_dbm"], c["window_db"], c["hysteresis_db"], c["hysteresis_ms"], c["stale_ms"],
        c["min_peek_dbm"],
    )


@pytest.mark.parametrize("vector", FIXTURE["vectors"], ids=lambda v: v["name"])
def test_proximity_vector(vector):
    f = _filter()
    for step in vector["steps"]:
        t = step["t"]
        if "signal" in step:
            s = step["signal"]
            f.update_signal(s["device"], s["rssi"], t, terminal_id=s.get("terminal_id"))
            continue
        check = step["check"]
        view = f.evaluate(t, preferred=check.get("preferred"))
        assert [x.device_id for x in view.visible] == check["visible"], f"t={t} visible"
        assert [x.device_id for x in view.hidden] == check["hidden"], f"t={t} hidden"
        by_id = {x.device_id: x for x in view.visible + view.hidden}
        for device, expected in check.get("smoothed", {}).items():
            assert by_id[device].smoothed_rssi == pytest.approx(expected, abs=0.01)
        for device, expected in check.get("peek", {}).items():
            assert f.should_peek(device) is expected


def test_distance_is_monotonic_and_calibrated():
    assert estimate_distance_m(-59) == pytest.approx(1.0)
    assert estimate_distance_m(-70) > estimate_distance_m(-60)
