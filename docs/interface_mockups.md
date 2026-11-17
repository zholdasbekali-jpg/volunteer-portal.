# Интерфейс макеті

Төмендегі суреттер дайын қосымшаның нақты скриншоттары (Chromium, демо-деректермен). Дизайн жүйесі: QAMQOR стилі: қою жасыл (#103309) шапка, hero және футер, алтын (#d0b470) жиектер мен акценттер, ақшыл бежевый фон, дөңгеленген карточкалар (16 px), жұмсақ көлеңкелер; Bootstrap 5 негізінде, `app/static/css/style.css` ішіндегі `:root` токендерімен. Логотип барлық беттерде бар.

| № | Бет | URL | Скриншот |
|---|---|---|---|
| 1 | Басты бет | `/` | ![](screenshots/01_home.png) |
| 2 | Іс-шаралар каталогы (іздеу, қала/күн/мәртебе сүзгісі) | `/events` | ![](screenshots/02_catalog.png) |
| 3 | Іс-шара беті (қонақ) | `/events/<id>` | ![](screenshots/03_detail_anon.png) |
| 3б | Іс-шара беті (ерікті, тіркелу) | `/events/<id>` | ![](screenshots/04_detail_vol.png) |
| 4 | Тіркелу | `/register` | ![](screenshots/14_register.png) |
| 5 | Кіру | `/login` | ![](screenshots/15_login.png) |
| 6 | Эріктінің жеке кабинеті | `/my` | ![](screenshots/05_my.png) |
| 7 | Ұйымдастырушы панелі | `/organizer` | ![](screenshots/07_org.png) |
| 7б | Іс-шара құру/өңдеу формасы | `/organizer/events/new` | ![](screenshots/09_form.png) |
| 8 | Қатысушыларды басқару | `/organizer/events/<id>/participants` | ![](screenshots/08_participants.png) |
| 9 | Сертификаттар беті | `/certificates` | ![](screenshots/06_certs.png) |
| 9б | PDF-сертификат үлгісі | жүктеу | ![](screenshots/16_certificate_pdf.png) |
| 9в | QR-кодты сертификат | жүктеу | ![](screenshots/14_certificate_qr.png) |
| 9г | QR-сканер беті | `/verify` | ![](screenshots/12_verify_scanner.png) |
| 9д | Тексеру нәтижесі | `/verify/<нөмір>` | ![](screenshots/13_verify_result.png) |
| 10 | Статистика | `/statistics` | ![](screenshots/10_stats.png) |
| 11 | Әкімші панелі | `/admin/` | ![](screenshots/11_admin.png) |
| — | Мобильді көрініс (390 px) | `/`, `/events`, `/login` | ![](screenshots/12_mobile_home.png) ![](screenshots/13_mobile_catalog.png) ![](screenshots/18_mobile_login.png) |
| — | 404 беті | кез келген жоқ URL | ![](screenshots/17_404.png) |
| 10 | QR арқылы белгілеу: ұйымдастырушы экраны | `/organizer/events/<id>/checkin` | ![](screenshots/17_checkin_screen.png) |
| 10б | Қатысуды растау (телефон) | `/checkin/<белгі>` | ![](screenshots/18_checkin_phone.png) |

Күйлер: бос деректер (мысалы, «Әзірге ешкім тіркелмеген»), қате/ескерту хабарламалары (flash), батырмадағы жүктелу индикаторы (`data-loading`), графиктердің жүктелу/қате күйі, 403/404/500 беттері.
