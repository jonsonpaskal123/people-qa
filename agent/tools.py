# agent/tools.py
import os
import logging
import pymysql
from langchain_core.tools import tool

log = logging.getLogger(__name__)

SR_HOST     = os.getenv("SR_HOST",     "starrocks")
SR_PORT     = int(os.getenv("SR_PORT", "9030"))
SR_USER     = os.getenv("SR_USER",     "readonly_user")
SR_PASSWORD = os.getenv("SR_PASSWORD", "ReadOnly@123")
SR_DATABASE = os.getenv("SR_DATABASE", "people_db")

FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP",
    "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE"
]


def _get_conn():
    return pymysql.connect(
        host=SR_HOST,
        port=SR_PORT,
        user=SR_USER,
        password=SR_PASSWORD,
        database=SR_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


def _is_safe(query: str) -> tuple[bool, str]:
    """چک می‌کنه کوئری safe هست یا نه"""
    q = query.strip().upper()
    for kw in FORBIDDEN_KEYWORDS:
        if kw in q:
            return False, kw
    if not (q.startswith("SELECT") or q.startswith("SHOW")):
        return False, "NOT_SELECT"
    return True, ""


@tool
def execute_sql(query: str) -> str:
    """
    اجرای کوئری SQL روی پایگاه داده StarRocks.
    فقط کوئری‌های SELECT مجاز هستند.

    Args:
        query: کوئری SQL

    Returns:
        نتیجه کوئری به صورت متن
    """
    # بررسی امنیت
    safe, reason = _is_safe(query)
    if not safe:
        return f"❌ کوئری غیرمجاز: عملیات '{reason}' اجازه داده نمی‌شود."

    log.info(f"🔍 SQL: {query}")

    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
        conn.close()

        if not rows:
            return "نتیجه‌ای یافت نشد."

        # یک مقدار ساده
        if len(rows) == 1 and len(rows[0]) == 1:
            val = list(rows[0].values())[0]
            return str(val)

        # جدول
        headers = list(rows[0].keys())
        lines   = [" | ".join(str(h) for h in headers)]
        lines.append("-" * (len(lines[0]) + 10))

        for row in rows[:50]:
            lines.append(" | ".join(str(v) if v is not None else "-" for v in row.values()))

        result = "\n".join(lines)

        if len(rows) > 50:
            result += f"\n\n... و {len(rows) - 50} ردیف دیگر"

        return result

    except Exception as e:
        log.error(f"❌ SQL Error: {e} | Query: {query}")
        return f"❌ خطا در اجرای کوئری: {str(e)}"


@tool
def get_sample_data() -> str:
    """
    دریافت ۵ نمونه داده از جدول برای درک مقادیر واقعی ستون‌ها.
    قبل از نوشتن کوئری از این ابزار استفاده کن.
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM `people_db`.`people` LIMIT 5")
            rows = cur.fetchall()
        conn.close()

        if not rows:
            return "جدول خالی است."

        result = "نمونه داده‌ها:\n"
        result += "=" * 40 + "\n"
        for i, row in enumerate(rows, 1):
            result += f"\nردیف {i}:\n"
            for k, v in row.items():
                result += f"  {k}: {v}\n"
        return result

    except Exception as e:
        return f"❌ خطا: {str(e)}"