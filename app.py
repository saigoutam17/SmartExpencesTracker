from flask import (
    Flask,
    render_template,
    request,
    redirect,
    jsonify,
    session
)
import os
from flask import request, render_template
from werkzeug.utils import secure_filename

from ai.receipt import extract_receipt
from functools import wraps

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

import os

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

from ai.categorizer import suggest_category
from ai.analyst import analyze_spending
from ai.chatbot import ask_financial_ai


# ============================================================
# APP CONFIG
# ============================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "SmartExpenseTracker@2026"
)

DATABASE_URL = os.getenv("DATABASE_URL")


# ============================================================
# DATABASE
# ============================================================

def get_db_connection():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


# ============================================================
# USER SETTINGS HELPER
# ============================================================

def get_user_settings(user_id):

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM user_settings
        WHERE user_id = %s
        """,
        (user_id,)
    )

    settings = cursor.fetchone()

    cursor.close()
    connection.close()

    return settings

def currency_symbol(currency):
    symbols = {
        "INR": "₹",
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥"
    }

    return symbols.get(currency, "₹")
@app.context_processor
def inject_user_settings():

    if "user_id" not in session:
        return {
            "settings": None,
            "currency_symbol": "₹"
        }

    try:
        settings = get_user_settings(session["user_id"])

        currency = settings.get("currency", "INR")

        return {
            "settings": settings,
            "currency_symbol": currency_symbol(currency)
        }

    except Exception:
        return {
            "settings": None,
            "currency_symbol": "₹"
        }
# ============================================================
# LOGIN REQUIRED
# ============================================================

def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if "user_id" not in session:
            return redirect("/login")

        return view(*args, **kwargs)

    return wrapped_view


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not username or not email or not password:
        return "All fields are required", 400

    if len(password) < 6:
        return "Password must contain at least 6 characters", 400

    password_hash = generate_password_hash(password)

    connection = get_db_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO users
            (
                username,
                email,
                password_hash
            )
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (
                username,
                email,
                password_hash
            )
        )

        user = cursor.fetchone()

        # Assign old migrated expenses
        cursor.execute(
            """
            UPDATE expenses
            SET user_id = %s
            WHERE user_id IS NULL
            """,
            (user["id"],)
        )

        # Create default settings
        cursor.execute(
            """
            INSERT INTO user_settings
            (
                user_id
            )
            VALUES (%s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user["id"],)
        )

        connection.commit()

    except Exception as error:

        connection.rollback()

        print("REGISTER ERROR:", error)

        cursor.close()
        connection.close()

        return "Username or email may already exist", 400

    cursor.close()
    connection.close()

    session["user_id"] = user["id"]
    session["username"] = username

    return redirect("/")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            username,
            password_hash
        FROM users
        WHERE email = %s
        """,
        (email,)
    )

    user = cursor.fetchone()

    cursor.close()
    connection.close()

    if user is None:
        return "Invalid email or password", 401

    if not check_password_hash(
        user["password_hash"],
        password
    ):
        return "Invalid email or password", 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return redirect("/")


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    connection = get_db_connection()
    cursor = connection.cursor()

    # USERS
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )

    # EXPENSES
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            amount NUMERIC NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            date DATE NOT NULL,
            user_id BIGINT
        )
        """
    )

    cursor.execute(
        """
        ALTER TABLE expenses
        ADD COLUMN IF NOT EXISTS user_id BIGINT
        """
    )

    # BUDGET
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS budget (
            id BIGINT PRIMARY KEY,
            amount NUMERIC NOT NULL
        )
        """
    )

    # USER SETTINGS
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id BIGINT PRIMARY KEY,

            currency TEXT DEFAULT 'INR',

            theme TEXT DEFAULT 'system',

            ai_enabled BOOLEAN DEFAULT TRUE,

            ai_categorization BOOLEAN DEFAULT TRUE,

            ai_analysis BOOLEAN DEFAULT TRUE,

            ai_chatbot BOOLEAN DEFAULT TRUE,

            budget_alerts BOOLEAN DEFAULT TRUE,

            weekly_summary BOOLEAN DEFAULT TRUE,

            monthly_report BOOLEAN DEFAULT TRUE,

            ai_history_enabled BOOLEAN DEFAULT TRUE,

            created_at TIMESTAMPTZ DEFAULT NOW(),

            updated_at TIMESTAMPTZ DEFAULT NOW(),

            CONSTRAINT user_settings_user_fk
                FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )

    connection.commit()

    cursor.close()
    connection.close()


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
@login_required
def home():

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    search = request.args.get("search", "")
    category_filter = request.args.get("category", "")
    date_filter = request.args.get("date_filter", "")

    query = """
        SELECT *
        FROM expenses
        WHERE user_id = %s
    """

    parameters = [user_id]

    if search:

        query += """
            AND (
                description ILIKE %s
                OR category ILIKE %s
            )
        """

        parameters.extend([
            "%" + search + "%",
            "%" + search + "%"
        ])

    if category_filter:

        query += """
            AND category = %s
        """

        parameters.append(category_filter)

    if date_filter == "this_month":

        query += """
            AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC('month', CURRENT_DATE)
        """

    elif date_filter == "last_month":

        query += """
            AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC(
                'month',
                CURRENT_DATE - INTERVAL '1 month'
            )
        """

    query += """
        ORDER BY date DESC
    """

    cursor.execute(query, parameters)

    expenses = cursor.fetchall()

    # TOTAL
    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        """,
        (user_id,)
    )

    total = cursor.fetchone()["total"]

    # THIS MONTH
    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC('month', CURRENT_DATE)
        """,
        (user_id,)
    )

    monthly_total = cursor.fetchone()["total"]

    # PREVIOUS MONTH
    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC(
                'month',
                CURRENT_DATE - INTERVAL '1 month'
            )
        """,
        (user_id,)
    )

    previous_month_total = cursor.fetchone()["total"]

    # CATEGORY TOTALS
    cursor.execute(
        """
        SELECT
            category,
            SUM(amount) AS total
        FROM expenses
        WHERE user_id = %s
        GROUP BY category
        ORDER BY total DESC
        """,
        (user_id,)
    )

    category_totals = cursor.fetchall()

    # BUDGET
    cursor.execute(
        """
        SELECT amount
        FROM budget
        WHERE id = %s
        """,
        (user_id,)
    )

    budget = cursor.fetchone()

    cursor.close()
    connection.close()

    total = total or 0
    monthly_total = monthly_total or 0
    previous_month_total = previous_month_total or 0

    if previous_month_total > 0:

        percentage_change = (
            (
                monthly_total -
                previous_month_total
            )
            / previous_month_total
        ) * 100

    else:

        percentage_change = 0

    if budget:

        budget_amount = budget["amount"]

    else:

        budget_amount = 0

    category_labels = [
        row["category"]
        for row in category_totals
    ]

    category_values = [
        float(row["total"])
        for row in category_totals
    ]

    insights = []

    if category_totals:

        highest_category = max(
            category_totals,
            key=lambda x: x["total"]
        )

        insights.append(
            f"💡 Your highest spending category is "
            f"{highest_category['category']} "
            f"with ₹{highest_category['total']:.2f}."
        )

    if budget_amount > 0:

        percentage = (
            monthly_total /
            budget_amount
        ) * 100

        if percentage >= 100:

            insights.append(
                "🔴 You have exceeded your monthly budget!"
            )

        elif percentage >= 80:

            insights.append(
                f"⚠️ You have used {percentage:.1f}% "
                "of your monthly budget."
            )

        elif percentage >= 50:

            insights.append(
                f"🟡 You have used {percentage:.1f}% "
                "of your monthly budget."
            )

        else:

            insights.append(
                "🟢 Your spending is currently "
                "within your budget."
            )

    else:

        insights.append(
            "💵 Set a monthly budget to receive "
            "budget insights."
        )

    return render_template(
        "index.html",

        expenses=expenses,

        total=total,

        monthly_total=monthly_total,

        previous_month_total=previous_month_total,

        percentage_change=percentage_change,

        category_totals=category_totals,

        category_labels=category_labels,

        category_values=category_values,

        budget_amount=budget_amount,

        insights=insights,

        search=search,

        category_filter=category_filter,

        date_filter=date_filter,

        username=session.get("username")
    )


# ============================================================
# EXPENSES PAGE
# ============================================================
@app.route("/expenses")
@login_required
def expenses_page():

    search = request.args.get("search", "").strip()
    category_filter = request.args.get("category", "").strip()
    date_filter = request.args.get("date_filter", "").strip()

    connection = get_db_connection()
    cursor = connection.cursor()

    query = """
        SELECT *
        FROM expenses
        WHERE user_id = %s
    """

    params = [session["user_id"]]

    if search:
        query += """
            AND (
                description ILIKE %s
                OR category ILIKE %s
            )
        """
        search_value = f"%{search}%"
        params.extend([search_value, search_value])

    if category_filter:
        query += " AND category = %s"
        params.append(category_filter)

    if date_filter == "this_month":
        query += """
            AND date >= DATE_TRUNC('month', CURRENT_DATE)
            AND date < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
        """

    elif date_filter == "last_month":
        query += """
            AND date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'
            AND date < DATE_TRUNC('month', CURRENT_DATE)
        """

    query += " ORDER BY date DESC, id DESC"

    cursor.execute(query, tuple(params))
    expenses = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "expenses.html",
        expenses=expenses,
        search=search,
        category_filter=category_filter,
        date_filter=date_filter
    )

# ============================================================
# BUDGET
# ============================================================

@app.route("/budget")
@login_required
def budget_page():

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT amount
        FROM budget
        WHERE id = %s
        """,
        (user_id,)
    )

    budget = cursor.fetchone()

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC('month', CURRENT_DATE)
        """,
        (user_id,)
    )

    monthly_total = cursor.fetchone()["total"]

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        """,
        (user_id,)
    )

    total = cursor.fetchone()["total"]

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC(
                'month',
                CURRENT_DATE - INTERVAL '1 month'
            )
        """,
        (user_id,)
    )

    previous_month_total = cursor.fetchone()["total"]

    cursor.close()
    connection.close()

    budget_amount = budget["amount"] if budget else 0

    if budget_amount > 0:

        percentage = (
            monthly_total /
            budget_amount
        ) * 100

    else:

        percentage = 0

    remaining = budget_amount - monthly_total

    return render_template(
        "budget.html",

        budget_amount=budget_amount,

        monthly_total=monthly_total,

        previous_month_total=previous_month_total,

        total=total,

        percentage=percentage,

        remaining=remaining,

        username=session.get("username")
    )


# ============================================================
# ANALYTICS
# ============================================================

@app.route("/analytics")
@login_required
def analytics():

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        """,
        (user_id,)
    )

    total = cursor.fetchone()["total"]

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC('month', CURRENT_DATE)
        """,
        (user_id,)
    )

    monthly_total = cursor.fetchone()["total"]

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC(
                'month',
                CURRENT_DATE - INTERVAL '1 month'
            )
        """,
        (user_id,)
    )

    previous_month_total = cursor.fetchone()["total"]

    cursor.execute(
        """
        SELECT
            category,
            SUM(amount) AS total
        FROM expenses
        WHERE user_id = %s
        GROUP BY category
        ORDER BY total DESC
        """,
        (user_id,)
    )

    category_totals = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            TO_CHAR(date, 'YYYY-MM') AS month,
            SUM(amount) AS total
        FROM expenses
        WHERE user_id = %s
        GROUP BY TO_CHAR(date, 'YYYY-MM')
        ORDER BY month
        """,
        (user_id,)
    )

    monthly_totals = cursor.fetchall()

    cursor.execute(
        """
        SELECT amount
        FROM budget
        WHERE id = %s
        """,
        (user_id,)
    )

    budget = cursor.fetchone()

    cursor.close()
    connection.close()

    total = total or 0
    monthly_total = monthly_total or 0
    previous_month_total = previous_month_total or 0

    budget_amount = budget["amount"] if budget else 0

    if previous_month_total > 0:

        percentage_change = (
            (
                monthly_total -
                previous_month_total
            )
            / previous_month_total
        ) * 100

    else:

        percentage_change = 0

    if budget_amount > 0:

        budget_percentage = (
            monthly_total /
            budget_amount
        ) * 100

    else:

        budget_percentage = 0

    remaining_budget = (
        budget_amount -
        monthly_total
    )

    category_labels = [
        row["category"]
        for row in category_totals
    ]

    category_values = [
        float(row["total"])
        for row in category_totals
    ]

    monthly_labels = [
        row["month"]
        for row in monthly_totals
    ]

    monthly_values = [
        float(row["total"])
        for row in monthly_totals
    ]

    if category_totals:

        highest_category = category_totals[0]["category"]

        highest_category_amount = (
            category_totals[0]["total"]
        )

    else:

        highest_category = "None"

        highest_category_amount = 0

    return render_template(
        "analytics.html",

        username=session.get("username"),

        total=total,

        monthly_total=monthly_total,

        previous_month_total=previous_month_total,

        percentage_change=percentage_change,

        budget_amount=budget_amount,

        budget_percentage=budget_percentage,

        remaining_budget=remaining_budget,

        category_totals=category_totals,

        category_labels=category_labels,

        category_values=category_values,

        monthly_totals=monthly_totals,

        monthly_labels=monthly_labels,

        monthly_values=monthly_values,

        highest_category=highest_category,

        highest_category_amount=highest_category_amount
    )

# ============================================================
# SETTINGS
# ============================================================

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    try:

        # ------------------------------------------------
        # SAVE SETTINGS
        # ------------------------------------------------

        if request.method == "POST":

            currency = request.form.get("currency", "INR")
            theme = request.form.get("theme", "system")

            ai_enabled = request.form.get("ai_enabled") == "on"
            ai_categorization = request.form.get("ai_categorization") == "on"
            ai_analysis = request.form.get("ai_analysis") == "on"
            ai_chatbot = request.form.get("ai_chatbot") == "on"

            budget_alerts = request.form.get("budget_alerts") == "on"
            weekly_summary = request.form.get("weekly_summary") == "on"
            monthly_report = request.form.get("monthly_report") == "on"

            ai_history_enabled = (
                request.form.get("ai_history_enabled") == "on"
            )

            cursor.execute(
                """
                INSERT INTO user_settings (
                    user_id,
                    currency,
                    theme,
                    ai_enabled,
                    ai_categorization,
                    ai_analysis,
                    ai_chatbot,
                    budget_alerts,
                    weekly_summary,
                    monthly_report,
                    ai_history_enabled,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, NOW()
                )
                ON CONFLICT (user_id)
                DO UPDATE SET
                    currency = EXCLUDED.currency,
                    theme = EXCLUDED.theme,
                    ai_enabled = EXCLUDED.ai_enabled,
                    ai_categorization = EXCLUDED.ai_categorization,
                    ai_analysis = EXCLUDED.ai_analysis,
                    ai_chatbot = EXCLUDED.ai_chatbot,
                    budget_alerts = EXCLUDED.budget_alerts,
                    weekly_summary = EXCLUDED.weekly_summary,
                    monthly_report = EXCLUDED.monthly_report,
                    ai_history_enabled = EXCLUDED.ai_history_enabled,
                    updated_at = NOW()
                """,
                (
                    user_id,
                    currency,
                    theme,
                    ai_enabled,
                    ai_categorization,
                    ai_analysis,
                    ai_chatbot,
                    budget_alerts,
                    weekly_summary,
                    monthly_report,
                    ai_history_enabled
                )
            )

            connection.commit()

            return redirect("/settings")

        # ------------------------------------------------
        # GET SETTINGS
        # ------------------------------------------------

        cursor.execute(
            """
            SELECT *
            FROM user_settings
            WHERE user_id = %s
            """,
            (user_id,)
        )

        user_settings = cursor.fetchone()

        # ------------------------------------------------
        # CREATE DEFAULT SETTINGS IF MISSING
        # ------------------------------------------------

        if user_settings is None:

            cursor.execute(
                """
                INSERT INTO user_settings (user_id)
                VALUES (%s)
                RETURNING *
                """,
                (user_id,)
            )

            user_settings = cursor.fetchone()

            connection.commit()

        return render_template(
            "settings.html",
            settings=user_settings,
            username=session.get("username")
        )

    except Exception as error:

        connection.rollback()

        print("SETTINGS ERROR:", error)

        return "Settings error. Check terminal.", 500

    finally:

        cursor.close()
        connection.close()

@app.route("/profile")
@login_required
def profile():
    return render_template(
        "profile.html",
        username=session.get("username"),
        user_id=session.get("user_id")
    )
# ============================================================
# AI CATEGORY
# ============================================================

@app.route(
    "/suggest-category",
    methods=["POST"]
)
@login_required
def suggest_expense_category():

    user_settings = get_user_settings(
        session["user_id"]
    )

    if user_settings:

        if not user_settings["ai_enabled"]:

            return jsonify({
                "error":
                    "AI features are disabled in Settings."
            }), 403

        if not user_settings["ai_categorization"]:

            return jsonify({
                "error":
                    "AI categorization is disabled in Settings."
            }), 403

    description = request.form.get(
        "description",
        ""
    )

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            description,
            category,
            amount
        FROM expenses

        WHERE user_id = %s

        AND description IS NOT NULL

        ORDER BY id DESC

        LIMIT 20
        """,
        (session["user_id"],)
    )

    previous_expenses = cursor.fetchall()

    cursor.close()
    connection.close()

    expense_history = [

        {
            "description":
                expense["description"],

            "category":
                expense["category"],

            "amount":
                expense["amount"]
        }

        for expense in previous_expenses
    ]

    result = suggest_category(
        description,
        expense_history
    )

    return jsonify({

        "category":
            result["category"],

        "confidence":
            result["confidence"],

        "reason":
            result["reason"]
    })


# ============================================================
# AI ANALYSIS
# ============================================================
@app.route("/ai-analysis")
@login_required
def ai_analysis():

    user_settings = get_user_settings(
        session["user_id"]
    )

    if user_settings:

        if not user_settings["ai_enabled"]:
            return (
                "AI features are disabled in Settings.",
                403
            )

        if not user_settings["ai_analysis"]:
            return (
                "AI spending analysis is disabled in Settings.",
                403
            )

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
    """, (user_id,))

    total = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC('month', CURRENT_DATE)
    """, (user_id,))

    monthly_total = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC(
                'month',
                CURRENT_DATE - INTERVAL '1 month'
            )
    """, (user_id,))

    previous_month_total = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT
            category,
            SUM(amount) AS total
        FROM expenses
        WHERE user_id = %s
        GROUP BY category
        ORDER BY total DESC
    """, (user_id,))

    category_totals = cursor.fetchall()

    cursor.execute("""
        SELECT amount
        FROM budget
        WHERE id = %s
    """, (user_id,))

    budget = cursor.fetchone()

    cursor.close()
    connection.close()

    budget_amount = (
        budget["amount"]
        if budget
        else 0
    )

    analysis = analyze_spending(
        total,
        monthly_total,
        previous_month_total,
        category_totals,
        budget_amount
    )

    return render_template(
        "ai-analysis.html",
        analysis=analysis
    )
@app.route("/chat",methods=["GET", "POST"])
@login_required
def assistant():

    if request.method == "GET":
        return render_template("chat.html")

    user_settings = get_user_settings(
        session["user_id"]
    )

    if user_settings:

        if not user_settings["ai_enabled"]:
            return jsonify({
                "error":
                "AI features are disabled in Settings."
            }), 403

        if not user_settings["ai_chatbot"]:
            return jsonify({
                "error":
                "AI chatbot is disabled in Settings."
            }), 403

    question = request.form.get(
        "question",
        ""
    ).strip()

    if not question:
        return jsonify({
            "answer":
            "Please enter a question."
        })

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    # TOTAL SPENDING
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
    """, (user_id,))

    total = cursor.fetchone()["total"]

    # THIS MONTH
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = %s
        AND DATE_TRUNC('month', date)
            =
            DATE_TRUNC('month', CURRENT_DATE)
    """, (user_id,))

    monthly_total = cursor.fetchone()["total"]

    # CATEGORIES
    cursor.execute("""
        SELECT
            category,
            SUM(amount) AS total
        FROM expenses
        WHERE user_id = %s
        GROUP BY category
        ORDER BY total DESC
    """, (user_id,))

    category_totals = cursor.fetchall()

    # RECENT EXPENSES
    cursor.execute("""
        SELECT
            date,
            category,
            description,
            amount
        FROM expenses
        WHERE user_id = %s
        ORDER BY date DESC, id DESC
        LIMIT 20
    """, (user_id,))

    recent_expenses = cursor.fetchall()

    # BUDGET
    cursor.execute("""
        SELECT amount
        FROM budget
        WHERE id = %s
    """, (user_id,))

    budget = cursor.fetchone()

    cursor.close()
    connection.close()

    budget_amount = (
        budget["amount"]
        if budget
        else 0
    )

    financial_data = {

        "total_spending":
            float(total),

        "this_month":
            float(monthly_total),

        "monthly_budget":
            float(budget_amount),

        "categories": [
            {
                "category":
                    row["category"],

                "total":
                    float(row["total"])
            }

            for row in category_totals
        ],

        "recent_expenses": [
            {
                "date":
                    str(row["date"]),

                "category":
                    row["category"],

                "description":
                    row["description"],

                "amount":
                    float(row["amount"])
            }

            for row in recent_expenses
        ]
    }

    answer = ask_financial_ai(
        question,
        financial_data
    )

    return jsonify({
        "answer": answer
    })
# ============================================================
# ADD EXPENSE
# ============================================================

@app.route(
    "/add",
    methods=["POST"]
)
@login_required
def add_expense():

    amount = request.form["amount"]
    category = request.form["category"]
    description = request.form["description"]
    date = request.form["date"]

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO expenses
        (
            amount,
            category,
            description,
            date,
            user_id
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            amount,
            category,
            description,
            date,
            session["user_id"]
        )
    )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect("/")


# ============================================================
# DELETE EXPENSE
# ============================================================

@app.route(
    "/delete/<int:id>"
)
@login_required
def delete_expense(id):

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM expenses
        WHERE id = %s
        AND user_id = %s
        """,
        (
            id,
            session["user_id"]
        )
    )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect("/")


# ============================================================
# EDIT EXPENSE
# ============================================================

@app.route(
    "/edit/<int:id>",
    methods=["GET", "POST"]
)
@login_required
def edit_expense(id):

    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == "POST":

        amount = request.form["amount"]
        category = request.form["category"]
        description = request.form["description"]
        date = request.form["date"]

        cursor.execute(
            """
            UPDATE expenses

            SET
                amount = %s,
                category = %s,
                description = %s,
                date = %s

            WHERE id = %s

            AND user_id = %s
            """,
            (
                amount,
                category,
                description,
                date,
                id,
                session["user_id"]
            )
        )

        connection.commit()

        cursor.close()
        connection.close()

        return redirect("/")

    cursor.execute(
        """
        SELECT *
        FROM expenses
        WHERE id = %s
        AND user_id = %s
        """,
        (
            id,
            session["user_id"]
        )
    )

    expense = cursor.fetchone()

    cursor.close()
    connection.close()

    if expense is None:

        return "Expense not found", 404

    return render_template(
        "edit.html",
        expense=expense
    )


# ============================================================
# SET BUDGET
# ============================================================

@app.route(
    "/set-budget",
    methods=["POST"]
)
@login_required
def set_budget():

    budget_amount = request.form["budget"]

    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
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
            user_id,
            budget_amount
        )
    )

    connection.commit()

    cursor.close()
    connection.close()

    return redirect("/")


# ============================================================
# API - GET ALL EXPENSES
# ============================================================

@app.route(
    "/api/expenses",
    methods=["GET"]
)
@login_required
def api_get_expenses():

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            amount,
            category,
            description,
            date
        FROM expenses
        WHERE user_id = %s
        ORDER BY date DESC
        """,
        (session["user_id"],)
    )

    expenses = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify([

        {
            "id":
                expense["id"],

            "amount":
                float(expense["amount"]),

            "category":
                expense["category"],

            "description":
                expense["description"],

            "date":
                str(expense["date"])
        }

        for expense in expenses
    ])


# ============================================================
# API - GET ONE
# ============================================================

@app.route(
    "/api/expenses/<int:id>",
    methods=["GET"]
)
@login_required
def api_get_expense(id):

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            amount,
            category,
            description,
            date
        FROM expenses

        WHERE id = %s

        AND user_id = %s
        """,
        (
            id,
            session["user_id"]
        )
    )

    expense = cursor.fetchone()

    cursor.close()
    connection.close()

    if expense is None:

        return jsonify({
            "error":
                "Expense not found"
        }), 404

    return jsonify({

        "id":
            expense["id"],

        "amount":
            float(expense["amount"]),

        "category":
            expense["category"],

        "description":
            expense["description"],

        "date":
            str(expense["date"])
    })


# ============================================================
# API - CREATE
# ============================================================

@app.route(
    "/api/expenses",
    methods=["POST"]
)
@login_required
def api_create_expense():

    data = request.get_json()

    if not data:

        return jsonify({
            "error":
                "JSON data required"
        }), 400

    amount = data.get("amount")
    category = data.get("category")
    description = data.get("description", "")
    date = data.get("date")

    if amount is None or not category or not date:

        return jsonify({
            "error":
                "amount, category and date are required"
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO expenses
        (
            amount,
            category,
            description,
            date,
            user_id
        )
        VALUES (%s, %s, %s, %s, %s)

        RETURNING id
        """,
        (
            amount,
            category,
            description,
            date,
            session["user_id"]
        )
    )

    expense_id = cursor.fetchone()["id"]

    connection.commit()

    cursor.close()
    connection.close()

    return jsonify({

        "message":
            "Expense created successfully",

        "id":
            expense_id

    }), 201
@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_server_error(error):
    return render_template("500.html"), 500
@app.route("/scan-receipt", methods=["GET", "POST"])
@login_required
def scan_receipt():

    if request.method == "GET":
        return render_template("scan_receipt.html")

    if "receipt" not in request.files:
        return render_template(
            "scan_receipt.html",
            error="Please select a receipt image."
        )

    file = request.files["receipt"]

    if file.filename == "":
        return render_template(
            "scan_receipt.html",
            error="Please select a receipt image."
        )

    upload_folder = "uploads"
    os.makedirs(upload_folder, exist_ok=True)

    filename = secure_filename(file.filename)
    file_path = os.path.join(upload_folder, filename)

    file.save(file_path)

    try:
        result = extract_receipt(file_path)

        return render_template(
            "scan_receipt.html",
            result=result
        )

    except Exception as e:
        print("RECEIPT SCANNER ERROR:", e)

        return render_template(
            "scan_receipt.html",
            error="Unable to scan the receipt."
        )

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
# ============================================================
# START APP
# ============================================================
if __name__ == "__main__":
    init_db()

    import os

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )