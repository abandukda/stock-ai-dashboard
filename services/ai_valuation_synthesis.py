"""On-demand structured synthesis and caching for Phase 7A AI valuation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping

from engines.ai_valuation import (
    FRAMEWORK_VERSION, INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE,
    attach_valuation_comparison, build_ai_valuation,
    input_fingerprint, normalize_ai_valuation_inputs, refresh_price_metrics,
)


DEFAULT_MODEL = "gpt-4o-mini"
CACHE_TTL_SECONDS = 86_400


def llm_is_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _model_snapshot() -> str:
    return os.getenv("ATLAS_AI_VALUATION_MODEL", os.getenv("ATLAS_LLM_MODEL", DEFAULT_MODEL))


def _prompt(context: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the bounded ATLAS relative-multiple research interpreter. Use only the supplied verified inputs. "
                "The valuation method, assumption bounds, confidence, and horizon are deterministic and cannot be changed. "
                "Return one complete JSON object with bear_pe, base_pe, bull_pe, method_rationale, supporting_factors, and risks. "
                "Never invent financial evidence, guidance, revisions, peers, or historical multiples. Never use or infer Atlas Quant Fair Value, "
                "rejected/raw fair value, Wall Street targets, analyst scenarios, decision targets, expected returns, or trade targets. "
                "This is a market-multiple-aware internal diagnostic, not an independent justified multiple. "
                "Select each P/E only inside its named bound and preserve bear_pe <= base_pe <= bull_pe."
            ),
        },
        {"role": "user", "content": json.dumps(dict(context), sort_keys=True, default=str)},
    ]


def synthesize_assumptions(context: Mapping[str, Any], *, caller: Callable[..., Any] | None = None) -> Mapping[str, Any] | None:
    if caller is not None:
        return caller(_prompt(context), _model_snapshot())
    if not llm_is_configured():
        return None
    try:
        from openai import OpenAI
        completion = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
            model=_model_snapshot(), messages=_prompt(context), temperature=0.0,
            max_tokens=600, response_format={"type": "json_object"},
        )
        return json.loads(completion.choices[0].message.content or "{}")
    except Exception:
        return None


def _cache_path(cache_dir: Path, ticker: str, fingerprint: str, model: str) -> Path:
    safe_ticker = re.sub(r"[^A-Z0-9_-]", "", str(ticker or "UNKNOWN").upper())
    safe_model = re.sub(r"[^A-Za-z0-9_.-]", "_", model)
    return cache_dir / f"{safe_ticker}_{FRAMEWORK_VERSION}_{safe_model}_{fingerprint}.json"


def _load(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(payload.get("_cache_epoch", 0)) <= CACHE_TTL_SECONDS:
            return payload.get("result") if isinstance(payload.get("result"), Mapping) else None
    except Exception:
        pass
    return None


def _save(path: Path, result: Mapping[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({"_cache_epoch": time.time(), "result": dict(result)}, default=str), encoding="utf-8")
        temp.replace(path)
        return True
    except OSError:
        return False


def get_ai_valuation_for_research(
    ticker: str,
    row: Mapping[str, Any],
    *,
    cache_dir: str | Path | None = None,
    synthesizer: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Explicit Full-Research entrypoint; never called by scanner or Home."""
    inputs = normalize_ai_valuation_inputs(row)
    gated = build_ai_valuation(row)
    if gated.get("ai_valuation_status") == INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE:
        gated["ai_cache_status"] = "BYPASSED_PUBLICATION_GATE"
        gated["ai_provider_call_count"] = 0
        gated["ai_synthesis_seconds"] = 0.0
        return attach_valuation_comparison(gated, row)
    fingerprint = input_fingerprint(inputs)
    model = _model_snapshot()
    directory = Path(cache_dir or os.getenv("ATLAS_AI_VALUATION_CACHE_DIR", ".atlas_research_cache/ai_valuation"))
    path = _cache_path(directory, ticker, fingerprint, model)
    cached = _load(path)
    if cached:
        refreshed = refresh_price_metrics(cached, inputs.get("current_price"))
        refreshed["ai_cache_status"] = "HIT"
        refreshed["ai_provider_call_count"] = 0
        return attach_valuation_comparison(refreshed, row)

    call = synthesizer or (lambda context: synthesize_assumptions(context))
    started = time.perf_counter()
    result = build_ai_valuation(row, synthesizer=call, model_snapshot=model)
    result["ai_synthesis_seconds"] = round(time.perf_counter() - started, 6)
    result["ai_provider_call_count"] = 1 if llm_is_configured() or synthesizer is not None else 0
    result["ai_cache_status"] = "MISS"
    if result.get("ai_valuation_status") == "PUBLISHED":
        _save(path, result)
    return attach_valuation_comparison(result, row)


__all__ = [
    "CACHE_TTL_SECONDS", "get_ai_valuation_for_research", "llm_is_configured",
    "synthesize_assumptions",
]
