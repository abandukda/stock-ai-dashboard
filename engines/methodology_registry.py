"""Governed registry for standard metrics and explicitly ATLAS-derived synthesis.

Permanent rule: a canonical metric bearing an industry-standard name must use
the registered standard definition (or a documented equivalent). Proprietary
aggregation is permitted only when it is explicitly named ATLAS-derived.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


REGISTRY_VERSION = "ATLAS_INSTITUTIONAL_METHODOLOGY_REGISTRY_V1"


@dataclass(frozen=True)
class Methodology:
    methodology_id: str
    name: str
    version: str
    category: str
    methodology_family: str
    industry_reference: str
    formula_description: str
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...] = ()
    input_authorities: tuple[str, ...] = ()
    eligible_company_types: tuple[str, ...] = ("ALL",)
    period_alignment_rules: str = "Inputs must use the same fiscal period and basis."
    unit_rules: str = "Canonical raw units; percentages stored as decimal ratios."
    normalization_rules: str = "No synthetic values; normalize once at ingestion."
    validation_rules: str = "Finite inputs, valid denominators, and explicit dates required."
    fallback_policy: str = "Fail closed or route to another eligible registered method."
    publication_requirements: str = "All required inputs, lineage, period, unit, and method version available."
    customer_interpretation: str = "Professional analytical evidence; not a recommendation by itself."
    is_standard_method: bool = True
    is_atlas_derived: bool = False

    def record(self) -> dict[str, object]:
        return asdict(self)


def _standard(methodology_id: str, name: str, category: str, formula: str,
              inputs: Iterable[str], *, family: str = "Recognized institutional practice",
              eligible: tuple[str, ...] = ("ALL",), reference: str = "CFA-style financial analysis / standard corporate finance") -> Methodology:
    return Methodology(methodology_id, name, "1.0", category, family, reference,
                       formula, tuple(inputs), eligible_company_types=eligible)


def _atlas(methodology_id: str, name: str, category: str, formula: str,
           inputs: Iterable[str]) -> Methodology:
    return Methodology(methodology_id, name, "1.0", category, "ATLAS proprietary synthesis",
                       "ATLAS governance specification", formula, tuple(inputs),
                       is_standard_method=False, is_atlas_derived=True,
                       customer_interpretation="ATLAS-derived synthesis of registered evidence; not an industry-standard metric.")


_METHODS = (
    _standard("FIN_REVENUE_GROWTH_YOY_V1", "Revenue Growth", "FUNDAMENTAL", "current comparable revenue / prior comparable revenue - 1", ("revenue_current", "revenue_prior")),
    _standard("FIN_EPS_GROWTH_YOY_V1", "Diluted EPS Growth", "FUNDAMENTAL", "current comparable diluted EPS / prior comparable diluted EPS - 1", ("diluted_eps_current", "diluted_eps_prior")),
    _standard("FIN_GROSS_MARGIN_V1", "Gross Margin", "FUNDAMENTAL", "gross profit / revenue", ("gross_profit", "revenue")),
    _standard("FIN_OPERATING_MARGIN_V1", "Operating Margin", "FUNDAMENTAL", "operating income / revenue", ("operating_income", "revenue")),
    _standard("FIN_NET_MARGIN_V1", "Net Margin", "FUNDAMENTAL", "net income / revenue", ("net_income", "revenue")),
    _standard("FIN_FCF_V1", "Free Cash Flow", "CASH_FLOW", "operating cash flow - capital expenditures", ("operating_cash_flow", "capital_expenditures")),
    _standard("FIN_FCFF_V1", "Free Cash Flow to Firm", "CASH_FLOW", "EBIT*(1-tax rate)+D&A-capex-change in NWC", ("ebit", "tax_rate", "depreciation_amortization", "capital_expenditures", "change_in_working_capital")),
    _standard("FIN_FCFE_V1", "Free Cash Flow to Equity", "CASH_FLOW", "net income+D&A-capex-change in NWC+net borrowing", ("net_income", "depreciation_amortization", "capital_expenditures", "change_in_working_capital", "net_borrowing")),
    _standard("FIN_ROE_V1", "Return on Equity", "FUNDAMENTAL", "net income / average shareholders' equity", ("net_income", "equity_begin", "equity_end")),
    _standard("FIN_ROA_V1", "Return on Assets", "FUNDAMENTAL", "net income / average total assets", ("net_income", "assets_begin", "assets_end")),
    _standard("FIN_ROIC_V1", "Return on Invested Capital", "FUNDAMENTAL", "NOPAT / average invested capital", ("ebit", "tax_rate", "invested_capital_begin", "invested_capital_end")),
    _standard("FIN_NET_DEBT_EBITDA_V1", "Net Debt / EBITDA", "RISK", "(debt-cash) / EBITDA", ("debt", "cash", "ebitda")),
    _standard("FIN_CURRENT_RATIO_V1", "Current Ratio", "LIQUIDITY", "current assets / current liabilities", ("current_assets", "current_liabilities")),
    _standard("FIN_INTEREST_COVERAGE_EBIT_V1", "Interest Coverage", "RISK", "EBIT / absolute interest expense", ("ebit", "interest_expense")),
    _standard("FORECAST_REVISION_V1", "Consensus Estimate Revision", "FORECAST", "current comparable consensus / prior comparable consensus - 1", ("current_consensus", "prior_consensus", "metric", "fiscal_period", "basis")),
    _standard("FORECAST_SURPRISE_V1", "Earnings Surprise", "FORECAST", "(actual-consensus) / absolute consensus", ("actual", "consensus")),
    _standard("VAL_WACC_V1", "Weighted Average Cost of Capital", "VALUATION", "E/(D+E)*Re + D/(D+E)*Rd*(1-T)", ("equity_value", "debt_value", "cost_of_equity", "cost_of_debt", "tax_rate")),
    _standard("VAL_CAPM_COE_V1", "CAPM Cost of Equity", "VALUATION", "risk-free rate + beta*equity risk premium", ("risk_free_rate", "beta", "equity_risk_premium")),
    _standard("VAL_FCFF_DCF_V1", "FCFF Discounted Cash Flow", "VALUATION", "PV of forecast FCFF plus PV of terminal value, less net debt and claims", ("forecast_fcff", "wacc", "terminal_growth", "debt", "cash", "diluted_shares"), eligible=("PROFITABLE_OPERATING_COMPANY", "PROFITABLE_PHARMA", "HIGH_GROWTH_SOFTWARE", "COMMODITY_PRODUCER")),
    _standard("VAL_FORWARD_PE_V1", "Forward Earnings Multiple", "VALUATION", "normalized forward EPS * justified forward P/E", ("forward_eps", "forward_eps_period", "justified_pe", "multiple_basis"), eligible=("PROFITABLE_OPERATING_COMPANY", "PROFITABLE_PHARMA", "HIGH_GROWTH_SOFTWARE", "BANK", "INSURER")),
    _standard("VAL_EV_EBITDA_V1", "EV / EBITDA", "VALUATION", "forward EBITDA*justified EV/EBITDA-net debt-other claims", ("forward_ebitda", "justified_ev_ebitda", "debt", "cash", "diluted_shares")),
    _standard("VAL_P_FCF_V1", "Price / Free Cash Flow", "VALUATION", "normalized equity FCF*justified P/FCF / diluted shares", ("normalized_fcf", "justified_p_fcf", "diluted_shares")),
    _standard("VAL_DDM_GORDON_V1", "Dividend Discount Model", "VALUATION", "D1 / (cost of equity-growth)", ("dividend_next", "cost_of_equity", "terminal_growth")),
    _standard("RISK_VOLATILITY_V1", "Annualized Volatility", "RISK", "sample standard deviation of daily returns * sqrt(252)", ("daily_returns",)),
    _standard("RISK_BETA_V1", "Beta", "RISK", "covariance(stock, benchmark) / variance(benchmark)", ("stock_returns", "benchmark_returns")),
    _standard("RISK_MAX_DRAWDOWN_V1", "Maximum Drawdown", "RISK", "minimum(value/running peak - 1)", ("values",)),
    _standard("TECH_SMA_V1", "Simple Moving Average", "TECHNICAL", "arithmetic mean of N completed adjusted closing prices", ("completed_adjusted_closes", "period")),
    _standard("TECH_RSI_WILDER_V1", "Wilder RSI", "TECHNICAL", "100-100/(1+Wilder-smoothed average gain / average loss)", ("completed_adjusted_closes", "period")),
    _standard("TECH_ATR_WILDER_V1", "Wilder ATR", "TECHNICAL", "Wilder-smoothed true range", ("completed_adjusted_ohlc", "period")),
    _standard("TECH_COMPLETED_DAILY_RVOL_V1", "Completed-Daily Relative Volume", "TECHNICAL", "completed daily volume / prior completed-session mean volume", ("completed_daily_volume", "prior_completed_daily_volumes")),
    _standard("TRADE_REWARD_RISK_V1", "Reward / Risk", "TRADE_PLAN", "(target-entry)/(entry-stop)", ("entry", "target", "stop")),
    _standard("PERF_TOTAL_RETURN_V1", "Total Return", "PERFORMANCE", "(ending value+distributions)/beginning value-1", ("beginning_value", "ending_value", "distributions")),
    _standard("PERF_CAGR_V1", "Compound Annual Growth Rate", "PERFORMANCE", "(ending/beginning)^(1/years)-1", ("beginning_value", "ending_value", "years")),
    _standard("PERF_SHARPE_V1", "Sharpe Ratio", "PERFORMANCE", "annualized excess return / annualized standard deviation", ("period_returns", "period_risk_free_rate")),
    _standard("PERF_SORTINO_V1", "Sortino Ratio", "PERFORMANCE", "annualized excess return / annualized downside deviation", ("period_returns", "minimum_acceptable_return")),
    _atlas("ATLAS_FUNDAMENTAL_QUALITY_V1", "ATLAS Fundamental Quality", "SYNTHESIS", "governed weighted normalization of registered fundamental metrics", ("registered_fundamental_metrics",)),
    _atlas("ATLAS_RISK_QUALITY_V1", "ATLAS Risk Quality", "SYNTHESIS", "governed weighted normalization of registered risk metrics", ("registered_risk_metrics",)),
    _atlas("ATLAS_TECHNICAL_QUALITY_V1", "ATLAS Technical Quality", "SYNTHESIS", "governed weighted normalization of registered technical evidence", ("registered_technical_metrics",)),
    _atlas("ATLAS_DECISION_METRICS_V1", "ATLAS Opportunity and Decision Confidence", "SYNTHESIS", "Founder-governed six-pillar aggregation", ("six_pillars", "evidence_coverage")),
)

REGISTRY = {method.methodology_id: method for method in _METHODS}


def methodology(methodology_id: str) -> Methodology:
    if methodology_id not in REGISTRY:
        raise KeyError(f"UNREGISTERED_CANONICAL_METHODOLOGY:{methodology_id}")
    return REGISTRY[methodology_id]


def assert_registered(methodology_id: str, *, standard_name: bool | None = None) -> Methodology:
    item = methodology(methodology_id)
    if standard_name is True and not item.is_standard_method:
        raise ValueError(f"STANDARD_NAME_REQUIRES_STANDARD_METHOD:{methodology_id}")
    if item.is_standard_method == item.is_atlas_derived:
        raise ValueError(f"INVALID_STANDARD_DERIVED_CLASSIFICATION:{methodology_id}")
    return item


def registry_snapshot() -> dict[str, object]:
    return {"version": REGISTRY_VERSION, "methodologies": {key: value.record() for key, value in sorted(REGISTRY.items())}}


__all__ = ["Methodology", "REGISTRY", "REGISTRY_VERSION", "assert_registered", "methodology", "registry_snapshot"]
