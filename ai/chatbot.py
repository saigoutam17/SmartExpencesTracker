from openai import OpenAI

client = OpenAI()


def ask_financial_ai(question, financial_data):

    try:

        prompt = f"""
You are an AI assistant for a personal expense tracker.

Answer the user's question using ONLY the financial
data provided below.

FINANCIAL DATA:

{financial_data}

USER QUESTION:

{question}

Rules:

1. Be concise and easy to understand.
2. Use ₹ for money.
3. Do not invent numbers.
4. If the requested information is not available,
   clearly say that it is not available.
5. Do not provide investment or financial-market advice.
"""


        response = client.responses.create(

            model="gpt-5.6-luna",

            input=prompt
        )


        return response.output_text.strip()


    except Exception as error:

        print("AI Chatbot Error:", error)

        return (
            "Sorry, the AI assistant is currently "
            "unavailable."
        )