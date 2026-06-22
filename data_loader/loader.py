# data_loader/loader.py
import os
import time
import logging
import pandas as pd
import pymysql

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
SR_HOST     = os.getenv("SR_HOST",     "starrocks")
SR_PORT     = int(os.getenv("SR_PORT", "9030"))
SR_USER     = os.getenv("SR_USER",     "root")
SR_PASSWORD = os.getenv("SR_PASSWORD", "")
SR_DATABASE = os.getenv("SR_DATABASE", "people_db")
EXCEL_PATH  = os.getenv("EXCEL_PATH",  "/data/people.xlsx")

# ─── نگاشت ستون فارسی به انگلیسی ────────────────────────────────────────────
COLUMN_MAP = {
    "شناسه":          "id",
    "نام":            "first_name",
    "نام خانوادگی":   "last_name",
    "جنسیت":          "gender",
    "سن":             "age",
    "کد ملی":         "national_id",
    "تلفن":           "phone",
    "استان":          "province",
    "شهر":            "city",
    "تحصیلات":        "education",
    "شغل":            "job",
    "وضعیت تأهل":     "marital_status",
    "گروه خونی":      "blood_group",
    "درآمد ماهانه":   "monthly_income",
}


def get_conn(database: str = None):
    return pymysql.connect(
        host=SR_HOST,
        port=SR_PORT,
        user=SR_USER,
        password=SR_PASSWORD,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


def wait_for_starrocks(max_retries=30, delay=10):
    log.info("⏳ منتظر StarRocks...")
    for i in range(max_retries):
        try:
            conn = get_conn()
            conn.close()
            log.info("✅ StarRocks آماده است!")
            return
        except Exception as e:
            log.warning(f"  تلاش {i+1}/{max_retries}: {e}")
            time.sleep(delay)
    raise RuntimeError("❌ StarRocks در دسترس نیست!")


def setup_database():
    log.info(f"🔧 ساخت دیتابیس '{SR_DATABASE}'...")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # ساخت دیتابیس
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{SR_DATABASE}`")
            log.info(f"✅ دیتابیس '{SR_DATABASE}' آماده است")

            # ساخت یوزر read-only برای Agent
            cur.execute("""
                CREATE USER IF NOT EXISTS 'readonly_user'@'%'
                IDENTIFIED BY 'ReadOnly@123'
            """)
            cur.execute(f"""
                GRANT SELECT ON `{SR_DATABASE}`.* TO 'readonly_user'@'%'
            """)
            log.info("✅ یوزر readonly_user ساخته شد")
        conn.commit()
    finally:
        conn.close()


def load_excel() -> pd.DataFrame:
    log.info(f"📂 خواندن فایل: {EXCEL_PATH}")
    df = pd.read_excel(EXCEL_PATH)

    # rename فارسی به انگلیسی
    df.rename(columns=COLUMN_MAP, inplace=True)

    # فقط ستون‌های شناخته شده
    known = [v for v in COLUMN_MAP.values() if v in df.columns]
    df = df[known].copy()

    # تمیزکاری
    df.dropna(how="all", inplace=True)
    df["age"]            = pd.to_numeric(df["age"],            errors="coerce").fillna(0).astype(int)
    df["monthly_income"] = pd.to_numeric(df["monthly_income"], errors="coerce").fillna(0).astype(int)

    log.info(f"✅ {len(df)} ردیف خوانده شد | ستون‌ها: {list(df.columns)}")
    return df


def create_table(conn):
    log.info("🔧 ساخت جدول people...")
    sql = f"""
    CREATE TABLE IF NOT EXISTS `{SR_DATABASE}`.`people` (
        `id`             BIGINT       NOT NULL,
        `first_name`     VARCHAR(100) NULL,
        `last_name`      VARCHAR(100) NULL,
        `gender`         VARCHAR(10)  NULL,
        `age`            INT          NULL,
        `national_id`    VARCHAR(20)  NULL,
        `phone`          VARCHAR(20)  NULL,
        `province`       VARCHAR(100) NULL,
        `city`           VARCHAR(100) NULL,
        `education`      VARCHAR(50)  NULL,
        `job`            VARCHAR(100) NULL,
        `marital_status` VARCHAR(20)  NULL,
        `blood_group`    VARCHAR(5)   NULL,
        `monthly_income` BIGINT       NULL
    )
    ENGINE = OLAP
    PRIMARY KEY(`id`)
    DISTRIBUTED BY HASH(`id`) BUCKETS 4
    PROPERTIES (
        "replication_num" = "1"
    )
    """
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    log.info("✅ جدول people آماده است")


def insert_data(conn, df: pd.DataFrame):
    log.info(f"📥 درج {len(df)} ردیف...")

    # پاک کردن داده قبلی
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE `{SR_DATABASE}`.`people`")
    conn.commit()

    # درج batch به batch
    cols    = list(df.columns)
    col_str = ", ".join(f"`{c}`" for c in cols)
    ph_str  = ", ".join(["%s"] * len(cols))
    sql     = f"INSERT INTO `{SR_DATABASE}`.`people` ({col_str}) VALUES ({ph_str})"

    BATCH = 200
    total = 0
    with conn.cursor() as cur:
        for start in range(0, len(df), BATCH):
            batch = df.iloc[start:start + BATCH]
            rows  = [tuple(row) for row in batch.itertuples(index=False)]
            cur.executemany(sql, rows)
            conn.commit()
            total += len(rows)
            log.info(f"  ✔ {total}/{len(df)} ردیف درج شد")

    log.info(f"✅ همه داده‌ها درج شدند!")


def verify_data(conn):
    log.info("🔍 تأیید داده‌ها...")
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) as cnt FROM `{SR_DATABASE}`.`people`")
        count = cur.fetchone()["cnt"]

        cur.execute(f"""
            SELECT province, COUNT(*) as cnt
            FROM `{SR_DATABASE}`.`people`
            GROUP BY province
            ORDER BY cnt DESC
            LIMIT 5
        """)
        top_provinces = cur.fetchall()

    log.info(f"✅ تعداد کل رکوردها: {count}")
    log.info("📊 Top 5 استان:")
    for row in top_provinces:
        log.info(f"   {row['province']}: {row['cnt']} نفر")


def main():
    wait_for_starrocks()
    setup_database()

    conn = get_conn(SR_DATABASE)
    try:
        df = load_excel()
        create_table(conn)
        insert_data(conn, df)
        verify_data(conn)
        log.info("🎉 فاز ۲ با موفقیت تکمیل شد!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()