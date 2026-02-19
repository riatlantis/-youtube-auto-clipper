@echo off
setlocal
curl -s -o nul -w "HTTP %%{http_code}\n" http://127.0.0.1:8501
if errorlevel 1 (
  echo GAGAL connect ke http://127.0.0.1:8501
  echo Cek log: C:\Users\cep_c\youtube-auto-clipper\logs\streamlit.err.log
)
endlocal
