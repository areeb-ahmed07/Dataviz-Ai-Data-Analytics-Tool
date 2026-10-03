"""
DataViz Pro — Application Entry Point

Usage:
    python run.py

Starts the Flask development server. For production, use gunicorn:
    gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
