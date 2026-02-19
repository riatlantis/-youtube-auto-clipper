@echo off
setlocal
cd /d %~dp0

set "STREAMLIT_SERVER_HEADLESS=true"
python -m streamlit run app\app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true

endlocal
