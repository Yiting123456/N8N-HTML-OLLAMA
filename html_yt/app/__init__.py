
from flask import Flask

def create_app(config_obj='app.config.DevelopmentConfig'):
    app = Flask(__name__)
    app.config.from_object(config_obj)

    from .routes import bp
    app.register_blueprint(bp)

    return app
