"""
Skrypt do eksportu rosyjskiej floty cieni z bazy SQLite (FormerLab / GUR)
do pliku CSV gotowego do analizy.

Źródło danych:
    https://github.com/FormerLab/shadow-fleet-tracker-light
    Pobierz plik Vessels1.db z repozytorium.

Użycie:
    python parse_gur.py --input Vessels1.db --output shadow_fleet_russia.csv

Wymagania:
    pip install pandas
"""

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def inspect_database(conn: sqlite3.Connection) -> list[str]:
    """Wyświetla dostępne tabele i ich kolumny."""
    tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)
    print("Dostępne tabele:")
    for table in tables["name"]:
        cols = pd.read_sql(f"PRAGMA table_info({table})", conn)
        print(f"\n  [{table}]")
        for _, row in cols.iterrows():
            print(f"    - {row['name']} ({row['type']})")
    return tables["name"].tolist()


def export_vessels(conn: sqlite3.Connection, table_name: str) -> pd.DataFrame:
    """Eksportuje dane statków z podanej tabeli."""
    df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
    return df


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ujednolica i czyści dane:
    - nazwy kolumn na małe litery ze znakiem podkreślenia
    - usuwa duplikaty po MMSI jeśli kolumna istnieje
    - dodaje kolumnę źródła dla późniejszego merge z danymi UANI
    """
    # ujednolicenie nazw kolumn
    df.columns = (
        df.columns
        .str.lower()
        .str.strip()
        .str.replace(r"\s+", "_", regex=True)
        .str.replace(r"[^\w]", "_", regex=True)
    )

    print(f"\nKolumny po czyszczeniu: {list(df.columns)}")

    # usuń duplikaty po MMSI jeśli kolumna istnieje
    mmsi_col = next((c for c in df.columns if "mmsi" in c), None)
    if mmsi_col:
        before = len(df)
        df = df.drop_duplicates(subset=[mmsi_col])
        print(f"Usunięto {before - len(df)} duplikatów po {mmsi_col}")

    # dodaj etykietę źródła – przyda się przy merge z listą UANI
    df["fleet_source"] = "GUR_Russia"

    return df


def main():
    parser = argparse.ArgumentParser(description="Eksportuj rosyjską flotę cieni z SQLite do CSV")
    parser.add_argument("--input", type=Path, required=True, help="Ścieżka do pliku Vessels1.db")
    parser.add_argument("--output", type=Path, default=Path("shadow_fleet_russia.csv"), help="Plik wyjściowy CSV")
    parser.add_argument("--table", type=str, default=None, help="Nazwa tabeli (domyślnie: auto-detect)")
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku: {args.input}")

    print(f"Otwieranie bazy: {args.input}\n")
    conn = sqlite3.connect(args.input)

    # inspekcja bazy
    tables = inspect_database(conn)

    # wybór tabeli
    if args.table:
        table_name = args.table
    else:
        # auto-detect: szukaj tabeli z "vessel" lub "ship" w nazwie
        candidates = [t for t in tables if any(k in t.lower() for k in ["vessel", "ship", "fleet"])]
        if candidates:
            table_name = candidates[0]
        else:
            table_name = tables[0]
        print(f"\nAuto-wybrana tabela: '{table_name}'")
        print("Użyj --table NAZWA aby wybrać inną.")

    # eksport
    print(f"\nEksportuję dane z tabeli '{table_name}'...")
    df = export_vessels(conn, table_name)
    conn.close()

    print(f"Wczytano {len(df)} rekordów")

    # czyszczenie
    df = clean_dataframe(df)

    # zapis
    df.to_csv(args.output, index=False)

    print(f"\n✅ Gotowe! Zapisano {len(df)} statków do: {args.output}")
    print(f"\nPodgląd:")
    print(df.head(3).to_string())
    print(f"\nStatystyki:")
    print(f"  Łączna liczba statków: {len(df)}")

    # podsumowanie flag jeśli kolumna istnieje
    flag_col = next((c for c in df.columns if "flag" in c), None)
    if flag_col:
        print(f"\n  Top 10 bander ({flag_col}):")
        print(df[flag_col].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()