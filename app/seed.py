"""Демо-деректер. Тек көрсету үшін: ойдан шығарылған аккаунттар, нақты адамдардың деректері емес."""
from datetime import datetime, timedelta

from .database import get_db, transaction
from .services import auth_service, certificate_service
from .services.event_service import DATE_FMT

DEMO_PASSWORD = "Demo12345"
ADMIN_EMAIL = "admin@volunteer.kz"
ADMIN_PASSWORD = "Admin12345"


def _when(days: int, hour: int = 10) -> str:
    d = datetime.now() + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).strftime(DATE_FMT)


def seed_demo() -> str:
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return "Деректер қорында пайдаланушылар бар — демо-деректер жүктелмеді."

    auth_service.create_user_unchecked("Жүйе әкімшісі", ADMIN_EMAIL, ADMIN_PASSWORD, "admin")
    org1 = auth_service.create_user_unchecked("Айгүл Нұрланқызы", "aigul@volunteer.kz", DEMO_PASSWORD, "organizer")
    org2 = auth_service.create_user_unchecked("Данияр Әбдірахман", "daniyar@volunteer.kz", DEMO_PASSWORD, "organizer")
    names = ["Асем Сәрсенбай", "Ержан Қасымов", "Мадина Төлеген", "Нұрсұлтан Оспан",
             "Динара Бекбосын", "Арман Ғабит"]
    vols = [auth_service.create_user_unchecked(n, f"volunteer{i + 1}@volunteer.kz", DEMO_PASSWORD, "volunteer")
            for i, n in enumerate(names)]

    events = [  # (атауы, сипаттама, қала, мекенжай, күні, сыйымдылық, ұйымдастырушы)
        ("Қала саябағын тазалау", "Көктемгі сенбілік: саябақтағы қоқысты жинап, ағаштарды ақтаймыз. Қолғап пен қаптар беріледі.",
         "Қызылорда", "Орталық саябақ", _when(-20, 9), 4, org1),
        ("Қайырымдылық азық-түлік акциясы", "Мұқтаж отбасыларға азық-түлік жиынтықтарын буып-түйіп, үйлеріне жеткіземіз.",
         "Қызылорда", "Қоғамдық орталық, Тәуке хан даңғылы, 15", _when(-8, 11), 3, org1),
        ("Балалар үйіне қонаққа бару", "Балалармен ойын, шығармашылық шеберхана және кітап сыйлау.",
         "Астана", "№3 балалар үйі, Сарыарқа көшесі, 8", _when(5, 14), 5, org2),
        ("Жаңа ағаш отырғызу күні", "Өзен жағасында 200 көшет отырғызамыз. Күрек пен су беріледі.",
         "Қызылорда", "Сырдария жағалауы", _when(9, 10), 20, org1),
        ("Қайта өңдеуге арналған қалдық жинау", "Пластик пен қағазды сұрыптау бойынша ашық сабақ және акция.",
         "Алматы", "Мәдениет үйі алаңы, Абай даңғылы, 52", _when(14, 12), 2, org2),
        ("Қарттарға көмек: үйге қызмет", "Жалғыз тұратын қарттарға дүкен мен дәріхана бойынша көмек.",
         "Шымкент", "Әйтеке би көшесі, 21", _when(21, 10), 10, org2),
    ]
    ids = []
    with transaction() as tdb:
        for title, desc, city, loc, when, cap, org in events:
            cur = tdb.execute(
                "INSERT INTO events (title, description, city, location, event_date, capacity, hours, organizer_id) VALUES (?,?,?,?,?,?,?,?)",
                (title, desc, city, loc, when, cap, 2 + len(title) % 4, org))
            ids.append(cur.lastrowid)
        # Тіркелімдер: өткен іс-шараларға қатысу белгіленген, толған іс-шара да бар
        plan = [(0, vols[0], "attended"), (0, vols[1], "attended"), (0, vols[2], "absent"),
                (1, vols[0], "attended"), (1, vols[3], "absent"),
                (2, vols[0], "pending"), (2, vols[1], "pending"), (2, vols[4], "pending"),
                (3, vols[2], "pending"), (3, vols[5], "pending"),
                (4, vols[1], "pending"), (4, vols[3], "pending")]  # №5 іс-шара толды (2/2)
        for ev, vol, status in plan:
            tdb.execute("INSERT INTO registrations (user_id, event_id, status) VALUES (?,?,?)",
                        (vol, ids[ev], status))
    return (f"Демо-деректер жүктелді.\n  Әкімші: {ADMIN_EMAIL} / {ADMIN_PASSWORD}\n"
            f"  Ұйымдастырушы: aigul@volunteer.kz / {DEMO_PASSWORD}\n"
            f"  Ерікті: volunteer1@volunteer.kz / {DEMO_PASSWORD}")
