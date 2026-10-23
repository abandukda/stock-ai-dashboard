"""Read-only explanation of the existing customer projection; no model/provider calls."""
from collections.abc import Mapping
from typing import Any
import math


def _positive_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def build_reasoning_packet(page: Mapping[str, Any]) -> dict[str, Any]:
    """Explain admitted inputs without inventing valuation drivers or AI claims.

    This is an educational projection of an existing customer-authorized page,
    not a source certifier, a price refresh, or a replacement scoring model.
    """
    if page.get('status') != 'AVAILABLE':
        return {'status': 'UNAVAILABLE', 'items': (), 'limitations': ()}
    header = page.get('header') or {}
    price, fair_value = header.get('price'), header.get('fair_value')
    identity = dict(page.get('identity') or {})
    ids = tuple((page.get('reading_views') or {}).get('evidence_ids') or ())
    items = []
    def item(kind, label, text, **extra):
        items.append({'kind': kind, 'label': label, 'text': text,
                      'evidence_ids': ids, **extra})
    if _positive_number(price):
        item('RETAINED_FACT', 'Price evidence',
             f'The last certified close is ${price:,.2f}. It is a historical observation, not a live quote or an executable offer.',
             value=price, unit='USD_PER_SHARE', as_of=header.get('price_timestamp'),
             source=header.get('price_source'))
    if _positive_number(fair_value):
        item('MODEL_ESTIMATE', 'Valuation estimate',
             f'ATLAS Fair Value is ${fair_value:,.2f}. It is a model estimate rather than a promised future price.',
             value=fair_value, unit='USD_PER_SHARE', as_of=None,
             source='CERTIFIED_ATLAS_VALUATION')
    if _positive_number(price) and _positive_number(fair_value):
        # Reproducible educational arithmetic only; never consume or modify a
        # score, recommendation, execution price or persisted gap authority.
        gap = (fair_value / price - 1) * 100
        if math.isfinite(gap):
            item('DETERMINISTIC_CALCULATION', 'What the price comparison means',
                 f'(${fair_value:,.2f} ÷ ${price:,.2f} − 1) × 100 = {gap:+.1f}%. '
                 f'The estimate is {abs(gap):.1f}% {"above" if gap >= 0 else "below"} the retained close. '
                 'This gap is neither an expected return nor a probability of success.',
                 value=gap, unit='PERCENT', formula='(fair_value / certified_close - 1) * 100',
                 input_values={'fair_value':fair_value, 'certified_close':price},
                 as_of=header.get('price_timestamp'))
    models = (page.get('financial_depth') or {}).get('valuation_models') or ()
    supported = []
    for model in models:
        if (not isinstance(model, Mapping)
                or model.get('source') != 'CERTIFIED_ATLAS_VALUATION'
                or not _positive_number(model.get('value'))):
            continue
        assumptions = model.get('assumptions')
        if not isinstance(assumptions, Mapping) or not assumptions:
            continue
        valid_assumptions = {}
        for key, value in assumptions.items():
            # Preserve source units/labels; do not turn missing/nonfinite or
            # structured values into an apparently meaningful model driver.
            numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
            if numeric:
                try:
                    valid = math.isfinite(value)
                except OverflowError:
                    valid = False
            else:
                valid = isinstance(value, str) and bool(value.strip())
            if str(key).strip() and valid:
                valid_assumptions[str(key)] = value
        if not valid_assumptions:
            continue
        supported.append({'name':str(model.get('name') or model.get('methodology_id') or 'Retained model'),
                          'methodology_id':model.get('methodology_id'),
                          'fiscal_period':model.get('fiscal_period'),
                          'assumptions':valid_assumptions})
    limitations = [
        'A favorable valuation gap alone does not establish business quality, a near-term catalyst or a suitable position size.',
        'Strong reported earnings do not guarantee a rising share price; expectations, valuation and new guidance can differ.',
    ]
    if not supported:
        limitations.append('The retained bundle does not disclose the valuation model assumptions needed to explain the estimate. No growth, margin or discount-rate driver is inferred.')
    if not header.get('price_timestamp'):
        limitations.append('The certified-close date is unavailable; currentness cannot be established.')
    return {'status':'AVAILABLE', 'schema':'ATLAS_RESEARCH_REASONING_PACKET_V1',
            'mode':'DETERMINISTIC_EDUCATIONAL_PROJECTION', 'external_model_active':False,
            'identity':identity, 'items':tuple(items), 'valuation_assumptions':tuple(supported),
            'limitations':tuple(limitations),
            'interpretation_scope':'Explains retained inputs; does not establish current data or comprehensive AI analysis.'}


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
            'answers': tuple({'key':key,'question':question,'answer':text} for key,question,text in answers),
            'reasoning_packet': build_reasoning_packet(page)}
