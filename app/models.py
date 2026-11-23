"""Домендік модельдер мен тұрақты мәндер (рөлдер, мәртебелер, қазақша атаулар)."""
from flask_login import UserMixin

# Іс-шара өтетін қалалар (форма мен сүзгіде тізімнен таңдалады). Қосу үшін осы тізімді өзгертіңіз.
CITIES = ("Астана", "Алматы", "Шымкент", "Ақтау", "Ақтөбе", "Атырау", "Екібастұз", "Жезқазған",
          "Қарағанды", "Көкшетау", "Қонаев", "Қостанай", "Қызылорда", "Орал", "Өскемен",
          "Павлодар", "Петропавл", "Семей", "Талдықорған", "Тараз", "Теміртау", "Түркістан")

# Іс-шара санаттары: деректер қорында код сақталады, атауы қазақша (басқа тілдерге аударылады)
EVENT_CATEGORIES = (("ecology", "Экология"), ("education", "Білім"), ("sport", "Спорт"),
                    ("charity", "Қайырымдылық"), ("health", "Денсаулық"), ("culture", "Мәдениет"),
                    ("other", "Басқа"))
CATEGORY_CODES = tuple(code for code, _label in EVENT_CATEGORIES)
CATEGORY_LABELS = dict(EVENT_CATEGORIES)
DEFAULT_CATEGORY = "other"

# Интерфейс тілдері: қазақша (әдепкі), орысша, ағылшынша
LANG_CODES = ("kk", "ru", "en")
DEFAULT_LANG = "kk"

ROLE_VOLUNTEER = "volunteer"
ROLE_ORGANIZER = "organizer"
ROLE_ADMIN = "admin"
ROLES = (ROLE_VOLUNTEER, ROLE_ORGANIZER, ROLE_ADMIN)
SELF_REGISTER_ROLES = (ROLE_VOLUNTEER, ROLE_ORGANIZER)  # админді тек жүйе жасайды

# V3: одобрение организаторов администратором. Старые пользователи считаются одобренными.
APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
APPROVAL_STATUSES = (APPROVAL_PENDING, APPROVAL_APPROVED, APPROVAL_REJECTED)
APPROVAL_LABELS = {APPROVAL_PENDING: "Күтуде", APPROVAL_APPROVED: "Мақұлдалды",
                   APPROVAL_REJECTED: "Қабылданбады"}


def approval_of(actor) -> str:
    """Устойчивое чтение approval: User, sqlite3.Row, dict и старые тестовые actor-ы."""
    value = None
    try:
        value = actor["approval"]
    except (KeyError, TypeError, IndexError):
        pass
    if value is None:
        value = getattr(actor, "approval", None)
    return value if value in APPROVAL_STATUSES else APPROVAL_APPROVED


EVENT_PUBLISHED = "published"
EVENT_CANCELLED = "cancelled"

REG_PENDING = "pending"
REG_ATTENDED = "attended"
REG_ABSENT = "absent"
REG_STATUSES = (REG_PENDING, REG_ATTENDED, REG_ABSENT)

ROLE_LABELS = {ROLE_VOLUNTEER: "Ерікті", ROLE_ORGANIZER: "Ұйымдастырушы", ROLE_ADMIN: "Әкімші"}
EVENT_STATUS_LABELS = {EVENT_PUBLISHED: "Жарияланған", EVENT_CANCELLED: "Тоқтатылған"}
REG_STATUS_LABELS = {REG_PENDING: "Расталмаған", REG_ATTENDED: "Қатысты", REG_ABSENT: "Қатыспады"}


class User(UserMixin):
    """Flask-Login үшін пайдаланушы. Деректер қорындағы жолдан құрылады."""

    def __init__(self, row):
        self.id = row["id"]
        self.full_name = row["full_name"]
        self.email = row["email"]
        self.role = row["role"]
        self.approval = row["approval"] if "approval" in row.keys() else APPROVAL_APPROVED

    def __getitem__(self, key):
        """Сервистер actor["role"] түрінде оқиды: User мен sqlite Row бірдей жұмыс істейді."""
        return getattr(self, key)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_organizer(self) -> bool:
        return self.role == ROLE_ORGANIZER

    @property
    def is_volunteer(self) -> bool:
        return self.role == ROLE_VOLUNTEER

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)
