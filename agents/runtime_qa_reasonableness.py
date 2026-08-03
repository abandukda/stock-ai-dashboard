from __future__ import annotations
import re

def _values(label: str, text: str):
    pattern = re.compile(rf"{re.escape(label)}\s*[:\-]?\s*\$?([+\-]?\d+(?:\.\d+)?)\s*%?", re.I)
    out=[]
    for m in pattern.finditer(text):
        try: out.append(float(m.group(1)))
        except Exception: pass
    return out

def evaluate_visible_page(page_name: str, visible_text: str):
    issues=[]
    for label in ("Opportunity","Confidence"):
        for value in _values(label,visible_text):
            if not 0 <= value <= 100:
                issues.append({"severity":"CRITICAL","category":"Score Range","page":page_name,"element":label,"expected":"0–100","actual":str(value),"recommendation":"Trace normalization and formatting.","likely_files":["engines/institutional_scoring_engine.py","engines/confidence_calibration_engine.py"],"regression_test":f"Assert {label} remains within 0–100."})
    if "BUY NOW" in visible_text.upper():
        conf=_values("Confidence",visible_text)
        ret=_values("Expected Return",visible_text)
        if conf and min(conf)<50:
            issues.append({"severity":"CRITICAL","category":"Decision Reasonableness","page":page_name,"element":"BUY NOW / Confidence","expected":"BUY NOW has adequate confidence.","actual":str(conf),"recommendation":"Reconcile committee verdict and confidence.","likely_files":["engines/investment_committee_v104.py","engines/confidence_calibration_engine.py"],"regression_test":"Prevent BUY NOW below confidence floor."})
        if ret and min(ret)<8:
            issues.append({"severity":"CRITICAL","category":"Decision Reasonableness","page":page_name,"element":"BUY NOW / Expected Return","expected":"BUY NOW has material upside.","actual":str(ret),"recommendation":"Repair valuation or downgrade verdict.","likely_files":["engines/investment_committee_v104.py","engines/atlas_research_builder_v2.py"],"regression_test":"Prevent BUY NOW below expected-return floor."})
    return issues
