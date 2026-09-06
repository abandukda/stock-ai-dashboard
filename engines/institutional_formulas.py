"""Pure, deterministic implementations of registered professional formulas."""

from __future__ import annotations

import math
import statistics
from typing import Iterable, Sequence


def _finite(value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("NON_FINITE_INPUT")
    return result


def ratio(numerator: float, denominator: float) -> float:
    top, bottom = _finite(numerator), _finite(denominator)
    if bottom == 0:
        raise ValueError("ZERO_DENOMINATOR")
    return top / bottom


def comparable_growth(current: float, prior: float) -> float:
    prior_value = _finite(prior)
    if prior_value <= 0:
        raise ValueError("NONPOSITIVE_COMPARABLE_DENOMINATOR")
    return _finite(current) / prior_value - 1.0


def margin(numerator: float, revenue: float) -> float:
    if _finite(revenue) <= 0:
        raise ValueError("NONPOSITIVE_REVENUE")
    return ratio(numerator, revenue)


def free_cash_flow(operating_cash_flow: float, capital_expenditures: float) -> float:
    return _finite(operating_cash_flow) - abs(_finite(capital_expenditures))


def fcff(ebit: float, tax_rate: float, depreciation_amortization: float,
         capital_expenditures: float, change_in_working_capital: float) -> float:
    tax = _finite(tax_rate)
    if not 0 <= tax <= 1:
        raise ValueError("INVALID_TAX_RATE")
    return _finite(ebit) * (1-tax) + _finite(depreciation_amortization) - abs(_finite(capital_expenditures)) - _finite(change_in_working_capital)


def fcfe(net_income: float, depreciation_amortization: float, capital_expenditures: float,
         change_in_working_capital: float, net_borrowing: float) -> float:
    return _finite(net_income) + _finite(depreciation_amortization) - abs(_finite(capital_expenditures)) - _finite(change_in_working_capital) + _finite(net_borrowing)


def average_return(numerator: float, beginning: float, ending: float) -> float:
    denominator = (_finite(beginning) + _finite(ending)) / 2
    return ratio(numerator, denominator)


def roic(ebit: float, tax_rate: float, invested_capital_begin: float, invested_capital_end: float) -> float:
    return average_return(_finite(ebit) * (1-_finite(tax_rate)), invested_capital_begin, invested_capital_end)


def return_on_equity(net_income: float, equity_begin: float, equity_end: float) -> float:
    """Net income divided by average shareholders' equity."""
    return average_return(net_income, equity_begin, equity_end)


def return_on_assets(net_income: float, assets_begin: float, assets_end: float) -> float:
    """Net income divided by average total assets."""
    return average_return(net_income, assets_begin, assets_end)


def interest_coverage(ebit: float, interest_expense: float) -> float:
    return ratio(ebit, abs(_finite(interest_expense)))


def downside_deviation(returns: Sequence[float], minimum_acceptable_return: float = 0,
                       periods: int = 252) -> float:
    values = list(map(_finite, returns)); threshold = _finite(minimum_acceptable_return)
    if not values:
        raise ValueError("INSUFFICIENT_RETURNS")
    return math.sqrt(sum(min(0.0, value-threshold) ** 2 for value in values)/len(values))*math.sqrt(periods)


def capm_cost_of_equity(risk_free_rate: float, beta: float, equity_risk_premium: float) -> float:
    return _finite(risk_free_rate) + _finite(beta) * _finite(equity_risk_premium)


def wacc(equity_value: float, debt_value: float, cost_of_equity: float,
         cost_of_debt: float, tax_rate: float) -> float:
    equity, debt, tax = _finite(equity_value), _finite(debt_value), _finite(tax_rate)
    if equity < 0 or debt < 0 or equity + debt <= 0 or not 0 <= tax <= 1:
        raise ValueError("INVALID_CAPITAL_STRUCTURE")
    return equity/(equity+debt)*_finite(cost_of_equity) + debt/(equity+debt)*_finite(cost_of_debt)*(1-tax)


def terminal_value_perpetuity(fcfc_next: float, discount_rate: float, growth_rate: float) -> float:
    discount, growth = _finite(discount_rate), _finite(growth_rate)
    if discount <= growth:
        raise ValueError("DISCOUNT_RATE_MUST_EXCEED_GROWTH")
    return _finite(fcfc_next)/(discount-growth)


def dividend_discount_model(dividend_next: float, cost_of_equity: float, growth_rate: float) -> float:
    """Gordon growth value; inputs are decimal rates and next-period dividend."""
    dividend = _finite(dividend_next)
    if dividend < 0:
        raise ValueError("NEGATIVE_DIVIDEND")
    return terminal_value_perpetuity(dividend, cost_of_equity, growth_rate)


def enterprise_to_equity_value(enterprise_value: float, debt: float, cash: float,
                               diluted_shares: float, other_claims: float = 0) -> float:
    shares = _finite(diluted_shares)
    if shares <= 0:
        raise ValueError("INVALID_DILUTED_SHARES")
    equity = _finite(enterprise_value) - _finite(debt) + _finite(cash) - _finite(other_claims)
    return equity / shares


def reward_risk(entry: float, target: float, stop: float) -> float:
    risk = _finite(entry) - _finite(stop)
    if risk <= 0:
        raise ValueError("NONPOSITIVE_PER_SHARE_RISK")
    return (_finite(target) - _finite(entry)) / risk


def sharpe_ratio(returns: Sequence[float], risk_free_returns: Sequence[float] | float = 0,
                 periods: int = 252) -> float:
    values = list(map(_finite, returns))
    if len(values) < 2:
        raise ValueError("INSUFFICIENT_RETURNS")
    rf = ([float(risk_free_returns)] * len(values) if isinstance(risk_free_returns, (int, float))
          else list(map(_finite, risk_free_returns)))
    if len(rf) != len(values):
        raise ValueError("RETURN_ALIGNMENT_REQUIRED")
    excess = [value - rate for value, rate in zip(values, rf)]
    deviation = statistics.stdev(excess)
    if deviation == 0:
        raise ValueError("ZERO_RETURN_DEVIATION")
    return statistics.fmean(excess) / deviation * math.sqrt(periods)


def sortino_ratio(returns: Sequence[float], minimum_acceptable_return: float = 0,
                  periods: int = 252) -> float:
    values = list(map(_finite, returns)); threshold = _finite(minimum_acceptable_return)
    if len(values) < 2:
        raise ValueError("INSUFFICIENT_RETURNS")
    downside = [min(0.0, value - threshold) ** 2 for value in values]
    deviation = math.sqrt(sum(downside) / len(values))
    if deviation == 0:
        raise ValueError("ZERO_DOWNSIDE_DEVIATION")
    return (statistics.fmean(values) - threshold) / deviation * math.sqrt(periods)


def dcf_equity_value(forecast_fcff: Sequence[float], discount_rate: float, terminal_growth: float,
                     debt: float, cash: float, diluted_shares: float, other_claims: float = 0) -> dict[str, float]:
    if not forecast_fcff or _finite(diluted_shares) <= 0:
        raise ValueError("INSUFFICIENT_DCF_INPUTS")
    rate = _finite(discount_rate)
    if rate <= 0:
        raise ValueError("INVALID_DISCOUNT_RATE")
    explicit = sum(_finite(value)/(1+rate)**year for year, value in enumerate(forecast_fcff, 1))
    terminal = terminal_value_perpetuity(_finite(forecast_fcff[-1])*(1+_finite(terminal_growth)), rate, terminal_growth)
    terminal_pv = terminal/(1+rate)**len(forecast_fcff)
    enterprise = explicit + terminal_pv
    equity = enterprise-_finite(debt)+_finite(cash)-_finite(other_claims)
    return {"enterprise_value": enterprise, "equity_value": equity, "per_share_value": equity/_finite(diluted_shares),
            "terminal_value_pct_of_enterprise_value": terminal_pv/enterprise if enterprise else 0.0}


def annualized_volatility(returns: Sequence[float], periods: int = 252) -> float:
    if len(returns) < 2:
        raise ValueError("INSUFFICIENT_RETURNS")
    return statistics.stdev(map(_finite, returns))*math.sqrt(periods)


def beta(stock_returns: Sequence[float], benchmark_returns: Sequence[float]) -> float:
    if len(stock_returns) != len(benchmark_returns) or len(stock_returns) < 2:
        raise ValueError("RETURN_ALIGNMENT_REQUIRED")
    stock, market = list(map(_finite, stock_returns)), list(map(_finite, benchmark_returns))
    variance = statistics.variance(market)
    if variance == 0:
        raise ValueError("ZERO_BENCHMARK_VARIANCE")
    return sum((a-statistics.fmean(stock))*(b-statistics.fmean(market)) for a,b in zip(stock,market))/(len(stock)-1)/variance


def max_drawdown(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("EMPTY_SERIES")
    peak, worst = _finite(values[0]), 0.0
    for raw in values:
        value = _finite(raw); peak = max(peak, value); worst = min(worst, value/peak-1)
    return worst


def cagr(beginning: float, ending: float, years: float) -> float:
    if _finite(beginning) <= 0 or _finite(ending) < 0 or _finite(years) <= 0:
        raise ValueError("INVALID_CAGR_INPUTS")
    return (_finite(ending)/_finite(beginning))**(1/_finite(years))-1


def earnings_surprise(actual: float, consensus: float, *, near_zero: float = 1e-9) -> float:
    estimate = _finite(consensus)
    if abs(estimate) <= near_zero:
        raise ValueError("CONSENSUS_NEAR_ZERO")
    return (_finite(actual)-estimate)/abs(estimate)


__all__ = ["annualized_volatility", "average_return", "beta", "cagr", "capm_cost_of_equity", "comparable_growth", "dcf_equity_value", "dividend_discount_model", "downside_deviation", "earnings_surprise", "enterprise_to_equity_value", "fcfe", "fcff", "free_cash_flow", "interest_coverage", "margin", "max_drawdown", "ratio", "return_on_assets", "return_on_equity", "reward_risk", "roic", "sharpe_ratio", "sortino_ratio", "terminal_value_perpetuity", "wacc"]
