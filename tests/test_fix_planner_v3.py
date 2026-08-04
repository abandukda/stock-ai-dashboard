from agents.fix_planner_v3 import create_fix_plan


def test_fix_plan_requires_human_approval():
    plan = create_fix_plan([
        {
            "severity": "HIGH",
            "category": "Missing Data",
            "likely_files": ["ui/example.py"],
        }
    ])
    assert plan["direct_production_writes"] is False
    assert plan["human_approval_required"] is True
