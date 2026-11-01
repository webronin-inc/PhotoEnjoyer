"""Точка входа WSGI (PythonAnywhere и любой другой WSGI-хостинг)."""
from server.app import create_app

application = create_app()
