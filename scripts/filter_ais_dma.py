"""
Skrypt do filtrowania plików AIS z Danish Maritime Authority (DMA).
Wyciąga wyłącznie rekordy gdzie Ship type = Tanker.

Źródło danych: http://aisdata.ais.dk/
Format pliku: CSV z nagłówkiem, separator przecinek, encoding latin-1

Użycie:
    python filter_ais_dma.py --input aisdk-2025-01-15.csv --output tankers_2025-01-15.csv

Wymagania:
    pip install pandas
"""

import argparse
from pathlib import Path

import pandas as pd


# Kolumny które nas interesują – reszta jest odrzucana żeby oszczędzić RAM
COLUMNS_TO_KEEP = [
    "# Timestamp",
    "MMSI",
    "Latitude",
    "Longitude",
    "Navigational status",
    "SOG",       # prędkość nad dnem (węzły)
    "COG",       # kurs nad dnem
    "Heading",
    "IMO",
    "Name",
    "Ship type",
    "Draught",
    "Destination",
]

# DMA używa tego separatora i encodingu
CSV_SEPARATOR = ","
CSV_ENCODING = "latin-1"

# Rozmiar chunka – czytamy plik partiami żeby nie zapchać RAM
# 500k wierszy to ok. 200-300 MB RAM, bezpieczne dla zwykłego laptopa
CHUNK_SIZE = 500_000


def filter_file(input_path: Path, output_path: Path) -> int:
    """
    Filtruje pojedynczy plik AIS, zapisuje tylko tankowce.
    Zwraca liczbę zapisanych rekordów.
    """
    total_rows = 0
    tanker_rows = 0
    first_chunk = True

    print(f"Przetwarzam: {input_path.name}")

    reader = pd.read_csv(
        input_path,
        sep=CSV_SEPARATOR,
        encoding=CSV_ENCODING,
        chunksize=CHUNK_SIZE,
        usecols=lambda c: c in COLUMNS_TO_KEEP,
        low_memory=False,
    )

    for chunk in reader:
        total_rows += len(chunk)

        # filtruj tankowce (case-insensitive)
        mask = chunk["Ship type"].str.contains("tanker", case=False, na=False)
        tankers = chunk[mask]

        if len(tankers) == 0:
            continue

        # zapisz do CSV – nagłówek tylko przy pierwszym chunku
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

    return tanker_rows


def main():
    parser = argparse.ArgumentParser(description="Filtruj dane AIS DMA – tylko tankowce")
    parser.add_argument("--input", type=Path, required=True, help="Plik wejściowy CSV")
    parser.add_argument("--output", type=Path, required=True, help="Plik wyjściowy CSV")
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku: {args.input}")

    filter_file(args.input, args.output)


if __name__ == "__main__":
    main()
