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
    # Default threshold is 1, so delta of 1 should trigger
    d = diff_snapshots(prev, curr, min_change_threshold=1)
    assert d.should_post is True


def test_diff_small_change_filtered_by_threshold():
    # Simulate a minor flap: 246 -> 244 (delta of 2)
    prev = make_snapshot(246, {"UP": 246}, 246)
    curr = make_snapshot(244, {"UP": 244}, 244)
    # With threshold of 10, delta of 2 should NOT trigger
    d = diff_snapshots(prev, curr, min_change_threshold=10)
    assert d.should_post is False


def test_diff_large_change_passes_threshold():
    # Simulate maintenance: 246 -> 82 (delta of 164)
    prev = make_snapshot(246, {"UP": 246}, 246)
    curr = make_snapshot(82, {"UP": 82, "DOWN": 164}, 246)
    # With threshold of 10, delta of 164 should trigger
    d = diff_snapshots(prev, curr, min_change_threshold=10)
    assert d.should_post is True


def test_diff_recovery_passes_threshold():
    # Simulate recovery: 0 -> 246 (delta of 246)
    prev = make_snapshot(0, {"DOWN": 246}, 246)
    curr = make_snapshot(246, {"UP": 246}, 246)
    d = diff_snapshots(prev, curr, min_change_threshold=10)
    assert d.should_post is True
