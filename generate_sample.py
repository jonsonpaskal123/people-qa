# generate_sample.py  ← این رو داخل پوشه project بساز
import pandas as pd
import random
import os

random.seed(42)

FIRST_NAMES_MALE = [
    "علی", "محمد", "حسین", "رضا", "احمد", "مهدی", "امیر", "سعید",
    "حسن", "ابراهیم", "کریم", "جواد", "یوسف", "سینا", "آرش",
    "بهزاد", "فرهاد", "کامران", "نادر", "میلاد", "پدرام", "بابک"
]

FIRST_NAMES_FEMALE = [
    "فاطمه", "زهرا", "مریم", "سارا", "نگار", "الهه", "شیرین", "نازنین",
    "لیلا", "سمیه", "آزاده", "پریسا", "مهسا", "یاسمن", "رویا",
    "ندا", "سحر", "بهاره", "گلناز", "مینا", "آناهیتا", "درسا"
]

LAST_NAMES = [
    "احمدی", "محمدی", "حسینی", "رضایی", "کریمی", "موسوی", "رحیمی",
    "جعفری", "نجفی", "صادقی", "علوی", "طاهری", "شریفی", "مرادی",
    "ابراهیمی", "اسماعیلی", "قاسمی", "یوسفی", "حیدری", "باقری",
    "نوری", "سلیمانی", "فرهادی", "کمالی", "زارعی", "منصوری",
    "غلامی", "ناصری", "اکبری", "عزیزی", "تهرانی", "اصفهانی"
]

PROVINCES_CITIES = {
    "تهران":               ["تهران", "کرج", "ری", "شهریار", "اسلامشهر"],
    "اصفهان":              ["اصفهان", "کاشان", "نجف‌آباد", "شاهین‌شهر"],
    "فارس":                ["شیراز", "مرودشت", "جهرم", "فسا"],
    "خراسان رضوی":         ["مشهد", "نیشابور", "سبزوار", "تربت حیدریه"],
    "آذربایجان شرقی":      ["تبریز", "مراغه", "مرند", "اهر"],
    "مازندران":            ["ساری", "آمل", "بابل", "قائم‌شهر"],
    "گیلان":               ["رشت", "انزلی", "لاهیجان", "لنگرود"],
    "خوزستان":             ["اهواز", "آبادان", "خرمشهر", "دزفول"],
    "کرمانشاه":            ["کرمانشاه", "اسلام‌آباد غرب", "سنقر"],
    "البرز":               ["کرج", "فردیس", "نظرآباد", "هشتگرد"],
    "قم":                  ["قم", "جعفریه", "سلفچگان"],
    "همدان":               ["همدان", "ملایر", "نهاوند"],
    "هرمزگان":             ["بندرعباس", "قشم", "کیش", "میناب"],
    "کرمان":               ["کرمان", "سیرجان", "رفسنجان", "بم"],
    "سمنان":               ["سمنان", "شاهرود", "دامغان"],
}

EDUCATIONS        = ["زیر دیپلم", "دیپلم", "فوق دیپلم", "کارشناسی", "کارشناسی ارشد", "دکترا"]
EDUCATION_WEIGHTS = [5, 20, 15, 35, 18, 7]

JOBS_BY_EDUCATION = {
    "دکترا":           ["استاد دانشگاه", "پزشک", "وکیل", "روانپزشک", "دندانپزشک", "داروساز", "مشاور"],
    "کارشناسی ارشد":   ["مهندس نرم‌افزار", "مهندس عمران", "مهندس برق", "مدیر", "پژوهشگر", "معلم"],
    "کارشناسی":        ["کارمند دولت", "کارمند بانک", "حسابدار", "معلم", "طراح گرافیک", "پرستار"],
    "فوق دیپلم":       ["کارمند شرکت خصوصی", "فروشنده", "مکانیک", "الکتریکی", "آرایشگر"],
    "دیپلم":           ["فروشنده", "راننده", "کارگر", "نانوا", "خیاط", "کشاورز"],
    "زیر دیپلم":       ["کارگر ساختمانی", "کشاورز", "دامدار", "خانه‌دار", "بیکار"],
}

MARITAL_STATUS  = ["مجرد", "متأهل", "مطلقه", "بیوه"]
MARITAL_WEIGHTS = [30, 58, 8, 4]

BLOOD_GROUPS  = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
BLOOD_WEIGHTS = [34, 6, 9, 2, 3, 1, 38, 7]


def weighted_choice(items, weights):
    return random.choices(items, weights=weights, k=1)[0]


def generate_phone():
    prefixes = ["0912", "0911", "0913", "0914", "0915",
                "0916", "0917", "0930", "0933", "0935",
                "0936", "0937", "0938", "0901", "0902"]
    return random.choice(prefixes) + "".join([str(random.randint(0, 9)) for _ in range(7)])


def generate_national_id():
    return "".join([str(random.randint(0, 9)) for _ in range(10)])


def generate_income(education):
    ranges = {
        "دکترا":           (15_000_000, 80_000_000),
        "کارشناسی ارشد":   (10_000_000, 50_000_000),
        "کارشناسی":        (7_000_000,  30_000_000),
        "فوق دیپلم":       (5_000_000,  20_000_000),
        "دیپلم":           (4_000_000,  15_000_000),
        "زیر دیپلم":       (3_000_000,  10_000_000),
    }
    lo, hi = ranges[education]
    return random.randint(lo, hi)


def generate_person(pid):
    gender     = random.choice(["مرد", "زن"])
    first_name = random.choice(FIRST_NAMES_MALE if gender == "مرد" else FIRST_NAMES_FEMALE)
    last_name  = random.choice(LAST_NAMES)
    age        = random.randint(18, 75)
    education  = weighted_choice(EDUCATIONS, EDUCATION_WEIGHTS)
    job        = random.choice(JOBS_BY_EDUCATION[education])
    province   = weighted_choice(
        list(PROVINCES_CITIES.keys()),
        weights=[25, 8, 7, 9, 6, 6, 5, 5, 4, 5, 3, 3, 3, 4, 3]
    )
    city       = random.choice(PROVINCES_CITIES[province])

    return {
        "شناسه":          pid,
        "نام":            first_name,
        "نام خانوادگی":   last_name,
        "جنسیت":          gender,
        "سن":             age,
        "کد ملی":         generate_national_id(),
        "تلفن":           generate_phone(),
        "استان":          province,
        "شهر":            city,
        "تحصیلات":        education,
        "شغل":            job,
        "وضعیت تأهل":     weighted_choice(MARITAL_STATUS, MARITAL_WEIGHTS),
        "گروه خونی":      weighted_choice(BLOOD_GROUPS, BLOOD_WEIGHTS),
        "درآمد ماهانه":   generate_income(education),
    }


def main():
    print("⏳ در حال تولید داده‌ها...")
    os.makedirs("data", exist_ok=True)

    people = [generate_person(i + 1) for i in range(1000)]
    df     = pd.DataFrame(people)

    output = "data/people.xlsx"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="افراد")
        ws = writer.sheets["افراد"]
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 18

    print(f"✅ فایل ساخته شد: {output}")
    print(f"📊 تعداد رکورد: {len(df)}")
    print(f"\n📈 نمونه آمار:")
    print(f"   استان‌ها: {df['استان'].value_counts().head(3).to_dict()}")
    print(f"   میانگین سن: {df['سن'].mean():.1f}")
    print(f"   تحصیلات: {df['تحصیلات'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
