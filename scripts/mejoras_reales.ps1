# Evaluación real de la VERSIÓN 2 (3 tandas seguidas, ~1 h en total). Ollama debe estar en marcha.
#   .\scripts\mejoras_reales.ps1
# Tandas (misma batería de casos congelados, mismo modelo y mismos límites que la base):
#   v2_base        contrato v2 + descripciones unificadas, sin más cambios        (smolagents, pydantic_local, pydantic_mcp)
#   v2_prompted    + salida como JSON en texto validado contra la misma unión      (pydantic_local, pydantic_mcp)
#   v2_verificada  + verificador DENTRO del bucle del agente                       (las tres)
$py = ".\.venv\Scripts\python.exe"
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "Fallan las pruebas offline." -ForegroundColor Red; exit 1 }
$sin_ref = "smolagents","pydantic_local","pydantic_mcp"
& $py evaluacion\ejecutar_evaluacion.py --modo real --etiqueta v2_base --configs $sin_ref --variante base --salida tool
& $py evaluacion\ejecutar_evaluacion.py --modo real --etiqueta v2_prompted --configs pydantic_local pydantic_mcp --variante base --salida prompted
& $py evaluacion\ejecutar_evaluacion.py --modo real --etiqueta v2_verificada --configs $sin_ref --variante verificada --salida prompted
& $py evaluacion\resumen.py resultados\base resultados\v2_base resultados\v2_prompted resultados\v2_verificada
