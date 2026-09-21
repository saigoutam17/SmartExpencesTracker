from openai import OpenAI
import json


client = OpenAI()


def analyze_spending(
    total,
    monthly_total,
    previous_month_total,
    category_totals,
    budget_amount
):

    # ============================================================
    # CONVERT VALUES SAFELY
    # ============================================================

    total = float(total or 0)
    monthly_total = float(monthly_total or 0)
    previous_month_total = float(previous_month_total or 0)
    budget_amount = float(budget_amount or 0)

    # ============================================================
    # PREPARE CATEGORY DATA
    # ============================================================

    categories = []

    for category in category_totals:

        categories.append({
            "category": str(category["category"]),
            "total": float(category["total"] or 0)
        })

    # ============================================================
    # 1. HIGHEST SPENDING CATEGORY
    # CALCULATED DIRECTLY FROM REAL DATABASE DATA
    # ============================================================

    if categories:

        highest = max(
            categories,
            key=lambda x: x["total"]
        )

        highest_category = (
            f"{highest['category']} "
            f"(₹{highest['total']:.2f})"
        )

    else:

        highest_category = "No expenses recorded"

    # ============================================================
    # 2. SPENDING TREND
    # CALCULATED DIRECTLY
    # ============================================================

    if previous_month_total > 0:

        percentage_change = (
            (monthly_total - previous_month_total)
            / previous_month_total
        ) * 100

        if percentage_change > 0:

            trend = (
                f"Increasing "
                f"(+{percentage_change:.1f}% vs last month)"
            )

        elif percentage_change < 0:

            trend = (
                f"Decreasing "
                f"({percentage_change:.1f}% vs last month)"
            )

        else:

            trend = "Stable compared with last month"

    else:

        if monthly_total > 0:
            trend = "Increasing (no previous month data)"
        else:
            trend = "No spending recorded this month"

    # ============================================================
    # 3. BUDGET STATUS
    # CALCULATED DIRECTLY
    # ============================================================

    if budget_amount > 0:

        budget_percentage = (
            monthly_total / budget_amount
        ) * 100

        remaining = budget_amount - monthly_total

        if budget_percentage >= 100:

            budget_status = (
                f"Exceeded "
                f"({budget_percentage:.1f}% of budget used)"
            )

        elif budget_percentage >= 80:

            budget_status = (
                f"Near limit "
                f"({budget_percentage:.1f}% of budget used)"
            )

        elif budget_percentage >= 50:

            budget_status = (
                f"Moderate "
                f"({budget_percentage:.1f}% of budget used)"
            )

        else:

            budget_status = (
                f"Under control "
                f"({budget_percentage:.1f}% of budget used)"
            )

    else:

        budget_percentage = 0
        remaining = 0
        budget_status = "No monthly budget set"

    # ============================================================
    # DATA SUMMARY FOR AI
    # ============================================================

    financial_data = {
        "total_spending": total,
        "this_month": monthly_total,
        "previous_month": previous_month_total,
        "monthly_budget": budget_amount,
        "budget_used_percentage": round(budget_percentage, 1),
        "budget_remaining": round(remaining, 2),
        "highest_category": highest_category,
        "trend": trend,
        "categories": categories
    }

    # ============================================================
    # AI RECOMMENDATION + SUMMARY
    # ============================================================

    prompt = f"""
You are the AI assistant for SmartExpenseTracker.

Analyze ONLY the financial data provided below.

FINANCIAL DATA:

{json.dumps(financial_data, indent=2)}

The application has already calculated the highest category,
spending trend and budget status.

Do NOT change or contradict those calculations.

Generate:

1. One practical recommendation based on the user's actual spending.
2. A short personalized financial summary based only on the data.

Do not provide investment advice.
Do not invent expenses.
Do not invent categories.
Do not invent a budget.
Do not mention information that is not present in the data.

Return JSON with exactly:

{{
    "recommendation": "string",
    "summary": "string"
}}
"""

    recommendation = (
        "Continue tracking your expenses and review your "
        "highest spending category regularly."
    )

    summary = (
        f"You have spent ₹{monthly_total:.2f} this month. "
        f"Your highest spending category is {highest_category}. "
        f"Your spending trend is {trend}. "
        f"Your budget status is {budget_status}."
    )

    try:

        response = client.responses.create(

            model="gpt-5.6-luna",

            input=prompt,

            text={
                "format": {
                    "type": "json_schema",
                    "name": "spending_recommendation",
                    "strict": True,

                    "schema": {

                        "type": "object",

                        "properties": {

                            "recommendation": {
                                "type": "string"
                            },

                            "summary": {
                                "type": "string"
                            }

                        },

                        "required": [
                            "recommendation",
                            "summary"
                        ],

                        "additionalProperties": False
                    }
                }
            }
        )

        ai_result = json.loads(
            response.output_text
        )

        recommendation = ai_result.get(
            "recommendation",
            recommendation
        )

        summary = ai_result.get(
            "summary",
            summary
        )

    except Exception as error:

        print("AI Recommendation Error:", error)

    # ============================================================
    # FINAL RESULT
    # ============================================================

    return {

        "category": highest_category,

        "trend": trend,

        "budget_status": budget_status,

        "recommendation": recommendation,

        "summary": summary
    }