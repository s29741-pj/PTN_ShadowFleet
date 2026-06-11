"""
Skrypt do łączenia list floty cieni (GUR + UANI) z danymi pozycyjnymi AIS.

Wejście:
    - ghost_armada_iran.csv      – lista irańskiej floty cieni (UANI)
    - shadow_fleet_russia.csv    – lista rosyjskiej floty cieni (GUR)

Wyjście:
    - shadow_fleet_combined.csv  – połączona lista obu flot cieni
    - ais_shadow_matches.csv     – rekordy AIS należące do floty cieni

Użycie:
    python merge_shadow_fleet.py

Wymagania:
    pip install pandas
"""

from pathlib import Path

import pandas as pd

# ── ścieżki ───────────────────────────────────────────────────────────────────

DATA_DIR = Path("data")

IRAN_FLEET_PATH = DATA_DIR / "ghost_armada_iran.csv"
RUSSIA_FLEET_PATH = DATA_DIR / "shadow_fleet_russia.csv"
AIS_DMA_DIR = DATA_DIR / "ais_dma"

OUT_COMBINED = DATA_DIR / "shadow_fleet_combined.csv"
OUT_MATCHES = DATA_DIR / "ais_shadow_matches.csv"


# ── krok 1: wczytaj i ujednolicaj listy flot cieni ───────────────────────────


def load_iran_fleet(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"mmsi": str, "imo": str})
    df["fleet"] = "Iran"
    df = df.rename(
        columns={
            "vessel_name": "name",
            "current_flag_clean": "flag",
        }
    )
    return df[
        [
            "mmsi",
            "imo",
            "name",
            "flag",
            "sanctioned",
            "false_flag",
            "date_added",
            "fleet",
        ]
    ]


def load_russia_fleet(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"mmsi": str, "imo": str})
    df["fleet"] = "Rosja"

    # nazwy kolumn mogą się różnić w zależności od struktury Vessels1.db
    col_map = {}
    for col in df.columns:
        low = col.lower()
        if "name" in low and "name" not in col_map.values():
            col_map[col] = "name"
        if "flag" in low and "flag" not in col_map.values():
            col_map[col] = "flag"
    df = df.rename(columns=col_map)

    for c in ["name", "flag", "date_added"]:
        if c not in df.columns:
            df[c] = None

    df["sanctioned"] = False
    df["false_flag"] = False

    return df[
        [
            "mmsi",
            "imo",
            "name",
            "flag",
            "sanctioned",
            "false_flag",
            "date_added",
            "fleet",
        ]
    ]


def combine_fleets(iran: pd.DataFrame, russia: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([iran, russia], ignore_index=True)
    combined["mmsi"] = combined["mmsi"].str.strip()

    before = len(combined)
    combined = combined.drop_duplicates(subset=["mmsi"])
    dropped = before - len(combined)
    if dropped:
        print(f"  Usunięto {dropped} duplikatów (ten sam MMSI na obu listach)")

    return combined


# ── krok 2: wczytaj dane AIS z katalogu ──────────────────────────────────────


def load_ais_dir(directory: Path, source_label: str) -> pd.DataFrame | None:
    if not directory.exists():
        print(f"  ⚠️  Brak katalogu: {directory} – pomijam")
        return None

    files = sorted(directory.glob("*.csv"))
    if not files:
        print(f"  ⚠️  Brak plików CSV w {directory} – pomijam")
        return None

    print(
        f"  Wczytywanie {source_label} ({len(files)} plików) ...", end=" ", flush=True
    )

    parts = []
    for f in files:
        df = pd.read_csv(f, dtype={"mmsi": str}, low_memory=False)
        df.columns = df.columns.str.lower().str.strip()

        if "mmsi" not in df.columns:
            print(f"\n  ⚠️  Brak kolumny 'mmsi' w {f.name} – pomijam ten plik")
            continue

        df["mmsi"] = df["mmsi"].astype(str).str.strip()
        df["ais_source"] = source_label
        parts.append(df)

    if not parts:
        return None

    combined = pd.concat(parts, ignore_index=True)

    # ujednolicenie kolumny timestamp
    ts_col = next((c for c in combined.columns if "time" in c or "date" in c), None)
    if ts_col:
        combined = combined.rename(columns={ts_col: "timestamp"})
        combined["timestamp"] = pd.to_datetime(
            combined["timestamp"], dayfirst=True, errors="coerce"
        )

    print(f"{len(combined):,} rekordów")
    return combined


# ── krok 3: merge AIS z listą floty cieni po MMSI ────────────────────────────


def match_shadow_fleet(ais: pd.DataFrame, fleet: pd.DataFrame) -> pd.DataFrame:
    matched = ais.merge(
        fleet[["mmsi", "name", "flag", "fleet", "sanctioned", "false_flag"]],
        on="mmsi",
        how="inner",
    )
    return matched


# ── main ──────────────────────────────────────────────────────────────────────


def main():
    print("\n=== Krok 1: Łączenie list flot cieni ===")

    iran = (
        load_iran_fleet(IRAN_FLEET_PATH) if IRAN_FLEET_PATH.exists() else pd.DataFrame()
    )
    russia = (
        load_russia_fleet(RUSSIA_FLEET_PATH)
        if RUSSIA_FLEET_PATH.exists()
        else pd.DataFrame()
    )

    if iran.empty and russia.empty:
        raise FileNotFoundError(
            "Brak obu plików list floty cieni. Sprawdź ścieżki w DATA_DIR."
        )

    if iran.empty:
        print("  ⚠️  Brak ghost_armada_iran.csv – używam tylko listy rosyjskiej")
        combined = russia
    elif russia.empty:
        print("  ⚠️  Brak shadow_fleet_russia.csv – używam tylko listy irańskiej")
        combined = iran
    else:
        combined = combine_fleets(iran, russia)

    combined.to_csv(OUT_COMBINED, index=False)
    print(f"  ✅ Łącznie {len(combined)} statków → {OUT_COMBINED.name}")
    print(
        f"     Iran: {(combined['fleet'] == 'Iran').sum()} | "
        f"Rosja: {(combined['fleet'] == 'Rosja').sum()}"
    )

    print("\n=== Krok 2: Wczytywanie danych AIS ===")

    ais_parts = []
    for directory, label in [(AIS_DMA_DIR, "DMA")]:
        df = load_ais_dir(directory, label)
        if df is not None:
            ais_parts.append(df)

    if not ais_parts:
        print("  ⚠️  Brak danych AIS. Wygenerowano tylko shadow_fleet_combined.csv.")
        return

    ais_all = pd.concat(ais_parts, ignore_index=True)
    print(f"  Łącznie rekordów AIS: {len(ais_all):,}")

    print("\n=== Krok 3: Dopasowanie do floty cieni ===")

    matches = match_shadow_fleet(ais_all, combined)
    matches.to_csv(OUT_MATCHES, index=False)

    print(f"  ✅ Dopasowano {len(matches):,} rekordów AIS należących do floty cieni")
    print(f"     Unikalne statki w danych: {matches['mmsi'].nunique()}")
    print(f"     → {OUT_MATCHES.name}")

    print("\n=== Podsumowanie ===")
    if len(matches):
        print("\nTop 10 najaktywniejszych statków floty cieni w danych AIS:")
        name_col = next((c for c in matches.columns if c.startswith("name")), "mmsi")
        top = (
            matches.groupby(["mmsi", name_col, "fleet"])
            .size()
            .reset_index(name="ping_count")
            .sort_values("ping_count", ascending=False)
            .head(10)
        )
        print(top.to_string(index=False))


if __name__ == "__main__":
    main()
