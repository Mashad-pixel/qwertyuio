import os

from app import create_app

# Production is the default. For local development, set FLASK_CONFIG=development in .env.
app = create_app(os.getenv("FLASK_CONFIG", "production"))

if __name__ == "__main__":
    app.run(port=8000)
