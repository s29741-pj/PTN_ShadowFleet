"""
generate_map_sample.py – generuje zafiksowaną próbkę danych AIS do mapy.

Zamiast losować 50k punktów przy każdym uruchomieniu aplikacji
(kosztowne na dużym pliku Parquet), generujemy próbkę raz i zapisujemy
jako osobny, mały plik. Aplikacja wczytuje go bezpośrednio.

Użycie:
    python scripts/generate_map_sample.py
"""

from pathlib import Path
import pandas as pd

DATA_DIR = Path("data")
SAMPLE_SIZE = 50_000
RANDOM_STATE = 42

def main():
    src = DATA_DIR / "ais_shadow_matches.parquet"
    dst = DATA_DIR / "ais_map_sample.parquet"

    print(f"Wczytuję {src} ...")
    df = pd.read_parquet(src)
    print(f"  Wierszy: {len(df):,}")

    df = df.dropna(subset=["latitude", "longitude"])
    sample = df.sample(n=min(SAMPLE_SIZE, len(df)), random_state=RANDOM_STATE)

    sample.to_parquet(dst, index=False, compression="snappy")
    print(f"✅ Zapisano {len(sample):,} wierszy → {dst}")
    print(f"   Rozmiar: {dst.stat().st_size / 1e6:.2f} MB")

if __name__ == "__main__":
    main()
