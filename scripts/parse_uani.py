"""
Skrypt do parsowania plików HTML z listą Ghost Armada (UANI)
i eksportu do zbiorczego pliku CSV.

Użycie:
    python parse_uani.py --input_dir /ścieżka/do/plików/html --output ghost_armada_iran.csv

Wymagania:
    pip install beautifulsoup4 pandas
"""

import argparse
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup


def parse_uani_file(filepath: Path) -> list[dict]:
    """
    Parsuje pojedynczy plik HTML z listą Ghost Armada.
    Zwraca listę słowników z danymi statków.
    """
    with open(filepath, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    rows = []
    for tr in soup.select("table.views-table tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue

        imo = cells[0].get_text(strip=True)

        # nazwa statku i MMSI z linka do MarineTraffic
        link = cells[1].find("a")
        name = link.get_text(strip=True) if link else cells[1].get_text(strip=True)

        mmsi = None
        if link and link.get("href"):
            match = re.search(r"mmsi:(\d+)", link["href"])
            if match:
                mmsi = match.group(1)

        # sanctioned = klasa "sanctioned" ale nie "not_sanctioned"
        classes = link.get("class", []) if link else []
        sanctioned = "sanctioned" in classes and "not_sanctioned" not in classes

        date_tag = cells[2].find("time")
        date_added = date_tag.get_text(strip=True) if date_tag else cells[2].get_text(strip=True)

        current_flag = cells[3].get_text(strip=True)
        former_flags = cells[4].get_text(strip=True)

        rows.append(
            {
                "imo": imo,
                "vessel_name": name,
                "mmsi": mmsi,
                "sanctioned": sanctioned,
                "date_added": date_added,
                "current_flag": current_flag,
                "former_flags": former_flags,
            }
        )

    return rows


def parse_all_files(input_dir: Path) -> pd.DataFrame:
    """
    Przetwarza wszystkie pliki HTML w podanym katalogu.
    Usuwa duplikaty po IMO (ten sam statek może być na kilku stronach paginacji).
    """
    html_files = sorted(input_dir.glob("*.html"))

    if not html_files:
        raise FileNotFoundError(f"Brak plików HTML w katalogu: {input_dir}")

    all_rows = []
    for filepath in html_files:
        rows = parse_uani_file(filepath)
        print(f"  {filepath.name}: {len(rows)} statków")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)

    # usuń duplikaty – ten sam statek może być na kilku stronach paginacji
    before = len(df)
    df = df.drop_duplicates(subset=["imo"])
    after = len(df)
    print(f"\nUsunięto {before - after} duplikatów (ten sam IMO na wielu stronach)")

    # konwersja daty
    df["date_added"] = pd.to_datetime(df["date_added"], errors="coerce")

    # flaga (FALSE) oznacza fałszywą banderę – wydziel jako osobną kolumnę
    df["false_flag"] = df["current_flag"].str.contains(r"\(FALSE\)", na=False)
    df["current_flag_clean"] = df["current_flag"].str.replace(r"\s*\(FALSE\)", "", regex=True).str.strip()

    return df


def main():
    parser = argparse.ArgumentParser(description="Parsuj pliki HTML UANI Ghost Armada do CSV")
    parser.add_argument("--input_dir", type=Path, required=True, help="Katalog z plikami HTML")
    parser.add_argument("--output", type=Path, default=Path("ghost_armada_iran.csv"), help="Plik wyjściowy CSV")
    args = parser.parse_args()

    print(f"Przetwarzam pliki HTML z: {args.input_dir}\n")
    df = parse_all_files(args.input_dir)

    df.to_csv(args.output, index=False)

    print(f"\n✅ Gotowe! Zapisano {len(df)} statków do: {args.output}")
    print(f"\nPodgląd danych:")
    print(df.head())
    print(f"\nKolumny: {list(df.columns)}")
    print(f"\nStatki z fałszywą banderą: {df['false_flag'].sum()}")
    print(f"Statki objęte sankcjami (OFAC): {df['sanctioned'].sum()}")
    print(f"Zakres dat dodania: {df['date_added'].min().date()} – {df['date_added'].max().date()}")


if __name__ == "__main__":
    main()