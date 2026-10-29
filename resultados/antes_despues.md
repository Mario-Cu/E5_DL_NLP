# Antes (v2_verificada) y después (v3_verificada) de la modificación v3


## Casos afectados por el fallo

| caso | smolagents antes | smolagents después | pydantic_local antes | pydantic_local después | pydantic_mcp antes | pydantic_mcp después |
|---|---|---|---|---|---|---|
| C04 | 0/1 (limite_excedido) | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| C07 | 0/1 (limite_excedido) | 1/1 | 0/1 (salida_invalida) | 1/1 | 0/1 (salida_invalida) | 1/1 |
| C07b | 1/1 | 1/1 | 0/1 (salida_invalida) | 1/1 | 0/1 (salida_invalida) | 1/1 |

## Casos de no regresión (acertaban antes)

| caso | smolagents antes | smolagents después | pydantic_local antes | pydantic_local después | pydantic_mcp antes | pydantic_mcp después |
|---|---|---|---|---|---|---|
| C01 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| C03 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| C05 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| C08 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| C09 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
