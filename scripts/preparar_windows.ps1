# Prepara el entorno en Windows (PowerShell). Ejecutar desde la raíz del proyecto:  .\scripts\preparar_windows.ps1
$ErrorActionPreference = "Stop"
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Ollama no está instalado. Instálalo con:  winget install Ollama.Ollama   (o desde https://ollama.com/download) y vuelve a ejecutar este script." -ForegroundColor Yellow
    exit 1
}
ollama pull qwen2.5:14b
ollama create qwen2.5-14b-asr -f ollama/Modelfile
Write-Host "Listo. Comprueba las pruebas offline con:  .\.venv\Scripts\python.exe -m pytest -q" -ForegroundColor Green
