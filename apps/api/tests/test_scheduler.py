from app.services.scheduler import build_demo_experiments, schedule_policy_comparison


def test_demo_experiments_seeded() -> None:
    experiments = build_demo_experiments()
    assert len(experiments) >= 5
    assert all('id' in exp for exp in experiments)


def test_policy_comparison_is_deterministic() -> None:
    first = schedule_policy_comparison()
    second = schedule_policy_comparison()
    assert first == second
