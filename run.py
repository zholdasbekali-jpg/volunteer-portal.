"""Қосымшаны іске қосу нүктесі: python run.py"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug параметрі config.py арқылы FLASK_DEBUG ортасынан оқылады (әдепкіде өшірулі)
    # HOST=0.0.0.0 болса, сайт сол Wi-Fi желісіндегі телефоннан да ашылады (docs/phone_access.md)
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")),
            debug=app.config["DEBUG"])
