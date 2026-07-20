@echo off
set UV_CACHE_DIR=C:\!Claude_Erica\.uvdata\cache
set UV_PYTHON_INSTALL_DIR=C:\!Claude_Erica\.uvdata\python
cd /d C:\!Claude_Erica\SunlightAgent
"C:\Users\iabe&AI\.local\bin\uv.exe" run uvicorn sunlight.server.app:app --host 127.0.0.1 --port 8100
