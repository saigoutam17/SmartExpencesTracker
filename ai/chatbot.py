import os
from openai import OpenAI


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def ask_financial_ai(question, financial_data):

    try:

        prompt = f"""
You are SmartExpense AI, a personal financial assistant.

Answer the user's question using the financial information provided below.

USER QUESTION:
{question}

USER FINANCIAL DATA:
{financial_data}

Rules:
- Answer the question directly.
- Use the user's actual financial data.
- Do not invent expenses, amounts, categories, or budgets.
- If the requested information is not available, clearly say so.
- Give simple, helpful answers.
- Use ₹ for Indian currency when discussing amounts.
- If the user asks for advice, base it on their actual spending.
"""

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt
        )

        return response.output_text

    except Exception as e:

        print("AI CHATBOT ERROR:", e)

        return "Sorry, the AI assistant is currently unavailable."