# Evaluación real de la VERSIÓN 3 (retroalimentación completa y accionable en la variante verificada). ~25 min.
#   .\scripts\mejora_v3.ps1
$py = ".\.venv\Scripts\python.exe"
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "Fallan las pruebas offline." -ForegroundColor Red; exit 1 }
& $py evaluacion\ejecutar_evaluacion.py --modo real --etiqueta v3_verificada --configs smolagents pydantic_local pydantic_mcp --variante verificada --salida prompted
& $py evaluacion\resumen.py resultados\v2_verificada resultados\v3_verificada
