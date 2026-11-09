"""Домендік модельдер мен тұрақты мәндер (рөлдер, мәртебелер, қазақша атаулар)."""
from flask_login import UserMixin

ROLE_VOLUNTEER = "volunteer"
ROLE_ORGANIZER = "organizer"
ROLE_ADMIN = "admin"
ROLES = (ROLE_VOLUNTEER, ROLE_ORGANIZER, ROLE_ADMIN)
SELF_REGISTER_ROLES = (ROLE_VOLUNTEER, ROLE_ORGANIZER)  # админді тек жүйе жасайды

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
