from typing import Any, Dict, List

from realm_bot.models import parse_connected_realms


def test_parse_connected_realms_basic() -> None:
    data: List[Dict[str, Any]] = [
        {
            "status": {"type": "UP"},
            "realms": [
                {
                    "slug": "area-52",
                    "name": {"en_US": "Area 52"},
                    "category": {"type": "RETAIL", "name": {"en_US": "Live"}},
                },
                {
                    "slug": "illidan",
                    "name": {"en_US": "Illidan"},
                    "category": {"type": "PTR", "name": {"en_US": "Public Test Realm"}},
                },
            ],
        },
        {
            "status": {"type": "DOWN"},
            "realms": [
                {"name": {"en_US": "Some RP Realm"}, "category": {"type": "BETA", "name": "Beta"}},
            ],
        },
    ]

    models = parse_connected_realms(data)
    assert len(models) == 2
    assert models[0].is_up() is True
    assert models[1].is_up() is False
    labels0 = models[0].realm_labels()
    labels1 = models[1].realm_labels()
    assert "area-52" in labels0 and "illidan" in labels0
    assert "Some RP Realm" in labels1
    assert models[0].realms[0].category_type() == "RETAIL"
    assert models[0].realms[1].category_type() == "PTR"
    assert models[1].realms[0].category_type() == "BETA"


def test_parse_connected_realms_string_names() -> None:
    # Simulate API returning plain strings for names
    data: List[Dict[str, Any]] = [
        {
            "status": {"type": "UP"},
            "realms": [
                {"slug": "azjol-nerub", "name": "Azjol-Nerub"},
                {"slug": "muradin", "name": "Muradin"},
            ],
        },
        {
            "status": {"type": "DOWN"},
            "realms": [
                {"name": "Random Realm"},
            ],
        },
    ]
    models = parse_connected_realms(data)  # type: ignore[arg-type]
    assert len(models) == 2
    first = models[0]
    second = models[1]
    assert first.is_up() is True
    labels_first = first.realm_labels()
    assert "azjol-nerub" in labels_first  # slug wins
    assert "muradin" in labels_first
    assert second.is_up() is False
    assert "Random Realm" in second.realm_labels()

def test_parse_connected_realms_category_defaults() -> None:
    data: List[Dict[str, Any]] = [
        {
            "status": {"type": "UP"},
            "realms": [
                {
                    "slug": "beta-test",
                    "name": "Beta Test",
                    "category": {"type": "beta", "name": {"en_US": "Beta"}},
                },
                {
                    "slug": "unknown",
                    "name": "Unknown",
                    "category": "United States",
                },
            ],
        }
    ]

    models = parse_connected_realms(data)  # type: ignore[arg-type]
    assert len(models) == 1
    summary_with_category = models[0].realms[0]
    summary_without_category = models[0].realms[1]
    assert summary_with_category.category_type() == "BETA"
    assert summary_without_category.category_type() is None
    assert summary_without_category.category_label() == "United States"
