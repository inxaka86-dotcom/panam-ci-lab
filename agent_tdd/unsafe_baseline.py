"""Deliberately invalid baseline used ONLY for an expected-fail TDD control.

Never use this implementation for real access control.
"""


def validate_change_plan(plan: object) -> tuple[str, ...]:
    if not isinstance(plan, dict) or not isinstance(plan.get("changes"), list):
        return ()
    return tuple(sorted(str(item.get("path", "")) for item in plan["changes"]
                        if isinstance(item, dict)))
