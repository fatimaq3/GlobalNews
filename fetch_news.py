# -*- coding: utf-8 -*-
"""
المرصد الإخباري العالمي — جالب الأخبار
يقرأ خلاصات RSS لجميع المصادر، يفلتر العناوين بالكلمات المفتاحية
(السعودية / الخليج / الحرب / التداعيات) بلغات متعددة،
ثم يدخل النتائج في جدول global_news على Supabase.

يعمل عبر GitHub Actions. المتغيرات المطلوبة:
  SUPABASE_URL          مثال: https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  مفتاح service_role (سرّي)
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

# ----------------------------------------------------------------------------
# الكلمات المفتاحية لكل فئة، مقسومة إلى:
#   bounded  : لغات تفصل الكلمات بمسافات (لاتينية/سيريلية...) — مطابقة بحدود كلمة
#   substring: العربية/العبرية/الفارسية + الصينية/اليابانية/الكورية — مطابقة جزئية
# ----------------------------------------------------------------------------

KEYWORDS = {
    "saudi": {
        "bounded": [
            "saudi", "riyadh", "aramco", "neom", "opec", "wahhabi",
            "mbs", "mohammed bin salman", "mohammad bin salman",
            "bin salman", "crown prince salman", "saudi crown prince",
            "jeddah", "mecca", "makkah", "medina", "dammam", "al-ula",
            "red sea global", "pif", "public investment fund",
            "arabie saoudite", "riyad", "prince heritier saoudien",
            "saudi-arabien", "saudiarabien", "kronprinz",
            "arabia saudita", "arabia saudí", "arábia saudita", "principe heredero saudi",
            "suudi arabistan", "veliaht prens",
        ],
        "substring": [
            "السعودية", "السعوديه", "الرياض", "أرامكو", "ارامكو", "نيوم", "أوبك",
            "محمد بن سلمان", "بن سلمان", "ولي العهد", "ولي عهد السعودية",
            "جدة", "مكة", "المدينة المنورة", "الدمام", "العلا",
            "صندوق الاستثمارات", "الوهابية",
            "سعودی", "عربستان", "ریاض", "ولیعهد",
            "סעודיה", "ריאד",
            "沙特", "利雅得", "阿美",
            "サウジ", "リヤド",
            "사우디", "리야드",
            "Саудовск", "Эр-Рияд",
        ],
    },
    "gulf": {
        "bounded": [
            "gulf state", "gulf states", "gulf countries", "gulf region",
            "gulf cooperation", "gcc", "persian gulf", "arabian gulf",
            "uae", "u.a.e", "emirates", "emirati", "abu dhabi", "dubai", "sharjah",
            "qatar", "qatari", "doha",
            "kuwait", "kuwaiti",
            "bahrain", "bahraini", "manama",
            "oman", "omani", "muscat",
            "strait of hormuz", "hormuz",
            "etats du golfe", "pays du golfe", "golfe persique", "emirats arabes",
            "golfstaaten", "persischer golf",
            "stati del golfo", "golfo persico",
            "estados del golfo", "estados do golfo",
            "korfez ulkeleri", "basra korfezi", "hurmuz",
        ],
        "substring": [
            "الخليج", "دول الخليج", "الخليج العربي", "الخليج الفارسي",
            "الإمارات", "الامارات", "قطر", "الكويت", "البحرين",
            "سلطنة عمان", "عُمان", "مضيق هرمز", "هرمز",
            "أبوظبي", "ابوظبي", "دبي", "الشارقة", "الدوحة", "المنامة", "مسقط",
            "مجلس التعاون", "مجلس التعاون الخليجي",
            "خلیج", "امارات", "کویت", "بحرین", "هرمز",
            "המפרץ", "קטר", "כווית", "בחריין", "עומאן", "אמירויות",
            "海湾", "波斯湾", "阿联酋", "卡塔尔", "科威特", "巴林", "阿曼", "霍尔木兹", "迪拜", "多哈",
            "湾岸", "ホルムズ", "カタール", "クウェート", "バーレーン", "オマーン", "首長国", "ドバイ", "ドーハ",
            "걸프", "카타르", "쿠웨이트", "바레인", "오만", "아랍에미리트", "호르무즈", "두바이", "도하",
            "Персидск", "залив", "ОАЭ", "Катар", "Кувейт", "Бахрейн", "Оман", "Ормуз", "Дубай", "Доха",
        ],
    },
    # حرب إيران: تُصنّف فقط عند اجتماع (طرف إيراني) + (حرب أو تداعيات).
    # المطابقة الفعلية تتم في classify()، وهنا نضع كلمات "الحرب/التداعيات".
    "iran_war": {
        "bounded": [
            # عسكري / حرب
            "war", "warfare", "battle", "combat", "conflict", "frontline", "front line",
            "airstrike", "air strike", "strike", "missile", "rocket", "shelling",
            "invasion", "offensive", "assault", "incursion", "siege", "escalation",
            "military", "troops", "soldiers", "army", "militia", "proxy",
            "bombing", "bombardment", "drone", "drone strike", "drone attack", "artillery",
            "ceasefire", "truce", "clashes", "casualties", "retaliation", "attack",
            "enrichment", "nuclear", "uranium", "centrifuge", "snapback",
            # تداعيات (اقتصادية / مالية / سياسية) الناتجة عن الحرب
            "sanctions", "embargo", "blockade", "oil price", "crude", "energy price",
            "shipping", "tanker", "maritime", "insurance", "supply chain",
            "crisis", "tensions", "diplomatic", "talks", "negotiations", "deal",
            "guerre", "frappe", "missile", "sanctions", "petrole", "petrolier",
            "krieg", "angriff", "rakete", "sanktionen", "olpreis",
            "guerra", "attacco", "missile", "sanzioni", "petrolio",
            "ataque", "misil", "sanciones", "petroleo",
            "savas", "saldiri", "fuze", "yaptirim", "petrol",
        ],
        "substring": [
            "حرب", "قصف", "غارة", "غارات", "ضربة", "ضربات", "هجوم", "هجمات",
            "صاروخ", "صواريخ", "مسيّرة", "مسيرات", "طائرة مسيرة", "اجتياح", "توغل",
            "تصعيد", "اشتباك", "اشتباكات", "عسكري", "عسكرية", "ميليشيا", "ميليشيات",
            "وقف إطلاق النار", "هدنة", "قتلى", "ضحايا", "رد", "انتقام",
            "نووي", "تخصيب", "يورانيوم", "أجهزة الطرد",
            "عقوبات", "حظر", "حصار", "أسعار النفط", "النفط", "ناقلة", "ناقلات",
            "الملاحة", "سلاسل الإمداد", "أزمة", "توتر", "توترات", "مفاوضات", "اتفاق", "دبلوماسي",
            "جنگ", "موشک", "پهپاد", "تحریم", "تنش", "هسته‌ای", "غنی‌سازی",
            "מלחמה", "טיל", "סנקציות", "גרעין", "העשרה",
            "战争", "导弹", "制裁", "核", "浓缩铀", "石油",
            "戦争", "ミサイル", "制裁", "核", "石油",
            "전쟁", "미사일", "제재", "핵", "석유",
            "война", "ракет", "санкци", "ядерн", "нефт",
        ],
    },
}

# أطراف حرب إيران: لا يُصنّف الخبر "حرب إيران" إلا إذا ذُكر أحد هؤلاء
# إلى جانب كلمة حرب/تداعيات من قائمة iran_war أعلاه.
IRAN_AXIS = {
    "bounded": [
        "iran", "iranian", "tehran", "irgc", "revolutionary guard", "quds force",
        "houthi", "houthis", "ansar allah", "ansarallah",
        "hezbollah", "hizbollah", "hizbullah",
        "khamenei", "iran-backed", "iran backed", "tehran-backed",
        "proxy", "proxies", "axis of resistance",
        "iran", "iranien", "teheran", "houthis", "hezbollah",
        "iran", "iranisch", "teheran", "huthi", "hisbollah",
        "iran", "iraniano", "teheran", "houthi", "hezbollah",
        "iran", "irani", "teheran", "huties", "hezbola",
        "iran", "tahran", "husi", "hizbullah",
    ],
    "substring": [
        "إيران", "ايران", "إيراني", "ايراني", "طهران", "الحرس الثوري", "فيلق القدس",
        "الحوثي", "الحوثيون", "الحوثيين", "أنصار الله", "انصار الله",
        "حزب الله", "خامنئي", "الميليشيات", "ميليشيات إيران", "أذرع إيران",
        "محور المقاومة", "وكلاء إيران", "الوكلاء",
        "ایران", "تهران", "سپاه", "حوثی", "حزب‌الله", "خامنه‌ای",
        "איראן", "טהראן", "חות'ים", "חיזבאללה",
        "伊朗", "德黑兰", "胡塞", "真主党", "革命卫队",
        "イラン", "テヘラン", "フーシ", "ヒズボラ", "革命防衛隊",
        "이란", "테헤란", "후티", "헤즈볼라", "혁명수비대",
        "Иран", "Тегеран", "хуситы", "Хезболла", "КСИР",
    ],
}

# فئات الحرب والتداعيات وحدها لا تكفي — لا بد أن يرتبط الخبر بالسعودية أو الخليج
# أو أن يكون خبر حرب/تصعيد بحد ذاته. (نُبقي كل خبر حرب لأن المطلوب "أي خبر يتعلق بالحرب".)

CATEGORY_LABELS_AR = {
    "saudi": "السعودية",
    "gulf": "الخليج",
    "iran_war": "حرب إيران",
}

# لا نقبل الأخبار الأقدم من هذه المدة (بالأيام)
MAX_AGE_DAYS = 90

MAX_ENTRIES_PER_FEED = 50
REQUEST_TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (GlobalNewsMonitor/1.0; +https://github.com)"}


def _compile_group(groups):
    bounded = [
        re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE | re.UNICODE)
        for kw in groups["bounded"]
    ]
    return (bounded, groups["substring"])


def compile_patterns():
    return {cat: _compile_group(groups) for cat, groups in KEYWORDS.items()}


PATTERNS = compile_patterns()
AXIS_PATTERN = _compile_group(IRAN_AXIS)


def _matches(text, low, compiled):
    bounded, substr = compiled
    if any(p.search(text) for p in bounded):
        return True
    return any(kw.lower() in low for kw in substr)


def classify(text: str):
    """يعيد قائمة الفئات المطابقة للنص.

    saudi / gulf: مطابقة مباشرة بالكلمات المفتاحية.
    iran_war: يُصنّف فقط عند اجتماع (طرف إيراني: إيران/الحوثي/حزب الله/الميليشيات)
              مع (كلمة حرب أو تداعيات). خبر حرب عام بلا طرف إيراني لا يدخل.
    """
    cats = []
    low = text.lower()
    for cat, compiled in PATTERNS.items():
        if cat == "iran_war":
            has_conflict = _matches(text, low, compiled)
            has_axis = _matches(text, low, AXIS_PATTERN)
            if has_conflict and has_axis:
                cats.append(cat)
        else:
            if _matches(text, low, compiled):
                cats.append(cat)
    return cats


def google_news_url(fb: dict) -> str:
    return (
        "https://news.google.com/rss/search?q=site:{domain}"
        "&hl={hl}&gl={gl}&ceid={ceid}"
    ).format(**fb)


def parse_feed(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        return parsed.entries or []
    except Exception as exc:  # noqa: BLE001
        print(f"  [!] فشل جلب الخلاصة: {url} — {exc}")
        return []


def entry_published(entry):
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc).isoformat()
            except Exception:  # noqa: BLE001
                pass
    return None


def entry_dt(entry):
    """يعيد تاريخ الخبر ككائن datetime أو None."""
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                pass
    return None


def clean_google_title(title: str) -> str:
    """عناوين Google News تنتهي بـ' - Source Name'؛ نحذف الذيل."""
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


def collect_articles(sources):
    rows = []
    seen_links = set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    for src in sources:
        feeds = list(src.get("feeds") or [])
        used_google = False
        if not feeds and src.get("google_fallback"):
            feeds = [google_news_url(src["google_fallback"])]
            used_google = True

        entries = []
        for feed_url in feeds:
            got = parse_feed(feed_url)
            if got:
                entries.extend(got[:MAX_ENTRIES_PER_FEED])
                break  # أول خلاصة ناجحة تكفي لكل مصدر

        # إن فشلت الخلاصات المباشرة وكان هناك بديل Google، جرّبيه
        if not entries and not used_google and src.get("google_fallback"):
            entries = parse_feed(google_news_url(src["google_fallback"]))[:MAX_ENTRIES_PER_FEED]
            used_google = True

        matched = 0
        for entry in entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link or link in seen_links:
                continue
            if used_google:
                title = clean_google_title(title)
            # تجاهل الأخبار الأقدم من الحد المسموح (يمنع نتائج الأرشيف القديمة)
            dt = entry_dt(entry)
            if dt is not None and dt < cutoff:
                continue
            summary = re.sub(r"<[^>]+>", " ", entry.get("summary") or "")
            cats = classify(f"{title} {summary}")
            if not cats:
                continue
            seen_links.add(link)
            matched += 1
            rows.append(
                {
                    "title": title,
                    "link": link,
                    "source_name": src["name"],
                    "source_name_ar": src.get("name_ar"),
                    "country": src.get("country"),
                    "language": src.get("language"),
                    "categories": cats,
                    "published_at": entry_published(entry),
                }
            )
        print(f"  {src['name']}: {len(entries)} خبرًا، منها {matched} مطابقًا")
        time.sleep(0.5)
    return rows


def upsert(rows, supabase_url, service_key):
    if not rows:
        print("لا توجد أخبار مطابقة جديدة.")
        return
    endpoint = f"{supabase_url}/rest/v1/global_news?on_conflict=link"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=minimal",
    }
    # إدخال على دفعات لتفادي الطلبات الكبيرة
    batch = 100
    inserted = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        resp = requests.post(endpoint, headers=headers, data=json.dumps(chunk), timeout=30)
        if resp.status_code >= 300:
            print(f"  [!] فشل الإدخال ({resp.status_code}): {resp.text[:300]}")
        else:
            inserted += len(chunk)
    print(f"تم إرسال {inserted} خبرًا إلى Supabase (المكرر يُتجاهل تلقائيًا).")


def main():
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not supabase_url or not service_key:
        print("خطأ: المتغيران SUPABASE_URL و SUPABASE_SERVICE_KEY مطلوبان.")
        sys.exit(1)

    with open(os.path.join(os.path.dirname(__file__), "sources.json"), encoding="utf-8") as fh:
        sources = json.load(fh)["sources"]

    print(f"جلب الأخبار من {len(sources)} مصدرًا...")
    rows = collect_articles(sources)
    print(f"إجمالي الأخبار المطابقة: {len(rows)}")
    upsert(rows, supabase_url, service_key)


if __name__ == "__main__":
    main()
