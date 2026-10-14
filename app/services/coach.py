"""Personal financial coach (R2): 30-day forecast, what-if, grounded product offers."""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.data import mock_data
from app.services.ai import get_ai

HORIZON_DAYS = 30
HISTORY_DAYS = 14


def forecast(customer_id: str, delay_days: int = 0, extra_expense_usd: float = 0.0) -> dict[str, Any]:
    persona = mock_data.PERSONAS.get(customer_id)
    if persona is None or persona["wallet"] is None:
        return {"customer_id": customer_id, "available": False, "reason": "Account under compliance investigation; coaching disabled."}

    w = persona["wallet"]
    today = dt.date(2026, 10, 14)
    delay_days = max(0, min(20, int(delay_days)))
    extra_expense_usd = max(0.0, float(extra_expense_usd))
    inflow_day = w["pending_inflow"]["day"] + delay_days

    # History: gentle variation ending at today's balance
    history = []
    for i in range(HISTORY_DAYS, 0, -1):
        wiggle = ((i * 37) % 11 - 5) * 40
        history.append({"date": (today - dt.timedelta(days=i)).isoformat(), "balance_usd": round(w["balance_usd"] + i * w["daily_spend_usd"] * 0.4 + wiggle, 2)})
    history.append({"date": today.isoformat(), "balance_usd": w["balance_usd"]})

    bal = w["balance_usd"]
    points, events = [], []
    for d in range(1, HORIZON_DAYS + 1):
        bal -= w["daily_spend_usd"]
        for f in w["fixed_outflows"]:
            if f["day"] == d:
                bal -= f["amount_usd"]
                events.append({"day": d, "label": f["label"], "amount_usd": -f["amount_usd"]})
        if extra_expense_usd and d == 7:
            bal -= extra_expense_usd
            events.append({"day": d, "label": "What-if expense", "amount_usd": -extra_expense_usd})
        if d == inflow_day:
            bal += w["pending_inflow"]["amount_usd"]
            events.append({"day": d, "label": w["pending_inflow"]["label"], "amount_usd": w["pending_inflow"]["amount_usd"]})
        points.append({"date": (today + dt.timedelta(days=d)).isoformat(), "day": d, "balance_usd": round(bal, 2)})

    low_days = [p for p in points if p["balance_usd"] < w["low_threshold_usd"]]
    lowest = min(points, key=lambda p: p["balance_usd"])
    gap_days = len(low_days)
    shortfall = round(max(0.0, w["low_threshold_usd"] - lowest["balance_usd"]), 2)

    return {
        "customer_id": customer_id,
        "available": True,
        "name": persona["name"],
        "balance_usd": w["balance_usd"],
        "low_threshold_usd": w["low_threshold_usd"],
        "history": history,
        "forecast": points,
        "events": events,
        "pending_inflow": w["pending_inflow"] | {"day": inflow_day},
        "dip": {
            "detected": gap_days > 0,
            "first_low_date": low_days[0]["date"] if low_days else None,
            "gap_days": gap_days,
            "lowest_date": lowest["date"],
            "lowest_balance_usd": lowest["balance_usd"],
            "shortfall_usd": shortfall,
        },
        "inputs": {"delay_days": delay_days, "extra_expense_usd": extra_expense_usd},
        "model": "Vertex AI forecast (mock)",
    }


def products(customer_id: str) -> list[dict[str, Any]]:
    persona = mock_data.PERSONAS.get(customer_id)
    if persona is None or persona["wallet"] is None:
        return []
    return [p | {"eligible": persona["avg_monthly_deposits_usd"] >= p["min_monthly_inflow_usd"]} for p in mock_data.PRODUCTS]


def eligibility(customer_id: str, product_id: str, delay_days: int = 0, extra_expense_usd: float = 0.0) -> dict[str, Any]:
    fc = forecast(customer_id, delay_days, extra_expense_usd)
    if not fc["available"]:
        return {"eligible": False, "explanation": fc["reason"]}
    persona = mock_data.PERSONAS[customer_id]
    product = next(p for p in mock_data.PRODUCTS if p["product_id"] == product_id)
    eligible = persona["avg_monthly_deposits_usd"] >= product["min_monthly_inflow_usd"]
    dip = fc["dip"]
    first = persona["name"].split()[0]

    if product["kind"] == "credit":
        draw = round(min(product["limit_usd"], dip["shortfall_usd"] + 500), -2) if dip["detected"] else 0
        interest = round(draw * product["apr_pct"] / 100 / 365 * max(dip["gap_days"], 1), 2)
        fallback = (
            f"Hi {first}, your balance is forecast to drop below ${fc['low_threshold_usd']:,.0f} on {dip['first_low_date']} "
            f"and stay low for {dip['gap_days']} days until {fc['pending_inflow']['label']} arrives. You're pre-qualified for the "
            f"{product['title']} at {product['apr_pct']}% APR: drawing ${draw:,.0f} bridges the {dip['gap_days']}-day gap for about "
            f"${interest:,.2f} in interest, with zero overdraft fees. It repays automatically when the invoice lands."
            if dip["detected"]
            else f"Hi {first}, no cash-flow gap is forecast, so you don't need the {product['title']} right now. It stays pre-approved."
        )
        numbers = {"suggested_draw_usd": draw, "estimated_interest_usd": interest}
    else:
        fallback = (
            f"Hi {first}, the {product['title']} earns {product['apr_pct']}% on money above your safety buffer and moves it back "
            f"before a dip. {'Turn it on after the upcoming gap closes.' if dip['detected'] else 'You have surplus cash to put to work now.'}"
        )
        numbers = {}

    explanation = get_ai().text(
        "You are a friendly bank financial coach. In 3 plain-English sentences, explain to the customer how this product "
        f"helps. Use only these facts. Customer={first}, forecast_dip={dip}, product={product['title']}, "
        f"apr={product['apr_pct']}%, terms={product['terms']}, numbers={numbers}, eligible={eligible}.",
        fallback,
    )
    return {"product": product, "eligible": eligible, "dip": dip, "explanation": explanation, "grounded_terms": product["terms"]} | numbers
