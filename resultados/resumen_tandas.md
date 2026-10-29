# Resumen de todas las tandas (sin las pruebas de transporte T01-T03: mismos 17 casos de contenido en cada configuración)

## Resumen por configuración

| config | n | exito | estructural | coherente | permisos | t_medio | req | tools | reint |
|---|---|---|---|---|---|---|---|---|---|
| referencia @base | 17 | 17/17 | 17/17 | 17/17 | 17/17 | 0.0 | 0.0 | 0.0 | 0.0 |
| smolagents @base | 17 | 8/17 | 17/17 | 11/17 | 17/17 | 17.65 | 3.76 | 2.76 | 0.88 |
| pydantic_local @base | 17 | 3/17 | 3/17 | 3/17 | 17/17 | 14.86 | 4.18 | 2.24 | 0.82 |
| pydantic_mcp @base | 17 | 10/17 | 12/17 | 11/17 | 17/17 | 13.52 | 3.35 | 2.24 | 0.65 |
| smolagents @v2_base | 17 | 12/17 | 17/17 | 15/17 | 17/17 | 10.24 | 4.12 | 2.76 | 1.24 |
| pydantic_local @v2_base | 17 | 3/17 | 3/17 | 3/17 | 17/17 | 14.07 | 4.24 | 2.41 | 0.18 |
| pydantic_mcp @v2_base | 17 | 4/17 | 5/17 | 4/17 | 17/17 | 13.37 | 3.94 | 2.24 | 0.12 |
| pydantic_local [prompted] @v2_prompted | 17 | 15/17 | 17/17 | 15/17 | 17/17 | 6.61 | 2.41 | 2.47 | 0.59 |
| pydantic_mcp [prompted] @v2_prompted | 17 | 15/17 | 17/17 | 15/17 | 17/17 | 7.45 | 2.41 | 2.47 | 0.59 |
| smolagents [verificada] @v2_verificada | 17 | 12/17 | 15/17 | 15/17 | 17/17 | 11.15 | 4.82 | 2.76 | 2.06 |
| pydantic_local [verificada+prompted] @v2_verificada | 17 | 15/17 | 15/17 | 15/17 | 17/17 | 6.6 | 2.65 | 2.47 | 0.82 |
| pydantic_mcp [verificada+prompted] @v2_verificada | 17 | 15/17 | 15/17 | 15/17 | 17/17 | 7.81 | 2.65 | 2.47 | 0.82 |
| smolagents [verificada] @v3_verificada | 17 | 14/17 | 17/17 | 17/17 | 17/17 | 10.52 | 4.24 | 2.76 | 1.35 |
| pydantic_local [verificada+prompted] @v3_verificada | 17 | 17/17 | 17/17 | 17/17 | 17/17 | 6.56 | 2.41 | 2.47 | 0.59 |
| pydantic_mcp [verificada+prompted] @v3_verificada | 17 | 17/17 | 17/17 | 17/17 | 17/17 | 7.85 | 2.41 | 2.47 | 0.59 |

## Éxito por caso

| caso | pydantic_local @base | pydantic_local [prompted] @v2_prompted | pydantic_local @v2_base | pydantic_local [verificada+prompted] @v2_verificada | pydantic_local [verificada+prompted] @v3_verificada | pydantic_mcp @base | pydantic_mcp [prompted] @v2_prompted | pydantic_mcp @v2_base | pydantic_mcp [verificada+prompted] @v2_verificada | pydantic_mcp [verificada+prompted] @v3_verificada | referencia @base | smolagents @v2_base | smolagents @base | smolagents [verificada] @v2_verificada | smolagents [verificada] @v3_verificada |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | 0/3 | 3/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| C02 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| C03 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| C04 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 | 1/1 |
| C05 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| C06 | 0/3 | 3/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| C06b | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| C07 | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 | 1/1 |
| C07b | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 | 1/1 | 0/1 | 0/1 | 1/1 | 1/1 |
| C08 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| C08b | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| C09 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| C10 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |


# Con las pruebas de transporte (pydantic_mcp, n=20)

## Resumen por configuración

| config | n | exito | estructural | coherente | permisos | t_medio | req | tools | reint |
|---|---|---|---|---|---|---|---|---|---|
| referencia @base | 17 | 17/17 | 17/17 | 17/17 | 17/17 | 0.0 | 0.0 | 0.0 | 0.0 |
| smolagents @base | 17 | 8/17 | 17/17 | 11/17 | 17/17 | 17.65 | 3.76 | 2.76 | 0.88 |
| pydantic_local @base | 17 | 3/17 | 3/17 | 3/17 | 17/17 | 14.86 | 4.18 | 2.24 | 0.82 |
| pydantic_mcp @base | 20 | 13/20 | 14/19 | 13/19 | 20/20 | 15.01 | 3.4 | 2.35 | 0.65 |
| smolagents @v2_base | 17 | 12/17 | 17/17 | 15/17 | 17/17 | 10.24 | 4.12 | 2.76 | 1.24 |
| pydantic_local @v2_base | 17 | 3/17 | 3/17 | 3/17 | 17/17 | 14.07 | 4.24 | 2.41 | 0.18 |
| pydantic_mcp @v2_base | 20 | 7/20 | 7/19 | 6/19 | 20/20 | 14.6 | 4.15 | 2.45 | 0.1 |
| pydantic_local [prompted] @v2_prompted | 17 | 15/17 | 17/17 | 15/17 | 17/17 | 6.61 | 2.41 | 2.47 | 0.59 |
| pydantic_mcp [prompted] @v2_prompted | 20 | 18/20 | 19/19 | 17/19 | 20/20 | 9.26 | 2.5 | 2.5 | 0.5 |
| smolagents [verificada] @v2_verificada | 17 | 12/17 | 15/17 | 15/17 | 17/17 | 11.15 | 4.82 | 2.76 | 2.06 |
| pydantic_local [verificada+prompted] @v2_verificada | 17 | 15/17 | 15/17 | 15/17 | 17/17 | 6.6 | 2.65 | 2.47 | 0.82 |
| pydantic_mcp [verificada+prompted] @v2_verificada | 20 | 18/20 | 17/19 | 17/19 | 20/20 | 9.53 | 2.7 | 2.55 | 0.7 |
| smolagents [verificada] @v3_verificada | 17 | 14/17 | 17/17 | 17/17 | 17/17 | 10.52 | 4.24 | 2.76 | 1.35 |
| pydantic_local [verificada+prompted] @v3_verificada | 17 | 17/17 | 17/17 | 17/17 | 17/17 | 6.56 | 2.41 | 2.47 | 0.59 |
| pydantic_mcp [verificada+prompted] @v3_verificada | 20 | 20/20 | 19/19 | 19/19 | 20/20 | 9.64 | 2.5 | 2.5 | 0.5 |

