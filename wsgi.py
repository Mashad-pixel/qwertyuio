import os

from app import create_app

# Production is the default: a missing FLASK_CONFIG must never start development settings.
# Local development sets FLASK_CONFIG=development in .env (see .env.example).
app = create_app(os.getenv("FLASK_CONFIG", "production"))
