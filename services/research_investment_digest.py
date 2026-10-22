"""Read-only explanation of the existing customer projection; no model/provider calls."""
from collections.abc import Mapping
from typing import Any
import math


def build_investment_digest(page: Mapping[str, Any]) -> dict[str, Any]:
    if page.get('status') != 'AVAILABLE':
        return {'status': 'UNAVAILABLE', 'mode': 'DETERMINISTIC_GROUNDED_FALLBACK',
                'external_model_active': False, 'answers': (), 'executive_digest': ()}
    reading = page.get('reading_views') or {}
    simple = reading.get('simple_view') or {}
    questions = tuple(simple.get('questions') or ())
    def answer(index, fallback):
        return str(questions[index].get('answer') or fallback) if len(questions)>index else fallback
    news = (page.get('recent_changes') or {}).get('items') or ()
    dated = sorted((n for n in news if n.get('article_timestamp') and n.get('article_publisher') and n.get('headline')),
                   key=lambda n: str(n['article_timestamp']), reverse=True)[:2]
    changes = tuple({'text': str(n['headline']), 'source': str(n['article_publisher']),
                     'as_of': str(n['article_timestamp']), 'url': str(n.get('url') or '')} for n in dated)
    recent = ' '.join(f"{n['text']} — {n['source']}, {n['as_of']}" for n in changes) or (
        'No dated, display-permitted company update is available in this bundle. A changed share price alone does not establish a business development.')
    valuation = answer(4, 'A certified valuation comparison is unavailable.')
    wall = page.get('wall_street') or {}
    if wall.get('status') == 'AVAILABLE':
        # Quote existing admitted values; never recompute a consensus or target.
        value = wall.get('target_average')
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            valuation += f" The retained Wall Street average target is ${float(value):,.2f}"
            valuation += f" as of {wall.get('as_of') or 'an unavailable date'}. It is a separate analyst estimate."
        if wall.get('consensus'):
            valuation += f" Retained analyst consensus: {wall['consensus']}; period {wall.get('recommendation_period') or 'unavailable'}."
    else:
        valuation += ' Display-permitted analyst consensus and target evidence is unavailable; no analyst agreement is inferred.'
    answers = (
        ('business', 'What does the company do?', answer(0, 'A verified business description is unavailable.')),
        ('changes', 'What changed recently?', recent),
        ('case', 'Why consider or avoid this investment?', answer(1, 'A source-grounded investment reason is unavailable.')),
        ('valuation', 'What do fundamentals, valuation and analysts indicate?', answer(2, 'Company-specific fundamental strengths are unavailable.')+' '+valuation),
        ('catalysts_risks', 'What are the main catalysts and risks?', answer(3, 'Company-specific risks are unavailable.')+' '+answer(6, 'A verified upcoming event is unavailable.')),
        ('change_conditions', 'What would change the assessment?', answer(7, 'Verified change conditions are unavailable.')),
    )
    return {'status': 'AVAILABLE', 'mode': 'DETERMINISTIC_GROUNDED_FALLBACK',
            'external_model_active': False, 'as_of': (page.get('header') or {}).get('price_timestamp'),
            'evidence_ids': tuple(reading.get('evidence_ids') or ()), 'recent_sources': changes,
            'executive_digest': tuple(dict.fromkeys((answers[0][2], answers[2][2], answer(4, valuation)))),
            'answers': tuple({'key':key,'question':question,'answer':text} for key,question,text in answers)}
