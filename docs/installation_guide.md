# Орнату және іске қосу нұсқаулығы

Талап: Python 3.11+ (тексерілген нұсқа: 3.13), интернет (тек `pip install` үшін). Bootstrap, иконкалар және PDF қарпі жоба ішінде (`app/static/`), сондықтан іске қосқанда интернет қажет емес.

## 1. Орта және тәуелділіктер
**Windows (PowerShell):**
```powershell
cd VolunteerPortal
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
**Linux / macOS:**
```bash
cd VolunteerPortal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Деректер қорын құру
Қосымша бірінші іске қосылғанда `instance/volunteer.db` және кестелерді өзі құрады. Қолмен: `flask --app run init-db`.

Демо-деректер (міндетті емес): `flask --app run seed-demo`.
Өз әкіміңізді құру: `flask --app run create-admin`.

## 3. Іске қосу
```
python run.py
```
Браузерде: http://127.0.0.1:5000

## 4. Конфигурация
Ортаның айнымалылары (міндетті емес): `SECRET_KEY` (болмаса `instance/secret_key` файлы бір рет жасалады), `DATABASE`, `CERTIFICATE_DIR`, `FLASK_DEBUG=1` (тек әзірлеу үшін; әдепкіде өшірулі).

## 5. Тесттер
```
python -m pytest
python -m pytest --cov=app/services --cov-report=term-missing
```

## Ақаулықтарды жою
- `ModuleNotFoundError: flask_login`: виртуалды орта белсенді емес немесе `pip install -r requirements.txt` орындалмады.
- Порт бос емес: `run.py` ішіндегі `port=5000` мәнін өзгертіңіз.
- Жоба папкасының атында бос орын болса (мысалы, «VolunteerPortal beta»), командаларды тырнақшамен жазыңыз.
