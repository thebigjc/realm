from realm_bot.realm_tracker import compute_counts, diff_snapshots, make_snapshot


def test_compute_counts_basic():
    # Two connected realms: one UP with 2 member realms, one DOWN with 1
    data = [
        {"status": {"type": "UP"}, "realms": [{"slug": "a"}, {"slug": "b"}]},
        {"status": {"type": "DOWN"}, "realms": [{"slug": "c"}]},
    ]
    available, status_counts, total = compute_counts(data)
    assert available == 2
    assert status_counts["UP"] == 2
    assert status_counts["DOWN"] == 1
    assert total == 3


def test_diff_first_run_no_post():
    curr = make_snapshot(5, {"UP": 5}, 5)
    d = diff_snapshots(None, curr)
    assert d.should_post is False


def test_diff_change_triggers_post():
    prev = make_snapshot(5, {"UP": 5}, 5)
    curr = make_snapshot(6, {"UP": 6}, 6)
    d = diff_snapshots(prev, curr)
    assert d.should_post is True
