"""Қосымшаны іске қосу нүктесі: python run.py"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug параметрі config.py арқылы FLASK_DEBUG ортасынан оқылады (әдепкіде өшірулі)
    app.run(host="127.0.0.1", port=5000, debug=app.config["DEBUG"])
