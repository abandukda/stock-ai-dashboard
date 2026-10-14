from services.g6_annual_financial_series import build_annual_series

def fact(concept,value,unit="usd",i=0):
    return {"concept":concept,"value":value,"unit":{"canonical":"USD","currency":"USD","kind":"CURRENCY","original":unit},
            "provenance":{"source_fact_index":i}}
def filing(year, accepted, accession, facts):
    return {"identity":{"year":year,"endDate":f"{year}-12-31 00:00:00","filedDate":accepted,"acceptedDate":accepted,"accessNumber":accession},"facts":facts}
def record(filings): return {"contract":"ATLAS_G6_ANNUAL_STATEMENT_NORMALIZATION_V1","ticker":"ABC","normalized_sha256":"a"*64,"filings":filings}
def facts(revenue=100,op=20,cfo=30,capex=5,debt_current=4,debt_long=10):
    return [fact("us-gaap_Revenues",revenue),fact("us-gaap_OperatingIncomeLoss",op),fact("us-gaap_NetCashProvidedByUsedInOperatingActivities",cfo),fact("us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",capex),fact("us-gaap_DebtCurrent",debt_current),fact("us-gaap_LongTermDebtNoncurrent",debt_long)]

def test_period_correct_metrics_and_derived_values():
    x=build_annual_series(record([filing(2024,"2025-02-01 10:00:00","old",facts())]))["periods"][0]
    assert x["metrics"]["operating_margin"]["value"] == .2
    assert x["metrics"]["free_cash_flow"]["value"] == 25
    assert x["metrics"]["total_debt"]["value"] == 14

def test_latest_accepted_restatement_wins():
    old=filing(2024,"2025-02-01 10:00:00","old",facts(100)); new=filing(2024,"2025-03-01 10:00:00","new",facts(110))
    x=build_annual_series(record([old,new]))["periods"][0]
    assert x["accession"]=="new" and x["restatement_candidates"]==2 and x["metrics"]["revenue"]["value"]==110

def test_ambiguous_duplicate_concept_fails_closed():
    fs=facts(); fs.append(fact("us-gaap_Revenues",999,i=9))
    x=build_annual_series(record([filing(2024,"2025-02-01 10:00:00","a",fs)]))["periods"][0]
    assert x["metrics"]["revenue"]["status"]=="UNAVAILABLE"
    assert x["metrics"]["operating_margin"]["status"]=="UNAVAILABLE"

def test_projection_is_explicitly_mechanical_and_requires_three_periods():
    two=[filing(y,f"{y+1}-02-01 10:00:00",str(y),facts(100+10*(y-2022))) for y in (2022,2023)]
    assert build_annual_series(record(two))["projections"]["revenue"]["status"]=="UNAVAILABLE"
    three=two+[filing(2024,"2025-02-01 10:00:00","2024",facts(120))]
    p=build_annual_series(record(three))["projections"]["revenue"]
    assert p["value"]==130 and p["classification"]=="MECHANICAL_TREND_NOT_ANALYST_FORECAST"

def test_rejects_wrong_normalization_contract():
    try: build_annual_series({"contract":"wrong"})
    except ValueError as e: assert str(e)=="NORMALIZED_CONTRACT_MISMATCH"
    else: raise AssertionError("must fail closed")
