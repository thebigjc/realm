from realm_bot.models import parse_connected_realms


def test_parse_connected_realms_basic() -> None:
    data = [
        {
            "status": {"type": "UP"},
            "realms": [
                {"slug": "area-52", "name": {"en_US": "Area 52"}},
                {"slug": "illidan", "name": {"en_US": "Illidan"}},
            ],
        },
        {
            "status": {"type": "DOWN"},
            "realms": [
                {"name": {"en_US": "Some RP Realm"}},
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


def test_parse_connected_realms_string_names() -> None:
    # Simulate API returning plain strings for names
    data = [
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
