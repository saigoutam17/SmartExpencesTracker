import sqlite3
import os

import psycopg2
from dotenv import load_dotenv


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


# ---------------- SQLITE ----------------

sqlite_connection = sqlite3.connect(
    "expenses.db"
)

sqlite_connection.row_factory = sqlite3.Row

sqlite_cursor = sqlite_connection.cursor()


# ---------------- POSTGRESQL ----------------

postgres_connection = psycopg2.connect(
    DATABASE_URL
)

postgres_cursor = postgres_connection.cursor()


# ---------------- EXPENSES ----------------

sqlite_cursor.execute(
    "SELECT * FROM expenses"
)

expenses = sqlite_cursor.fetchall()


print(
    f"Found {len(expenses)} expenses."
)


for expense in expenses:

    postgres_cursor.execute(
        """
        INSERT INTO expenses
        (
            id,
            amount,
            category,
            description,
            date
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,

        (
            expense["id"],
            expense["amount"],
            expense["category"],
            expense["description"],
            expense["date"]
        )
    )


# ---------------- BUDGET ----------------

sqlite_cursor.execute(
    "SELECT * FROM budget"
)

budgets = sqlite_cursor.fetchall()


for budget in budgets:

    postgres_cursor.execute(
        """
        INSERT INTO budget
        (
            id,
            amount
        )
        VALUES (%s, %s)

        ON CONFLICT (id)
        DO UPDATE SET
            amount = EXCLUDED.amount
        """,

        (
            budget["id"],
            budget["amount"]
        )
    )


# ---------------- COMMIT ----------------

postgres_connection.commit()


# ---------------- CLOSE ----------------

sqlite_cursor.close()
sqlite_connection.close()

postgres_cursor.close()
postgres_connection.close()


print("✅ Migration completed successfully!")