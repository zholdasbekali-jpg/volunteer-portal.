"""Ақылды іздеу (ИИ-сіз): сұрауды қала, уақыт және тақырып бойынша бөліп түсінеді.
Мысал: «экология Қызылордада осы апта» -> қала=Қызылорда, апта, тақырып=экология."""
import re
from datetime import date, timedelta

from ..i18n import translate
from ..models import CITIES

# Тақырыптар: сөздің бір мүшесі табылса, бүкіл топ бойынша іздейміз (қазақша + орысша)
TOPICS = {
    "экология": ("экология", "эколог", "қоқыс", "тазалау", "ағаш", "жасыл", "табиғат",
                 "экологи", "уборк", "мусор", "дерев"),
    "білім": ("білім", "оқу", "сабақ", "мектеп", "курс", "образован", "урок", "обуч"),
    "спорт": ("спорт", "жүгіру", "марафон", "футбол", "жарыс", "бег"),
    "қайырымдылық": ("қайырымдылық", "көмек", "қарт", "жетім", "мейірім", "благотвор", "помощ", "пожил"),
    "медицина": ("медицина", "қан", "донор", "денсаулық", "дәрігер", "здоровь", "медицин"),
}
STOPWORDS = {"осы", "және", "мен", "бар", "керек", "іс-шара", "іс-шаралар", "іс", "шара", "іздеу",
             "найди", "найти", "мероприятия", "мероприятие", "в", "на", "и"}
_WORD = re.compile(r"[\w\-]+", re.UNICODE)


def _city_match(token: str):
    """Септік жалғауын ескереді: «Қызылордада», «Астанада» -> бастапқы қала атауының түбірі.
    Қала атауы қазақша, орысша және ағылшынша жазылса да танылады («Кызылорда», «Kyzylorda»)."""
    for city in CITIES:
        for name in {city.casefold(), translate(city, "ru").casefold(), translate(city, "en").casefold()}:
            stem = name[:max(4, len(name) - 2)]
            if token == name or (len(token) >= 4 and token.startswith(stem) and len(token) <= len(name) + 5):
                return city
    return None


def _topic_terms(token: str):
    for terms in TOPICS.values():
        if any(token == t or (len(token) >= 4 and (token.startswith(t) or t.startswith(token))) for t in terms):
            return terms
    return None


def parse(q: str, today: date = None) -> dict:
    """-> {city, date_from, date_to, groups, labels}. groups: AND ішіндегі OR-топтар."""
    today = today or date.today()
    text = (q or "").casefold()
    out = {"city": "", "date_from": "", "date_to": "", "groups": [], "labels": []}

    def span(a, b, label):
        out["date_from"], out["date_to"] = a.isoformat(), b.isoformat()
        out["labels"].append(label)

    # (сөз тіркестері қазақша, орысша, ағылшынша; белгі әрқашан қазақша — көрсеткенде аударылады)
    for phrases, fn in (
        (("осы апта", "на этой неделе", "эта неделя", "this week"),
         lambda: span(today - timedelta(days=today.weekday()),
                      today - timedelta(days=today.weekday()) + timedelta(days=6), "осы апта")),
        (("осы ай", "в этом месяце", "этот месяц", "this month"),
         lambda: span(today.replace(day=1),
                      (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), "осы ай")),
        (("бүгін", "сегодня", "today"), lambda: span(today, today, "бүгін")),
        (("ертең", "завтра", "tomorrow"), lambda: span(today + timedelta(days=1), today + timedelta(days=1), "ертең")),
    ):
        phrase = next((p for p in phrases if p in text), None)
        if phrase:
            fn()
            text = text.replace(phrase, " ")
            break

    for token in _WORD.findall(text):
        if token in STOPWORDS or len(token) < 2:
            continue
        city = _city_match(token) if not out["city"] else None
        if city:
            out["city"] = city
            out["labels"].append(f"қала: {city}")
            continue
        terms = _topic_terms(token)
        if terms:
            out["groups"].append(tuple(dict.fromkeys((token,) + terms)))
            out["labels"].append(f"тақырып: {token}")
        else:
            out["groups"].append((token,))
            out["labels"].append(f"«{token}»")
    return out
