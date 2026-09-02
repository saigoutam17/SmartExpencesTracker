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

    try:

        categories = []

        for category in category_totals:

            categories.append({
                "category": category["category"],
                "total": float(category["total"])
            })


        prompt = f"""
You are a personal expense analysis assistant.

Analyze the following user's financial spending data.

Total spending:
₹{total}

This month's spending:
₹{monthly_total}

Previous month's spending:
₹{previous_month_total}

Monthly budget:
₹{budget_amount}

Spending by category:
{json.dumps(categories)}


Provide a concise analysis.

Identify:

1. Highest spending category
2. Whether spending increased or decreased
3. Budget situation
4. One practical recommendation

Do not provide investment advice.

Return JSON with:

category
trend
budget_status
recommendation
summary
"""


        response = client.responses.create(

            model="gpt-5.6-luna",

            input=prompt,

            text={
                "format": {
                    "type": "json_schema",

                    "name": "spending_analysis",

                    "strict": True,

                    "schema": {

                        "type": "object",

                        "properties": {

                            "category": {
                                "type": "string"
                            },

                            "trend": {
                                "type": "string"
                            },

                            "budget_status": {
                                "type": "string"
                            },

                            "recommendation": {
                                "type": "string"
                            },

                            "summary": {
                                "type": "string"
                            }

                        },

                        "required": [
                            "category",
                            "trend",
                            "budget_status",
                            "recommendation",
                            "summary"
                        ],

                        "additionalProperties": False
                    }
                }
            }
        )


        return json.loads(
            response.output_text
        )


    except Exception as error:

        print("AI Analyst Error:", error)

        return {
            "category": "Unknown",
            "trend": "Unable to determine",
            "budget_status": "Unable to determine",
            "recommendation": "Continue tracking your expenses.",
            "summary": "AI analysis is currently unavailable."
        }