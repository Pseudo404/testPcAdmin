@echo off
echo Installation des dependances...
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install fastapi uvicorn sqlalchemy jinja2
echo.
echo Demarrage du serveur de synchronisation...
echo L'interface sera disponible sur http://localhost:8000
uvicorn main:app --host 0.0.0.0 --port 8000
