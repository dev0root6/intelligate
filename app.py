from flask import Flask
from config import Config
from database import init_db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    init_db()

    from routes import register_routes
    register_routes(app)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
