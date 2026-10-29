# Evaluación real con el LLM local (Ollama debe estar en marcha). Desde la raíz del proyecto:
#   .\scripts\evaluacion_real.ps1 base            -> las 4 configuraciones, variante base
#   .\scripts\evaluacion_real.ps1 mejora verificada -> solo Pydantic AI con el validador dentro del bucle
param([string]$Etiqueta = "base", [string]$Variante = "base")
$py = ".\.venv\Scripts\python.exe"
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "Fallan las pruebas offline: no se lanza la evaluación." -ForegroundColor Red; exit 1 }
& $py evaluacion\ejecutar_evaluacion.py --modo real --etiqueta $Etiqueta --variante $Variante
& $py evaluacion\resumen.py "resultados\$Etiqueta"
