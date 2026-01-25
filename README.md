# Phydroperiod

Librería Python para calcular el hidroperiodo (días de inundación) a partir de series temporales de máscaras de agua.

## Instalación

```bash
pip install phydroperiod
```

O para desarrollo:

```bash
git clone https://github.com/Digdgeo/phydroperiod.git
cd phydroperiod
pip install -e ".[dev]"
```

## Uso básico

```python
from phydroperiod import compute_hydroperiod

# Calcular hidroperiodo desde un directorio con máscaras de agua
results = compute_hydroperiod("/path/to/water_masks")

print(f"Hidroperiodo: {results['hydroperiod']}")
print(f"Días válidos: {results['valid_days']}")
print(f"Normalizado (0-365): {results['normalized']}")
```

## Requisitos de las máscaras

- Formato: GeoTIFF (.tif)
- Valores: binarios (0 = seco, 1 = agua)
- Nombres: deben empezar con fecha YYYYMMDD (ej: `20200915_flood.tif`)

## Funciones disponibles

### `compute_hydroperiod(input_path, output_path=None, normalize=True)`

Pipeline completo que ejecuta todos los pasos:

```python
from phydroperiod import compute_hydroperiod

results = compute_hydroperiod(
    input_path="/path/to/masks",
    output_path="/path/to/output",  # opcional
    normalize=True,  # genera hidroperiodo normalizado a 365 días
)
```

### Funciones individuales

```python
from phydroperiod import (
    calculate_scene_weights,
    process_masks,
    accumulate_hydroperiod,
    normalize_hydroperiod,
)

# 1. Calcular pesos por escena
weights = calculate_scene_weights(mask_files)

# 2. Procesar máscaras (genera productos intermedios)
intermediate_dir = process_masks(input_path, weights=weights)

# 3. Acumular hidroperiodo total
hydroperiod_path, valid_days_path = accumulate_hydroperiod(intermediate_dir)

# 4. Normalizar a 365 días
normalized_path = normalize_hydroperiod(output_path)
```

## Ciclo hidrológico

El cálculo se basa en el ciclo hidrológico que va del 1 de septiembre al 31 de agosto del año siguiente. Cada escena recibe un peso proporcional basado en su posición temporal dentro del ciclo.

## Productos generados

| Archivo | Descripción |
|---------|-------------|
| `*_flood_rec.tif` | Días de inundación por escena |
| `*_dry_rec.tif` | Días secos por escena |
| `*_valid_rec.tif` | Días válidos por escena |
| `hydroperiod_YYYY_YYYY+1.tif` | Hidroperiodo acumulado |
| `valid_days_YYYY_YYYY+1.tif` | Días válidos acumulados |
| `hydroperiod_nor_YYYY_YYYY+1.tif` | Hidroperiodo normalizado (0-365) |

## Roadmap

- [ ] Integración con Google Earth Engine para obtener máscaras de agua
- [ ] Integración con Ndvi2Gif para generar máscaras automáticamente
- [ ] CLI para uso desde terminal
- [ ] Soporte para múltiples ciclos hidrológicos

## Licencia

MIT
