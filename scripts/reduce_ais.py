"""
reduce_ais.py – redukuje rozmiar ais_shadow_matches.csv do wdrożenia.

Zostawia tylko kolumny używane przez aplikację, usuwa duplikaty
i zapisuje jako Parquet (5-10x mniejszy niż CSV).

Użycie:
    python scripts/reduce_ais.py

Wymagania:
    pip install pandas pyarrow
"""

from pathlib import Path
import pandas as pd

DATA_DIR = Path("data")

# kolumny których aplikacja rzeczywiście używa
KEEP_COLS = [
    "mmsi",
    "timestamp",
    "latitude",
    "longitude",
    "sog",
    "fleet",
    "name_x",       # nazwa statku z AIS
    "ais_source",
]

def main():
    src  = DATA_DIR / "ais_shadow_matches.csv"
    dst_parquet = DATA_DIR / "ais_shadow_matches.parquet"
    dst_csv     = DATA_DIR / "ais_shadow_matches_small.csv"

    print(f"Wczytuję {src} ...")
    df = pd.read_csv(src, dtype={"mmsi": str}, low_memory=False)
    print(f"  Wierszy: {len(df):,}  |  Kolumn: {len(df.columns)}")
    print(f"  Rozmiar: {df.memory_usage(deep=True).sum() / 1e6:.0f} MB")

    # zostaw tylko potrzebne kolumny
    cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols]

    # popraw typy
    df["timestamp"] = pd.to_datetime(df["timestamp"], dayfirst=True, errors="coerce")
    df["latitude"]  = pd.to_numeric(df["latitude"],  errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["sog"]       = pd.to_numeric(df["sog"],       errors="coerce")
    df["mmsi"]      = df["mmsi"].astype(str).str.strip()

    # usuń wiersze bez pozycji lub timestamp
    before = len(df)
    df = df.dropna(subset=["timestamp", "latitude", "longitude"])
    print(f"\n  Usunięto {before - len(df):,} wierszy bez pozycji/timestamp")

    # usuń duplikaty (ten sam statek, ta sama sekunda, ta sama pozycja)
    before = len(df)
    df = df.drop_duplicates(subset=["mmsi", "timestamp", "latitude", "longitude"])
    print(f"  Usunięto {before - len(df):,} duplikatów")

    print(f"\n  Wierszy po redukcji: {len(df):,}")
    print(f"  Kolumn: {len(df.columns)} {list(df.columns)}")
    print(f"  Rozmiar w pamięci: {df.memory_usage(deep=True).sum() / 1e6:.0f} MB")

    # zapisz jako Parquet (główny format dla aplikacji)
    df.to_parquet(dst_parquet, index=False, compression="snappy")
    size_parquet = dst_parquet.stat().st_size / 1e6
    print(f"\n✅ Parquet: {dst_parquet}  ({size_parquet:.1f} MB)")

    # zapisz też jako CSV (backup / kompatybilność)
    df.to_csv(dst_csv, index=False)
    size_csv = dst_csv.stat().st_size / 1e6
    print(f"✅ CSV:     {dst_csv}  ({size_csv:.1f} MB)")

    print(f"\nRedukcja: 302 MB → {size_parquet:.0f} MB Parquet / {size_csv:.0f} MB CSV")

if __name__ == "__main__":
    main()
