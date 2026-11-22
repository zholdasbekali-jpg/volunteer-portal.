"""Ақылды іздеу (ИИ-сіз): сұрауды қала, уақыт және тақырып бойынша бөліп түсінеді.
Мысал: «экология Қызылордада осы апта» -> қала=Қызылорда, апта, тақырып=экология."""
import re
from datetime import date, timedelta

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
    """Септік жалғауын ескереді: «Қызылордада», «Астанада» -> бастапқы қала атауының түбірі."""
    for city in CITIES:
        c = city.casefold()
        stem = c[:max(4, len(c) - 2)]
        if token == c or (len(token) >= 4 and token.startswith(stem) and len(token) <= len(c) + 5):
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

    for phrase, fn in (
        ("осы апта", lambda: span(today - timedelta(days=today.weekday()),
                                  today - timedelta(days=today.weekday()) + timedelta(days=6), "осы апта")),
        ("осы ай", lambda: span(today.replace(day=1),
                                (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1),
                                "осы ай")),
        ("бүгін", lambda: span(today, today, "бүгін")),
        ("ертең", lambda: span(today + timedelta(days=1), today + timedelta(days=1), "ертең")),
    ):
        if phrase in text:
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
