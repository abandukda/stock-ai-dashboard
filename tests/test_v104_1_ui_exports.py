from ui.research_report_v104 import (
    inject_v104_polish_css,
    render_candidate_card,
    render_full_research_report,
)
from ui.home_v104 import render_v104_home
from ui.market_briefing_v104 import render_v104_earnings_briefing


def test_v104_1_public_exports_exist():
    assert callable(inject_v104_polish_css)
    assert callable(render_candidate_card)
    assert callable(render_full_research_report)
    assert callable(render_v104_home)
    assert callable(render_v104_earnings_briefing)
