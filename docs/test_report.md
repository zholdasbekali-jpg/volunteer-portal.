# Тестілеу жоспары мен есебі

Барлық нәтиже төменде 2026-11-12 күні нақты іске қосылған командалардан алынған (Linux, Python 3.13.18, Flask 3.1.3, pytest 9.1.1).

## Жоспар
- Құрал: pytest + pytest-cov. Әр тест жеке уақытша SQLite қорында (`tmp_path`) жұмыс істейді; тек ойдан шығарылған деректер.
- Деңгейлер: сервис (бизнес-логика) тесттері, HTTP тесттері (Flask test client: рөлдер, CSRF, қайта бағыттау, статус-кодтар), бір мезгілдік (ағындар) тест, қайта іске қосу тесті.
- Қосымша қолмен тексеру: тірі серверде Playwright/Chromium арқылы барлық рөлдердің беттері, PDF-ті суретке айналдырып көру.

## Нәтиже
```
python -m pytest
204 passed
```
| Файл | Тест саны |
|---|---|
| test_auth.py | 21 |
| test_events.py | 27 |
| test_registrations.py | 16 |
| test_admin_and_misc.py | 18 |
| test_certificates.py | 30 |
| test_checkin.py | 10 |
| test_cabinet.py | 11 |
| test_security.py | 20 |
| test_v2.py | 41 |
| test_statistics.py | 10 |
| **Барлығы** | **204** |

## ТЗ бойынша міндетті 12 тест
| № | Талап | Тест |
|---|---|---|
| 1 | Сәтті тіркелу | `test_register_success` |
| 2 | Бұрын тіркелген email | `test_register_duplicate_email_rejected` |
| 3 | Сәтті кіру | `test_login_success_and_wrong_password`, `test_http_register_login_logout_flow` |
| 4 | Қате пароль | `test_login_success_and_wrong_password`, `test_http_login_wrong_password_shows_error` |
| 5 | Іс-шара құру | `test_create_event` |
| 6 | Іс-шараға сәтті тіркелу | `test_register_success` (registrations) |
| 7 | Орын толғанда бас тарту | `test_register_rejected_when_full` |
| 8 | Қайталанатын тіркеуге тыйым | `test_duplicate_registration_forbidden`, `test_db_unique_constraint_blocks_duplicates` |
| 9 | Тіркеуден бас тарту (орын қайта есептеледі) | `test_cancel_registration_frees_spot` |
| 10 | Сертификаттың сәтті жасалуы | `test_certificate_issued_for_attended` |
| 11 | Қатыспағанға сертификат бермеу | `test_certificate_denied_when_not_attended` |
| 12 | Статистика дұрыс есептелуі | `test_summary_platform`, `test_summary_scoped_to_organizer`, `test_event_stats` |

Қосымша: рөл шектеулері (`test_role_restrictions`, `test_admin_actions_forbidden_for_others`, басқа ұйымдастырушыға 403), транзакция rollback, 5 ағынды бәсеке, CSRF, open-redirect, SQL-инъекция әрекеті, қайта іске қосудан кейін деректердің сақталуы, CLI командалары.

## QR-сканерді қолмен тексеру (Chromium, тірі сервер)
- Ерікті сертификатты жүктеді, PDF 200 DPI суретке айналдырылды, сурет `/verify` бетінде жүктелді: `/verify/VP-…` бетіне өтіп, «Сертификат түпнұсқа» көрсетілді.
- Камера: Chromium-ның виртуалды камерасына сертификат суреті берілді, «Камераны қосу» басылғанда QR танылып, тексеру бетіне өтті.
- Нақты телефонда, Windows-та және Termux-та тексерілмеген.

## Қамту (pytest-cov)
Бизнес-логика (`app/services`): **97 %** (782 жол, 26 өткізілген).

| Модуль | Қамту |
|---|---|
| services/auth_service.py | 92 % |
| services/certificate_service.py | 97 % |
| services/event_service.py | 97 % |
| services/registration_service.py | 93 % |
| services/statistics_service.py | 100 % |
| Бүкіл `app` | 97 % (1114 жол, 34 өткізілген) |

Қайталау: `python -m pytest --cov=app/services --cov-report=term-missing`.

## Тесттер ашқан қате
`test_search_and_filters` бастапқыда құлады: SQLite `LOWER()` кириллицаны төмендетпейді, сондықтан «саябақ» сұранысы «Саябақ тазалау» атауын таппады. Түзетілді (`PYLOWER` функциясы, `app/database.py`), қайта іске қосқанда 95/95 өтті. Кейінгі итерацияда қосылған тесттер: қала өрісі мен сүзгісі, ескі қорды көшіру, логотиптің барлық беттерде болуы және файлдың сервер арқылы берілуі, сынған логотиптің журналға жазылуы, сертификатта қала. Қолмен тексеруде (скриншот) каталог сүзгісінде мәтіннің кесіліп қалуы, графиктердің дизайн кемшіліктері (легенда бағанды жауып тұрды, бөлшек сандар осьте) де түзетілді.

## Өлшенбегендер / шектеулер (шынайы тізім)
- Тесттер тек Linux-та орындалды; Windows-та іске қосу `README.md` бойынша жазылған, бірақ осы жерде тексерілмеген.
- Мобильді бейімделу тек Chromium-да 390 px көрінісімен тексерілді, нақты телефон/планшетте емес.
- Өнімділік Flask test client-пен өлшенді (медиана ≈1 мс бет, ≈47 мс график); желі, көп пайдаланушы жүктемесі өлшенмеген.
- Браузердегі JS (растау диалогтары, клиенттік валидация) автоматты тестілермен қамтылмаған және жеке тексерілмеген.
- Қолмен тексерілген тізім: барлық беттердің ашылуы, PDF жүктеу және оның мәтінін оқу (`pdftotext`), браузер консолінде бет қателері болмады.
