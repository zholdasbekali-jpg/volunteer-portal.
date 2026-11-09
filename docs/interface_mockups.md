# Интерфейс макеті

Төмендегі суреттер дайын қосымшаның нақты скриншоттары (Chromium, демо-деректермен). Дизайн жүйесі: ашық фон, негізгі жасыл түс (#1f7a4d), дөңгеленген карточкалар (16 px), жұмсақ көлеңкелер, жүйелік қаріп стегі; Bootstrap 5 негізінде, `app/static/css/style.css` ішінде бірыңғай токендермен.

| № | Бет | URL | Скриншот |
|---|---|---|---|
| 1 | Басты бет | `/` | ![](screenshots/01_home.png) |
| 2 | Іс-шаралар каталогы (іздеу, сүзгі) | `/events` | ![](screenshots/02_catalog.png) |
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
| 10 | Статистика | `/statistics` | ![](screenshots/10_stats.png) |
| 11 | Әкімші панелі | `/admin/` | ![](screenshots/11_admin.png) |
| — | Мобильді көрініс (390 px) | `/`, `/events` | ![](screenshots/12_mobile_home.png) ![](screenshots/13_mobile_catalog.png) |

Күйлер: бос деректер (мысалы, «Әзірге ешкім тіркелмеген»), қате/ескерту хабарламалары (flash), батырмадағы жүктелу индикаторы (`data-loading`), графиктердің жүктелу/қате күйі, 403/404/500 беттері.
