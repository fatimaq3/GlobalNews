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
from datetime import datetime, timezone

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
            "saudi", "riyadh", "aramco", "neom", "opec",
            "arabie saoudite", "riyad",
            "saudi-arabien", "saudiarabien",
            "arabia saudita", "arabia saudí", "arábia saudita",
            "suudi arabistan",
        ],
        "substring": [
            "السعودية", "السعوديه", "الرياض", "أرامكو", "ارامكو", "نيوم", "أوبك",
            "سعودی", "عربستان", "ریاض",
            "סעודיה", "ריאד",
            "沙特", "利雅得", "阿美",
            "サウジ", "リヤド",
            "사우디", "리야드",
            "Саудовск", "Эр-Рияд",
        ],
    },
    "gulf": {
        "bounded": [
            "gulf", "gcc", "uae", "emirates", "qatar", "kuwait", "bahrain",
            "oman", "hormuz", "abu dhabi", "dubai", "doha",
            "golfe", "émirats", "qatari",
            "katar", "kuveyt", "bahreyn", "umman", "körfez", "hürmüz",
            "golfo", "emiratos", "emirados", "emirati",
        ],
        "substring": [
            "الخليج", "الإمارات", "الامارات", "قطر", "الكويت", "البحرين",
            "عمان", "عُمان", "هرمز", "أبوظبي", "ابوظبي", "دبي", "الدوحة",
            "مجلس التعاون",
            "خلیج", "امارات", "کویت", "بحرین", "هرمز",
            "המפרץ", "קטר", "כווית", "בחריין", "עומאן", "אמירויות",
            "海湾", "波斯湾", "阿联酋", "卡塔尔", "科威特", "巴林", "阿曼", "霍尔木兹", "迪拜", "多哈",
            "湾岸", "ホルムズ", "カタール", "クウェート", "バーレーン", "オマーン", "首長国", "ドバイ", "ドーハ",
            "걸프", "카타르", "쿠웨이트", "바레인", "오만", "아랍에미리트", "호르무즈", "두바이", "도하",
            "Персидск", "залив", "ОАЭ", "Катар", "Кувейт", "Бахрейн", "Оман", "Ормуз", "Дубай", "Доха",
        ],
    },
    "war": {
        "bounded": [
            "war", "airstrike", "air strike", "missile", "invasion", "offensive",
            "military", "troops", "bombing", "shelling", "drone attack", "ceasefire",
            "guerre", "frappe", "attaque", "invasion", "militaire",
            "krieg", "angriff", "rakete", "luftangriff", "militär",
            "guerra", "attacco", "missile", "invasione", "militare",
            "ataque", "misil", "invasión", "militar", "míssil", "invasão",
            "savaş", "saldırı", "füze", "işgal", "askeri", "ateşkes",
        ],
        "substring": [
            "حرب", "قصف", "غارة", "غارات", "هجوم", "هجمات", "صاروخ", "صواريخ",
            "اجتياح", "معارك", "عسكري", "عسكرية", "مسيّرة", "مسيرات", "وقف إطلاق النار",
            "جنگ", "حمله", "موشک", "نظامی", "پهپاد",
            "מלחמה", "תקיפה", "טיל", "פלישה", "צבאי", "הפצצה",
            "战争", "空袭", "袭击", "导弹", "入侵", "军事", "轰炸", "无人机袭击", "停火",
            "戦争", "空爆", "攻撃", "ミサイル", "侵攻", "軍事", "無人機", "停戦",
            "전쟁", "공습", "공격", "미사일", "침공", "군사", "무인기", "휴전",
            "война", "войн", "удар", "атак", "ракет", "вторжени", "военн", "обстрел", "перемири",
        ],
    },
    "repercussions": {
        "bounded": [
            "escalation", "sanctions", "crisis", "tensions", "fallout", "repercussions",
            "escalade", "crise", "eskalation", "sanktionen", "krise", "spannungen",
            "sanzioni", "crisi", "tensioni",
            "escalada", "sanciones", "tensiones", "sanções", "tensões",
            "gerilim", "yaptırım", "kriz", "tırmanma",
        ],
        "substring": [
            "تداعيات", "تصعيد", "عقوبات", "أزمة", "ازمة", "توتر", "توترات",
            "تنش", "تحریم", "بحران", "تشدید",
            "הסלמה", "סנקציות", "משבר", "מתיחות",
            "升级", "制裁", "危机", "紧张",
            "制裁", "危機", "緊張", "エスカレート",
            "제재", "위기", "긴장", "확전",
            "эскалаци", "санкци", "кризис", "напряжен",
        ],
    },
}

# فئات الحرب والتداعيات وحدها لا تكفي — لا بد أن يرتبط الخبر بالسعودية أو الخليج
# أو أن يكون خبر حرب/تصعيد بحد ذاته. (نُبقي كل خبر حرب لأن المطلوب "أي خبر يتعلق بالحرب".)

CATEGORY_LABELS_AR = {
    "saudi": "السعودية",
    "gulf": "الخليج",
    "war": "الحرب",
    "repercussions": "التداعيات",
}

MAX_ENTRIES_PER_FEED = 50
REQUEST_TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (GlobalNewsMonitor/1.0; +https://github.com)"}


def compile_patterns():
    compiled = {}
    for cat, groups in KEYWORDS.items():
        bounded = [
            re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE | re.UNICODE)
            for kw in groups["bounded"]
        ]
        substr = groups["substring"]
        compiled[cat] = (bounded, substr)
    return compiled


PATTERNS = compile_patterns()


def classify(text: str):
    """يعيد قائمة الفئات المطابقة للنص."""
    cats = []
    low = text.lower()
    for cat, (bounded, substr) in PATTERNS.items():
        hit = any(p.search(text) for p in bounded)
        if not hit:
            hit = any(kw.lower() in low for kw in substr)
        if hit:
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


def clean_google_title(title: str) -> str:
    """عناوين Google News تنتهي بـ' - Source Name'؛ نحذف الذيل."""
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


def collect_articles(sources):
    rows = []
    seen_links = set()
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
