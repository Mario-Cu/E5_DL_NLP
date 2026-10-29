# E5 — Asistente para comparar el WER de sistemas ASR por idioma

Entrega individual de la tarea E5 del módulo 5 (*Deep Learning aplicado al PLN*, UVa). Un asistente con agentes de IA
compara el WER de sistemas de reconocimiento de voz **por idioma**, usa herramientas para obtener la evidencia, calcula el
WER de forma determinista y **se abstiene** cuando faltan datos o no son válidos. Se implementa con tres frameworks
(smolagents, Pydantic AI y MCP) sobre un mismo dominio y se evalúan con el mismo modelo, datos, casos y límites.

* Repositorio: <https://github.com/Mario-Cu/E5_DL_NLP>
* Memoria: `memoria/memoria.pdf` (fuente LaTeX en `memoria/memoria.tex`)
* Todos los datos son **sintéticos** (conteos agregados inventados); no hay grabaciones ni información personal.
* No se usan claves de API: el modelo se ejecuta en local con Ollama.

## Estructura

```
asr_asistente/
  dominio.py        núcleo determinista: datos, validación, WER exacto (Fraction), permisos, regla de comparación
  herramientas.py   las dos herramientas de solo lectura (listar_sistemas, obtener_resultados) + auditoría
  contratos.py      salida final: unión discriminada comparacion / datos_insuficientes (Pydantic)
  verificador.py    verificación semántica independiente del modelo + evaluación de aceptación (4 niveles)
  politica.py       política de evaluación (resource MCP), instrucciones, límites y configuración del modelo
  servidor_mcp.py   servidor MCP (stdio): 2 tools + resource + prompt  |  cliente_mcp.py: transporte para pruebas/agente
  referencia.py     configuración 1: referencia determinista (sin LLM)
  dobles.py         modelos simulados con guion (solo prueban integración)
  agentes/          smol_agente.py (2) · pydantic_local.py (3) · pydantic_mcp.py (4) · modelos.py · comun.py · errores.py
datos/              resultados_asr.json (datos del enunciado) · escenarios/ (copias con una alteración) · generar_escenarios.py
evaluacion/         definir_casos.py → casos.json + casos.sha256 (congelados) · ejecutar_evaluacion.py · resumen.py ·
                    antes_despues.py · corregir_reintentos.py
pruebas/            96 pruebas offline (dominio, contrato, verificador, herramientas, MCP sin LLM, agentes con dobles, transporte)
resultados/         tandas REALES: base · v2_base · v2_prompted · v2_verificada · v3_verificada (medidas.csv/json, config_ejecucion.json,
                    no_ejecutadas.csv, trazas/) · resumen_tandas.md · antes_despues.md · trazas_comentadas.md
                    humo/ (prueba de humo previa, real, no se usa en la memoria) · integracion*/ (modelos simulados: NO son resultados)
scripts/            preparar_windows.ps1 · evaluacion_real.ps1 · mejoras_reales.ps1 · mejora_v3.ps1
ollama/Modelfile    qwen2.5:14b con num_ctx 8192
memoria/            memoria.tex, refs.bib y memoria.pdf
CAMBIOS.md          qué se ha cambiado respecto al código de ejemplo del módulo y entre versiones
```

## Reproducibilidad

* **Python**: 3.13 (probado con 3.13.16 en Linux y 3.13.5 en Windows 11); debería valer ≥ 3.11.
* **Dependencias**: `requirements.txt` (directas, versiones fijadas) y `requirements-lock.txt` (congelado completo del entorno de pruebas Linux).
  Versiones clave: smolagents 1.26.0, pydantic-ai-slim 2.63.0, mcp 2.3.0, fastmcp-slim 4.1.4, litellm 1.83.0, pydantic 2.14.1.
* **MCP**: transporte **stdio** (el servidor se lanza como subproceso). Revisión del protocolo negociada: **2026-07-28**
  (se registra en `resultados/*/config_ejecucion.json`). No confundir con la versión del paquete (`mcp==2.3.0`).
* **Modelo**: `qwen2.5:14b` en Ollama (`ollama/Modelfile` fija `num_ctx 8192`, temperatura 0.2, semilla 7; etiqueta local `qwen2.5-14b-asr`).
  Misma configuración para smolagents (LiteLLM → `ollama_chat/…`) y Pydantic AI (endpoint OpenAI-compatible de Ollama).
* **Límites** (fijados antes de ejecutar; `asr_asistente/politica.py`): 8 solicitudes al modelo, 10 llamadas a herramienta,
  2 reintentos de salida, 8 pasos en smolagents, 2 reintentos de transporte, 20 s por llamada MCP, 180 s por ejecución.

### Windows (PowerShell, desde la raíz del proyecto)

```powershell
.\scripts\preparar_windows.ps1                 # entorno virtual, dependencias, ollama pull + ollama create
.\.venv\Scripts\python.exe -m pytest -q         # 96 pruebas offline (sin LLM)
.\scripts\evaluacion_real.ps1 base              # evaluación real, versión 1 del código: git checkout v1-base
.\scripts\mejoras_reales.ps1                    # v2_base, v2_prompted, v2_verificada
.\scripts\mejora_v3.ps1                         # v3_verificada
```

### Linux / macOS

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
ollama pull qwen2.5:14b && ollama create qwen2.5-14b-asr -f ollama/Modelfile
python -m pytest -q
python evaluacion/ejecutar_evaluacion.py --modo real --etiqueta mi_tanda --variante verificada --salida prompted
python evaluacion/resumen.py resultados/mi_tanda
```

`--modo doble` ejecuta todo con modelos simulados (solo integración, resultados etiquetados como tales).
Las tandas de `resultados/` se hicieron con **el código de cada versión**: `v1-base` (git tag) produjo `resultados/base`;
`v2` produjo `v2_base`, `v2_prompted` y `v2_verificada`; `v3` produjo `v3_verificada` (ver `CAMBIOS.md`).

### Resultados reales frente a integración

Solo cuentan como resultado del sistema las tandas con `modo=real` (modelo `qwen2.5:14b`). Las carpetas `resultados/integracion*` se
generaron con **dobles de modelo con guion** (`--modo doble`, y `--defecto wer_falso|sigue_inyeccion` para inyectar un fallo de forma controlada):
comprueban que el montaje, el verificador y los permisos funcionan, pero no demuestran la capacidad de decisión de ningún LLM.
Las tandas `v2_prompted`, `v2_verificada` y `v3_verificada` tienen la columna `reintentos` corregida con `evaluacion/corregir_reintentos.py`
(el original está en `medidas_sin_corregir.csv`), y todas las tandas tienen corregida la validez estructural/coherencia de las salidas
descartadas por el verificador con `evaluacion/corregir_estructural.py` (original en `medidas_sin_corregir_estructural.csv`). Ambas correcciones
sincronizan también `medidas.json` y la fila embebida en cada traza. Son errores de **medida**, no del sistema:

```bash
python evaluacion/corregir_reintentos.py   resultados/v2_prompted resultados/v2_verificada resultados/v3_verificada
python evaluacion/corregir_estructural.py  resultados/base resultados/v2_base resultados/v2_prompted resultados/v2_verificada resultados/v3_verificada
python evaluacion/antes_despues.py resultados/v2_verificada resultados/v3_verificada resultados/antes_despues.md
python evaluacion/resumen.py resultados/base resultados/v2_base resultados/v2_prompted resultados/v2_verificada resultados/v3_verificada --sin-transporte
```

### Memoria

`memoria/memoria.tex` (+ `refs.bib`, `memoria.bbl`) y `memoria/memoria.pdf`. Compilar con `latexmk -pdf memoria.tex` (necesita `babel-spanish`).

### Qué NO se ha ejecutado

`resultados/*/no_ejecutadas.csv` lista cada configuración no ejecutada y su motivo. En particular, la alternativa
**`CodeAgent` de smolagents no se ha ejecutado**: ejecutar código generado por el modelo exigiría un entorno aislado
(Docker/E2B) que no se ha desplegado; se analiza en la memoria pero no hay quinta configuración medida.
