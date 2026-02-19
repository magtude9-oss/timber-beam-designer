"""Utility functions for timber beam designer."""


def format_util(util: float) -> str:
    """Format utilisation as percentage string with pass/fail indicator."""
    status = "OK" if util <= 100.0 else "FAIL"
    return f"{util:.0f}% [{status}]"


def print_results_table(results: list) -> None:
    """Print design check results as a formatted table."""
    print(f"\n{'Check':<12} {'Demand':>10} {'Capacity':>10} {'Util':>8} {'Status':>6}")
    print("-" * 50)
    for r in results:
        status = "OK" if r.passed else "FAIL"
        print(
            f"{r.name:<12} "
            f"{r.demand:>8.2f} {r.unit:<2} "
            f"{r.capacity:>8.2f} {r.unit:<2} "
            f"{r.utilisation:>6.0f}% "
            f"{status:>6}"
        )
    print()
