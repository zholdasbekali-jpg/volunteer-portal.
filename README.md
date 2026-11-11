# Еріктілер іс-шаралары порталы

Flask-та жасалған веб-қосымша: еріктілер іс-шараларды іздейді, тіркеледі, қатысуы расталған соң PDF-сертификат алады; ұйымдастырушылар іс-шараларды және қатысушыларды басқарады; әкімші платформаны бақылайды. Интерфейс тілі: қазақша.

## Технологиялар
Python, Flask, Flask-Login, SQLite, Werkzeug, Jinja2, Bootstrap 5 (локалды), ReportLab (PDF), Matplotlib (графиктер), pytest, pytest-cov.

## Жүйелік талаптар
Python 3.11+ (тексерілген: 3.13). Орнату үшін интернет.

## Орнату
```bash
python -m venv .venv
# Windows:   .venv\Scripts\activate
# Linux/mac: source .venv/bin/activate
pip install -r requirements.txt
```

## Конфигурация
Әдепкі мәндермен жұмыс істейді. Қажет болса ортаның айнымалылары: `SECRET_KEY`, `DATABASE`, `CERTIFICATE_DIR`, `FLASK_DEBUG` (әдепкіде өшірулі). `SECRET_KEY` берілмесе, `instance/secret_key` жасалады (Git-ке түспейді).

## Деректер қорын құру
Автоматты түрде бірінші іске қосуда (`instance/volunteer.db`). Қолмен: `flask --app run init-db`.
Демо-деректер: `flask --app run seed-demo`. Әкімші: `flask --app run create-admin`.

## Іске қосу
```bash
python run.py
```
http://127.0.0.1:5000

## Тесттер және қамту
```bash
python -m pytest
python -m pytest --cov=app/services --cov-report=term-missing
```
Соңғы нәтиже: 105 тест өтті, бизнес-логика қамтуы 96 % (`docs/test_report.md`).

## Тест аккаунттар (тек `seed-demo` жүктелгенде)
| Рөл | Email | Пароль |
|---|---|---|
| Әкімші | admin@volunteer.kz | Admin12345 |
| Ұйымдастырушы | aigul@volunteer.kz | Demo12345 |
| Ерікті | volunteer1@volunteer.kz | Demo12345 |

Өндірісте бұл аккаунттарды пайдаланбаңыз.

## Брендинг және қалалар
- Логотип: `app/static/images/logo.png` (шапка, hero, кіру беттері, футер, сертификат). Ауыстыру үшін осы файлды өз суретіңізбен алмастырыңыз (мөлдір фонды PNG), серверді қайта іске қосыңыз.
- Түстер: `app/static/css/style.css` ішіндегі `:root`; сертификат түстері мен мәтіні: `app/services/certificate_service.py` (бастапқы тұрақтылар).
- Қалалар тізімі: `app/models.py` ішіндегі `CITIES`. Іс-шара қаласы мен мекенжайы бөлек өрістер. Ескі қор (қала бағанасыз) бірінші іске қосуда автоматты көшіріледі.

## Құжаттама
`docs/` бумасы: техникалық тапсырма, аналогтар талдауы, архитектура, деректер қоры, интерфейс, тест есебі, пайдаланушы және орнату нұсқаулықтары, түсіндірме жазба.
