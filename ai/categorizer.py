from openai import OpenAI
import json


client = OpenAI()


# ------------------------------------------------
# LOCAL FALLBACK
# ------------------------------------------------

def local_category(description):

    description = description.lower().strip()


    food_words = [
        "food",
        "lunch",
        "dinner",
        "breakfast",
        "restaurant",
        "pizza",
        "burger",
        "kfc",
        "swiggy",
        "zomato",
        "coffee",
        "tea"
    ]

    for word in food_words:

        if word in description:

            return {
                "category": "Food",
                "confidence": 0.70,
                "reason": "Local fallback detected a food-related keyword."
            }


    travel_words = [
        "uber",
        "ola",
        "taxi",
        "bus",
        "train",
        "flight",
        "metro",
        "travel",
        "fuel",
        "petrol",
        "diesel"
    ]

    for word in travel_words:

        if word in description:

            return {
                "category": "Travel",
                "confidence": 0.70,
                "reason": "Local fallback detected a travel-related keyword."
            }


    shopping_words = [
        "amazon",
        "flipkart",
        "shopping",
        "clothes",
        "shirt",
        "shoes",
        "mall",
        "purchase"
    ]

    for word in shopping_words:

        if word in description:

            return {
                "category": "Shopping",
                "confidence": 0.70,
                "reason": "Local fallback detected a shopping-related keyword."
            }


    bill_words = [
        "electricity",
        "water bill",
        "internet",
        "wifi",
        "recharge",
        "bill",
        "rent"
    ]

    for word in bill_words:

        if word in description:

            return {
                "category": "Bills",
                "confidence": 0.70,
                "reason": "Local fallback detected a bill-related keyword."
            }


    education_words = [
        "book",
        "course",
        "college",
        "school",
        "education",
        "udemy",
        "coursera",
        "exam"
    ]

    for word in education_words:

        if word in description:

            return {
                "category": "Education",
                "confidence": 0.70,
                "reason": "Local fallback detected an education-related keyword."
            }


    return {
        "category": "Other",
        "confidence": 0.40,
        "reason": "No clear category was detected."
    }
def suggest_category(description, expense_history=None):

    if expense_history is None:
        expense_history = []

    try:

        history_text = ""

        for expense in expense_history:

            history_text += (
                f"- {expense['description']} "
                f"→ {expense['category']} "
                f"(₹{expense['amount']})\n"
            )


        prompt = f"""
You are a personalized expense categorization assistant.

Analyze this new expense:

"{description}"

Previous expenses from this user:

{history_text}

Choose exactly ONE category:

Food
Travel
Shopping
Bills
Education
Other

Use the previous expenses when they are relevant.

Return:
- category
- confidence from 0 to 1
- short reason
"""


        response = client.responses.create(

            model="gpt-5.6-luna",

            input=prompt,

            text={
                "format": {
                    "type": "json_schema",

                    "name": "expense_category",

                    "strict": True,

                    "schema": {

                        "type": "object",

                        "properties": {

                            "category": {
                                "type": "string",
                                "enum": [
                                    "Food",
                                    "Travel",
                                    "Shopping",
                                    "Bills",
                                    "Education",
                                    "Other"
                                ]
                            },

                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1
                            },

                            "reason": {
                                "type": "string"
                            }

                        },

                        "required": [
                            "category",
                            "confidence",
                            "reason"
                        ],

                        "additionalProperties": False
                    }
                }
            }
        )


        result = json.loads(
            response.output_text
        )

        return result


    except Exception as error:

        print("AI Error:", error)

        return local_category(description)