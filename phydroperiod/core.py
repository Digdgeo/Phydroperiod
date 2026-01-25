"""
Funciones core para el cálculo del hidroperiodo.

El hidroperiodo representa el número de días que un píxel permanece inundado
durante un ciclo hidrológico (1 septiembre - 31 agosto).
"""

import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import rasterio
from rasterio.profiles import Profile


def calculate_scene_weights(
    mask_files: List[str],
    hydrological_year_start: Tuple[int, int] = (9, 1),
) -> Dict[str, float]:
    """Calcula el peso en días para cada escena dentro de un ciclo hidrológico.

    Distribuye 365 días entre las escenas disponibles, asignando a cada una
    un rango de días proporcional a su posición temporal.

    Args:
        mask_files: Lista de rutas a archivos de máscaras. Los nombres deben
            empezar con formato YYYYMMDD (ej: 20200315_flood.tif).
        hydrological_year_start: Tupla (mes, día) del inicio del ciclo
            hidrológico. Por defecto (9, 1) = 1 de septiembre.

    Returns:
        Diccionario {fecha_escena: días_asignados}.

    Example:
        >>> files = ["20200915_flood.tif", "20201015_flood.tif", "20201115_flood.tif"]
        >>> weights = calculate_scene_weights(files)
        >>> print(weights)
        {'20200915': 30.0, '20201015': 30.5, '20201115': 304.5}
    """
    # Extraer fechas de los nombres de archivo
    scene_dates = []
    for f in mask_files:
        basename = os.path.basename(f)
        date_str = basename[:8]
        scene_dates.append(date_str)

    scene_dates = sorted(set(scene_dates))

    if not scene_dates:
        return {}

    # Determinar año base del ciclo hidrológico
    years = [int(d[:4]) for d in scene_dates]
    base_year = min(years)
    start_month, start_day = hydrological_year_start
    d0 = date(base_year, start_month, start_day)

    # Calcular días desde el inicio del ciclo para cada escena
    days_from_start = []
    for date_str in scene_dates:
        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        d1 = date(year, month, day)
        delta = d1 - d0
        days_from_start.append(delta.days)

    # Calcular puntos medios entre escenas consecutivas
    midpoints = []
    for i in range(len(days_from_start) - 1):
        mid = (days_from_start[i + 1] - days_from_start[i]) / 2
        midpoints.append(mid)

    # Calcular puntos de corte acumulados
    cutpoints = []
    for i, mid in enumerate(midpoints):
        cutpoints.append(mid + days_from_start[i])

    # Calcular valor (días) para cada escena
    values = []
    if cutpoints:
        values.append(cutpoints[0])
        for i in range(len(cutpoints) - 1):
            values.append(cutpoints[i + 1] - cutpoints[i])
        values.append(365 - cutpoints[-1])
    else:
        # Solo una escena, asignar 365 días
        values.append(365)

    return dict(zip(scene_dates, values))


def process_masks(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    weights: Optional[Dict[str, float]] = None,
    water_value: int = 1,
    dry_value: int = 0,
    nodata_value: int = 2,
) -> Path:
    """Procesa máscaras de agua generando productos intermedios por escena.

    Para cada máscara genera tres productos:
    - *_flood_rec.tif: Días de inundación (píxeles con water_value)
    - *_dry_rec.tif: Días secos (píxeles con dry_value)
    - *_valid_rec.tif: Días válidos (flood + dry, excluyendo nodata)

    Args:
        input_path: Directorio con máscaras de agua (.tif).
        output_path: Directorio de salida. Si no se especifica,
            se crea un subdirectorio 'output' en input_path.
        weights: Diccionario de pesos por escena. Si no se especifica,
            se calcula automáticamente.
        water_value: Valor que representa agua/inundación en las máscaras.
            Por defecto 1.
        dry_value: Valor que representa suelo seco en las máscaras.
            Por defecto 0.
        nodata_value: Valor que representa nodata (nubes, sombras, etc.).
            Por defecto 2. Estos píxeles se excluyen del cálculo.

    Returns:
        Path al directorio de salida con los productos intermedios.
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path / "output"
    else:
        output_path = Path(output_path)

    output_path.mkdir(parents=True, exist_ok=True)

    # Obtener lista de máscaras
    mask_files = sorted([f for f in input_path.glob("*.tif")])

    if not mask_files:
        raise ValueError(f"No se encontraron archivos .tif en {input_path}")

    # Calcular pesos si no se proporcionan
    if weights is None:
        weights = calculate_scene_weights([str(f) for f in mask_files])

    # Procesar cada máscara
    for mask_file in mask_files:
        date_str = mask_file.name[:8]
        weight = weights.get(date_str, 0)

        if weight == 0:
            continue

        with rasterio.open(mask_file) as src:
            data = src.read()
            profile = src.profile.copy()
            profile.update(dtype=rasterio.float32)

            # Inundadas: donde píxel = water_value, asignar peso
            flood_data = np.where(data == water_value, weight, 0).astype(np.float32)

            # Secas: donde píxel = dry_value, asignar peso
            dry_data = np.where(data == dry_value, weight, 0).astype(np.float32)

            # Válidas: suma de flood + dry (nodata queda excluido automáticamente)
            valid_data = (flood_data + dry_data).astype(np.float32)

            # Guardar productos
            base_name = mask_file.stem
            _write_raster(output_path / f"{base_name}_flood_rec.tif", flood_data, profile)
            _write_raster(output_path / f"{base_name}_dry_rec.tif", dry_data, profile)
            _write_raster(output_path / f"{base_name}_valid_rec.tif", valid_data, profile)

    return output_path


def accumulate_hydroperiod(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
) -> Tuple[Path, Path]:
    """Acumula los productos intermedios para generar hidroperiodo total.

    Suma todos los *_flood_rec.tif y *_valid_rec.tif para generar:
    - hydroperiod_YYYY_YYYY+1.tif: Días totales de inundación
    - valid_days_YYYY_YYYY+1.tif: Días totales válidos

    Args:
        input_path: Directorio con productos intermedios (*_flood_rec.tif, *_valid_rec.tif).
        output_path: Directorio de salida. Si no se especifica, se usa el padre de input_path.

    Returns:
        Tupla (path_hydroperiod, path_valid_days).
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.parent
    else:
        output_path = Path(output_path)

    output_path.mkdir(parents=True, exist_ok=True)

    # Obtener archivos
    flood_files = sorted(input_path.glob("*_flood_rec.tif"))
    valid_files = sorted(input_path.glob("*_valid_rec.tif"))

    if not flood_files:
        raise ValueError(f"No se encontraron archivos *_flood_rec.tif en {input_path}")

    # Determinar ciclo hidrológico
    first_file = flood_files[0].name
    year1 = first_file[:4]
    year2 = str(int(year1) + 1)
    cycle_suffix = f"_{year1}_{year2}"

    # Leer primer archivo para obtener forma y metadata
    with rasterio.open(flood_files[0]) as src:
        shape = src.read().shape
        profile = src.profile.copy()
        profile.update(dtype=rasterio.float32)

    # Acumular flood
    flood_sum = np.zeros(shape, dtype=np.float32)
    for f in flood_files:
        with rasterio.open(f) as src:
            flood_sum += src.read()

    # Acumular valid
    valid_sum = np.zeros(shape, dtype=np.float32)
    for f in valid_files:
        with rasterio.open(f) as src:
            valid_sum += src.read()

    # Guardar resultados
    hydroperiod_path = output_path / f"hydroperiod{cycle_suffix}.tif"
    valid_days_path = output_path / f"valid_days{cycle_suffix}.tif"

    _write_raster(hydroperiod_path, flood_sum, profile)
    _write_raster(valid_days_path, valid_sum, profile)

    return hydroperiod_path, valid_days_path


def normalize_hydroperiod(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    target_days: int = 365,
) -> Path:
    """Normaliza el hidroperiodo a un número objetivo de días.

    Calcula: hydroperiod_normalizado = (hydroperiod / valid_days) * target_days

    Args:
        input_path: Directorio con hydroperiod_*.tif y valid_days_*.tif.
        output_path: Directorio de salida. Si no se especifica, se usa input_path.
        target_days: Días objetivo para normalización (por defecto 365).

    Returns:
        Path al archivo normalizado.
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path
    else:
        output_path = Path(output_path)

    output_path.mkdir(parents=True, exist_ok=True)

    # Buscar archivos de hydroperiod y valid_days
    hydroperiod_file = None
    valid_days_file = None
    cycle = None

    for f in input_path.iterdir():
        if f.name.startswith("hydroperiod") and f.suffix == ".tif" and "nor" not in f.name:
            hydroperiod_file = f
            # Extraer ciclo del nombre
            parts = f.stem.split("_")
            if len(parts) >= 3:
                cycle = f"{parts[1]}_{parts[2]}"
        elif f.name.startswith("valid_days") and f.suffix == ".tif":
            valid_days_file = f

    if hydroperiod_file is None or valid_days_file is None:
        raise ValueError(
            f"No se encontraron archivos hydroperiod_*.tif y valid_days_*.tif en {input_path}"
        )

    with rasterio.open(hydroperiod_file) as hyd_src:
        hyd_data = hyd_src.read()
        profile = hyd_src.profile.copy()

        with rasterio.open(valid_days_file) as val_src:
            val_data = val_src.read()

            # Normalizar evitando división por cero
            with np.errstate(divide="ignore", invalid="ignore"):
                normalized = np.true_divide(hyd_data, val_data) * target_days
                normalized = np.where(np.isfinite(normalized), normalized, 0)
                normalized = np.clip(normalized, 0, target_days).astype(np.float32)

    output_file = output_path / f"hydroperiod_nor_{cycle}.tif"
    _write_raster(output_file, normalized, profile)

    return output_file


def compute_hydroperiod(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    normalize: bool = True,
    target_days: int = 365,
    water_value: int = 1,
    dry_value: int = 0,
    nodata_value: int = 2,
) -> Dict[str, Path]:
    """Pipeline completo para calcular el hidroperiodo.

    Ejecuta todos los pasos del cálculo:
    1. Calcula pesos por escena
    2. Procesa máscaras generando productos intermedios
    3. Acumula hidroperiodo total
    4. (Opcional) Normaliza a días objetivo

    Args:
        input_path: Directorio con máscaras de agua (.tif).
            Nombres con formato YYYYMMDD*.tif.
        output_path: Directorio base de salida. Si no se especifica,
            se crean subdirectorios en input_path.
        normalize: Si True, genera también el hidroperiodo normalizado.
        target_days: Días objetivo para normalización.
        water_value: Valor que representa agua/inundación en las máscaras.
            Por defecto 1.
        dry_value: Valor que representa suelo seco en las máscaras.
            Por defecto 0.
        nodata_value: Valor que representa nodata (nubes, sombras, etc.).
            Por defecto 2. Estos píxeles se excluyen del cálculo.

    Returns:
        Diccionario con rutas a los productos generados:
        - 'intermediate_dir': directorio con productos intermedios
        - 'hydroperiod': ruta al hidroperiodo acumulado
        - 'valid_days': ruta a días válidos acumulados
        - 'normalized': ruta al hidroperiodo normalizado (si normalize=True)

    Example:
        >>> results = compute_hydroperiod("/path/to/masks")
        >>> print(f"Hydroperiod: {results['hydroperiod']}")
        Hydroperiod: /path/to/masks/hydroperiod_2020_2021.tif
    """
    input_path = Path(input_path)

    if output_path is None:
        intermediate_path = input_path / "output"
        final_path = input_path
    else:
        output_path = Path(output_path)
        intermediate_path = output_path / "intermediate"
        final_path = output_path

    # Paso 1 y 2: Calcular pesos y procesar máscaras
    intermediate_dir = process_masks(
        input_path,
        intermediate_path,
        water_value=water_value,
        dry_value=dry_value,
        nodata_value=nodata_value,
    )

    # Paso 3: Acumular hidroperiodo
    hydroperiod_path, valid_days_path = accumulate_hydroperiod(
        intermediate_dir, final_path
    )

    results = {
        "intermediate_dir": intermediate_dir,
        "hydroperiod": hydroperiod_path,
        "valid_days": valid_days_path,
    }

    # Paso 4: Normalizar (opcional)
    if normalize:
        normalized_path = normalize_hydroperiod(final_path, final_path, target_days)
        results["normalized"] = normalized_path

    return results


def _write_raster(path: Path, data: np.ndarray, profile: Profile) -> None:
    """Escribe un array numpy como raster GeoTIFF."""
    profile.update(dtype=rasterio.float32)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(np.float32))
