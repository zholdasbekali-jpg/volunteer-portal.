"""Көмекшілер: басқару кестелерін іздеу, сүзгілеу және сұрыптау.

Функциялар таза: sqlite Row немесе dict қатарымен жұмыс істейді, деректер қорына
қолданбайды. Барлық қолжетімділік тексеруі сәйкес сервистерде қалады.
"""

# Іс-шараларды басқару беттеріндегі мәртебе сүзгісі
EVENT_FILTERS = (
    ("", "Барлығы"),
    ("upcoming", "Алдағы"),
    ("past", "Өткен"),
    ("published", "Жарияланған"),
    ("cancelled", "Тоқтатылған"),
)


def search_rows(rows, query, fields):
    """Бірнеше өріс бойынша регистрге сезімтал емес іздеу."""
    needle = (query or "").strip().casefold()
    if not needle:
        return list(rows)
    return [row for row in rows
            if any(needle in str(row[field] if row[field] is not None else "").casefold()
                   for field in fields)]


def filter_rows(rows, field, value):
    """Нақты мән бойынша сүзгі (бос мән — сүзгі жоқ)."""
    if not value:
        return list(rows)
    return [row for row in rows if str(row[field]) == str(value)]


def _sort_key(value):
    if value is None:
        return (0, "")
    if isinstance(value, (int, float)):
        return (1, value)
    return (2, str(value).casefold())


def sort_rows(rows, key, choices, default):
    """choices: {аты: (өріс, кері рет пе)}. Белгісіз аты әдепкіге ауысады."""
    field, reverse = choices.get(key) or choices[default]
    return sorted(rows, key=lambda row: _sort_key(row[field]), reverse=reverse)
