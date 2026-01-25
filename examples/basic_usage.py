"""
Ejemplo básico de uso de la librería phydroperiod.

Este script muestra cómo calcular el hidroperiodo a partir de
un directorio con máscaras de agua.
"""

from pathlib import Path

from phydroperiod import compute_hydroperiod


def main():
    # Ruta al directorio con máscaras de agua
    # Las máscaras deben ser GeoTIFF binarios (0=seco, 1=agua)
    # con nombres que empiecen por YYYYMMDD
    masks_dir = Path("/path/to/water_masks")

    # Calcular hidroperiodo (pipeline completo)
    print(f"Procesando máscaras en: {masks_dir}")

    results = compute_hydroperiod(
        input_path=masks_dir,
        normalize=True,  # Normalizar a 365 días
    )

    # Mostrar resultados
    print("\nProductos generados:")
    print(f"  - Intermedios: {results['intermediate_dir']}")
    print(f"  - Hidroperiodo: {results['hydroperiod']}")
    print(f"  - Días válidos: {results['valid_days']}")
    print(f"  - Normalizado: {results['normalized']}")


if __name__ == "__main__":
    main()
