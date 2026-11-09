"""Бизнес-логиканың ерекшеліктері. Маршруттар оларды ұстап, пайдаланушыға түсінікті хабарлама көрсетеді."""


class ServiceError(Exception):
    """Базалық қате: хабарлама пайдаланушыға көрсетіледі."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(ServiceError):
    """Енгізілген деректер дұрыс емес."""

    status_code = 400


class PermissionDenied(ServiceError):
    """Әрекетке құқық жоқ (рөл немесе меншік)."""

    status_code = 403


class NotFound(ServiceError):
    """Жазба табылмады."""

    status_code = 404


class Conflict(ServiceError):
    """Бизнес-ереже бұзылды (орын жоқ, қайталанған тіркелу, т.б.)."""

    status_code = 409
