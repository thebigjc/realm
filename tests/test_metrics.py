from typing import Any, cast

from realm_bot.metrics import update_realm_gauges, realm_up


def test_update_realm_gauges_basic() -> None:
    status: dict[str, bool] = {"a": True, "b": False}
    update_realm_gauges(status)
    # Access internal samples to assert values
    # Each gauge has a sample with labels
    metrics_list: list[Any] = list(realm_up.collect())
    # Treat elements as Any to keep tests robust despite missing type stubs
    first_metric: Any = metrics_list[0]
    samples: list[Any] = cast(list[Any], first_metric.samples)
    found: dict[str, float] = {
        str(s.labels["realm"]): float(s.value)
        for s in samples
        if getattr(s, "name", "") == "realm_up"
    }
    assert found.get("a") == 1.0
    assert found.get("b") == 0.0
