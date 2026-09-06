from pathlib import Path
import pytest
from services.alert_events import event
from services.performance_tracking import aggregate,append_snapshots,build_snapshot,mature_snapshot
from services.regression_monitoring import compare_runs
from services.volume_screener import build_volume_screener

def row(action='BUY_NOW',rvol=2.0,technical='SETUP_FORMING',confirmed=False):
 return {'ticker':'ABC','company':'Acme','price':10,'canonical_investment_evaluation':{'evaluated_at':'2026-09-04T20:00:00Z','methodology_version':'M1','methodology_registry_version':'R1','input_digest':'same','market_snapshot':{'price':10},'guidance':{'state':action,'opportunity_thesis':'VALUE_RERATING'},'opportunity':70,'decision_confidence':80,'component_coverage':90,'technical_confirmation':{'state':technical},'volume_intelligence':{'status':'AVAILABLE','relative_volume':rvol,'volume_confirmed':confirmed,'average_dollar_volume':1_000_000,'as_of':'2026-09-04','evidence_id':'V1'},'atlas_valuation':{'professional_valuation_v2':{'status':'PUBLISHED','atlas_base_fair_value':15,'atlas_expected_return':50,'valuation_confidence':60,'valuation_methodology_version':'V2','models':[]}},'trade_plan':{'entry_low':9,'entry_high':11,'stop':8},**{k:{'score':60} for k in ('technical_quality','fundamental_quality','valuation_quality','risk_quality','entry_quality','volume_quality')}}}

def test_snapshot_is_deterministic_append_only_and_horizons_do_not_look_ahead(tmp_path:Path):
 s=build_snapshot(row()); assert s==build_snapshot(row());p=tmp_path/'history.jsonl';assert append_snapshots(p,[s])==1 and append_snapshots(p,[s])==0
 assert s['action_stars']==5.0 and s['return_policy']['transaction_costs']=='excluded'
 changed={**s,'action':'AVOID','snapshot_id':'different'}
 with pytest.raises(ValueError,match='IMMUTABLE_SNAPSHOT_CONFLICT'): append_snapshots(p,[changed])
 assert [x['horizon_sessions'] for x in mature_snapshot(s,[{'close':11}]*4)]==[1]
 records=mature_snapshot(s,[{'close':11}]*5,[{'close':100},{'close':101},{'close':102},{'close':103},{'close':104}]);assert records[-1]['horizon_sessions']==5 and records[-1]['mfe']==pytest.approx(.1)
 assert mature_snapshot(s,[{'timestamp':'2026-09-03T20:00:00Z','close':99}])==[]

def test_volume_discovery_never_changes_canonical_action_and_breakout_requires_confirmation():
 wait=build_volume_screener([row(action='WAIT_FOR_CONFIRMATION')])[0];assert wait['volume_state']=='VOLUME_SURGE' and wait['action']=='WAIT_FOR_CONFIRMATION' and wait['action_stars']==3.5
 breakout=build_volume_screener([row(technical='BREAKOUT_CONFIRMED',confirmed=True)])[0];assert breakout['volume_state']=='BREAKOUT_CONFIRMED'

def test_alert_and_regression_foundations_are_non_mutating():
 assert event('HIGH_VOLUME','ABC','2026-09-04',{})['delivery_status']=='NOT_SENT'
 old=row();new=row(action='ACCUMULATE');assert compare_runs([old],[new])[0]['type']=='ACTION_CHANGED_WITHOUT_INPUT_CHANGE'

def test_performance_aggregation_is_observational():
 result=aggregate([{'action':'BUY_NOW','price_return':.1,'benchmark_relative_return':.02,'max_drawdown':-.03}]);assert result[0]['sample_count']==1 and result[0]['win_rate']==1
