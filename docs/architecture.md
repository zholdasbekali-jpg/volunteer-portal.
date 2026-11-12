# Қосымшаның архитектурасы

Қабатты архитектура: **маршруттар (HTTP) → бизнес-логика (services) → деректер қоры**. Маршруттарда SQL және бизнес-ережелер жоқ; сервистер Flask-тың `request`/шаблондарын білмейді.

```
Браузер ── HTTP ──> Blueprints (auth, events, registrations, certificates, statistics, admin)
                        │  roles_required, CSRF, flash-хабарламалар, шаблондар
                        ▼
                    services/ (auth, event, registration, certificate, statistics)
                        │  валидация, рөл/иелік тексеруі, транзакциялар, PDF, графиктер
                        ▼
                    database.py ── sqlite3 (параметрленген SQL) ──> instance/volunteer.db
                                                    generated/certificates/*.pdf
```

## Модульдер
| Модуль | Міндеті |
|---|---|
| `run.py` | Іске қосу нүктесі |
| `config.py` | Баптаулар; `SECRET_KEY` env-тен немесе `instance/secret_key` (Git-ке түспейді); `DEBUG` әдепкіде өшірулі |
| `app/__init__.py` | Қосымша фабрикасы, Flask-Login, CSRF, фильтрлер, қате беттері, CLI (`init-db`, `seed-demo`, `create-admin`) |
| `app/database.py` | Қосылым, схема, `transaction()` (BEGIN IMMEDIATE), кириллицаға арналған `PYLOWER` |
| `app/models.py` | `User` (Flask-Login), рөл/мәртебе константалары, қазақша атаулар, `CITIES` (қалалар тізімі) |
| `app/security.py` | CSRF токені мен тексеруі, қауіпсіз `next` |
| `app/auth.py` | Тіркелу/кіру/шығу, `roles_required` |
| `app/events.py` | Каталог, толық бет, ұйымдастырушы панелі, іс-шара CRUD, қатысушылар беті |
| `app/registrations.py` | Тіркелу, бас тарту, жеке кабинет, қатысу мәртебесі |
| `app/certificates.py` | Сертификат беті, PDF жүктеу, `/verify` (QR-сканер), `/verify/<код>` |
| `app/statistics.py` | Статистика беті, PNG графиктер |
| `app/admin.py` | Әкімші панелі, рөл өзгерту, пайдаланушыны жою |
| `app/services/*` | Бизнес-логика (төменде) |
| `app/seed.py` | Демо-деректер |

## Сервистер
- **auth_service**: валидация (email, пароль), тіркеу, аутентификация (қате хабарламасы email/парольді ажыратпайды), әкімші операциялары.
- **event_service**: деректерді тексеру (қала тізімнен), құру/өңдеу/тоқтату/жою, `can_manage` (ие немесе әкімші), іздеу мен сүзгілер (мәтін, қала, күні, мәртебе), `full_address`.
- **registration_service**: тіркелу (орын тексеру мен INSERT бір `BEGIN IMMEDIATE` транзакциясында), бас тарту, қатысу мәртебесі.
- **certificate_service**: беру шарттары, бірегей нөмір `VP-<жыл>-<8 hex>`, ReportLab PDF (QAMQOR дизайны, DejaVu Serif қарпі `app/static/fonts/`, логотип фонға кіріктіріліп беріледі; сертификатқа `/verify/<нөмір>` сілтемесі бар QR-код (ReportLab-тың кіріктірілген QR генераторы, қосымша тәуелділіксіз) салынады; логотип оқылмаса журналға ескерту жазылады, сертификат логотипсіз жасалады).
- **statistics_service**: SQL-есептеулер және Matplotlib графиктері (Agg backend, жадта PNG).

## Статикалық файлдар
`static_url()` (Jinja) файл атына өзгерген уақытты (`?v=`) қосады, сондықтан логотип/CSS жаңарғанда браузер ескі кэшті көрсетпейді.

## Қауіпсіздік шаралары
- Рөлдер серверде `roles_required` және сервистердегі иелік тексеруімен қорғалады (интерфейсте батырманы жасыру қорғаныс емес).
- Барлық SQL параметрленген (`?`).
- CSRF: сессиялық токен, барлық POST-та тексеріледі.
- Парольдер Werkzeug `generate_password_hash` арқылы.
- `SECRET_KEY`, `.db` және PDF-тер `.gitignore`-да.
- Жауап тақырыптары: `X-Content-Type-Options`, `X-Frame-Options`; cookie `HttpOnly`, `SameSite=Lax`.
