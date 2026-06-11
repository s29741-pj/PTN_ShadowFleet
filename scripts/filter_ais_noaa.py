"""
Skrypt do filtrowania plików AIS z NOAA MarineCadastre.
Wyciąga wyłącznie rekordy gdzie VesselType = 80-89 (tankowce wg ITU).

Źródło danych: https://noaaocm.blob.core.windows.net/ais/csv2/csv2025/
Format pliku: CSV (po rozpakowaniu .zst np. przez 7-Zip lub zstd.exe)
Nagłówek: MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,
          CallSign,VesselType,Status,Length,Width,Draft,Cargo,TransceiverClass

Kody VesselType dla tankowców (wg ITU):
    80 – Tanker
    81 – Tanker, Hazardous category A
    82 – Tanker, Hazardous category B
    83 – Tanker, Hazardous category C
    84 – Tanker, Hazardous category D
    85–88 – Tanker (reserved)
    89 – Tanker, No additional information

Użycie:
    python filter_ais_noaa.py --input ais-2025-01-15.csv --output tankers_2025-01-15.csv

Wymagania:
    pip install pandas
"""

import argparse
from pathlib import Path

import pandas as pd


# Kody VesselType odpowiadające tankowcom wg standardu ITU/AIS
TANKER_VESSEL_TYPES = set(range(80, 90))  # 80–89 włącznie

# Kolumny które zachowujemy – reszta odrzucana żeby oszczędzić RAM
COLUMNS_TO_KEEP = [
    "mmsi",
    "base_date_time",
    "latitude",
    "longitude",
    "sog",
    "cog",
    "heading",
    "vessel_name",
    "imo",
    "vessel_type",
    "status",
    "draft",
    "cargo",
]

# Rozmiar chunka – czytamy partiami żeby nie zapchać RAM
CHUNK_SIZE = 500_000


def filter_file(input_path: Path, output_path: Path) -> None:
    """
    Filtruje plik CSV, zapisuje tylko tankowce (VesselType 80–89).
    """
    total_rows = 0
    tanker_rows = 0
    first_chunk = True

    print(f"Przetwarzam: {input_path.name}")

    reader = pd.read_csv(
        input_path,
        chunksize=CHUNK_SIZE,
        usecols=lambda c: c in COLUMNS_TO_KEEP,
        low_memory=False,
    )

    for chunk in reader:
        total_rows += len(chunk)

        vessel_type_numeric = pd.to_numeric(chunk["vessel_type"], errors="coerce")
        mask = vessel_type_numeric.between(80, 89)
        tankers = chunk[mask].copy()

        if len(tankers) == 0:
            continue

        tankers.to_csv(
            output_path,
            mode="a" if not first_chunk else "w",
            header=first_chunk,
            index=False,
        )
        first_chunk = False
        tanker_rows += len(tankers)

    ratio = (tanker_rows / total_rows * 100) if total_rows > 0 else 0
    print(f"✅ {tanker_rows:,} tankowców / {total_rows:,} rekordów ({ratio:.1f}%)")
    print(f"   → zapisano: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Filtruj dane AIS NOAA – tylko tankowce (VesselType 80-89)")
    parser.add_argument("--input", type=Path, required=True, help="Plik wejściowy CSV")
    parser.add_argument("--output", type=Path, required=True, help="Plik wyjściowy CSV")
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku: {args.input}")

    filter_file(args.input, args.output)


if __name__ == "__main__":
    main()