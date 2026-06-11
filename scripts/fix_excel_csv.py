"""
fix_excel_csv.py – naprawia pliki CSV uszkodzone przez Excel.

Excel przy Ctrl+H może scalić wartości boolean w jeden string
lub zmienić separator. Skrypt rekonstruuje pliki ze źródłowych
ghost_armada_iran.csv i shadow_fleet_russia.csv.

Użycie:
    python scripts/fix_excel_csv.py
"""

from pathlib import Path
import pandas as pd

DATA_DIR = Path("data")


def fix_shadow_fleet_combined():
    """Regeneruje shadow_fleet_combined.csv ze źródłowych plików."""
    iran_path   = DATA_DIR / "ghost_armada_iran.csv"
    russia_path = DATA_DIR / "shadow_fleet_russia.csv"

    if not iran_path.exists() or not russia_path.exists():
        print("❌ Brak plików źródłowych ghost_armada_iran.csv lub shadow_fleet_russia.csv")
        return

    # Iran
    iran = pd.read_csv(iran_path, dtype=str)
    iran["fleet"] = "Iran"
    iran = iran.rename(columns={"vessel_name": "name", "current_flag_clean": "flag"})
    for c in ["name", "flag", "former_flags", "sanctioned", "false_flag", "date_added"]:
        if c not in iran.columns:
            iran[c] = None
    iran = iran[["mmsi", "imo", "name", "flag", "former_flags",
                 "sanctioned", "false_flag", "date_added", "fleet"]]

    # Rosja
    russia = pd.read_csv(russia_path, dtype=str)
    russia["fleet"]       = "Rosja"
    russia["sanctioned"]  = "False"
    russia["false_flag"]  = "False"
    russia["date_added"]  = None
    russia["former_flags"] = None
    col_map = {}
    for col in russia.columns:
        if "name" in col.lower() and "name" not in col_map.values():
            col_map[col] = "name"
        if "flag" in col.lower() and "flag" not in col_map.values():
            col_map[col] = "flag"
    russia = russia.rename(columns=col_map)
    for c in ["name", "flag"]:
        if c not in russia.columns:
            russia[c] = None
    russia = russia[["mmsi", "imo", "name", "flag", "former_flags",
                     "sanctioned", "false_flag", "date_added", "fleet"]]

    # połącz i deduplikuj po IMO
    combined = pd.concat([iran, russia], ignore_index=True)
    combined["imo"]  = combined["imo"].astype(str).str.strip()
    combined["mmsi"] = combined["mmsi"].astype(str).str.strip()
    combined = combined.sort_values("fleet")  # Iran przed Rosja
    combined = combined.drop_duplicates(subset=["imo"], keep="first")

    out = DATA_DIR / "shadow_fleet_combined.csv"
    combined.to_csv(out, index=False, encoding="utf-8")
    print(f"✅ {out.name}: {len(combined)} statków "
          f"(Iran: {(combined['fleet']=='Iran').sum()}, "
          f"Rosja: {(combined['fleet']=='Rosja').sum()})")


def fix_ais_matches():
    """
    Naprawia ais_shadow_matches.csv – usuwa scalenia i poprawia typy.
    Wymaga że plik jest czytelny (tylko uszkodzone wartości bool).
    """
    path = DATA_DIR / "ais_shadow_matches.csv"
    if not path.exists():
        print(f"❌ Brak {path}")
        return

    # próbuj różne kodowania
    for enc in ["utf-8", "utf-8-sig", "cp1250", "latin-1"]:
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc, low_memory=False)
            print(f"  Wczytano {path.name} jako {enc}: {len(df)} wierszy")
            break
        except Exception:
            continue
    else:
        print(f"❌ Nie można wczytać {path}")
        return

    # napraw kolumny boolean – zamień "True"/"False" na właściwe stringi
    for col in ["sanctioned", "false_flag"]:
        if col in df.columns:
            # jeśli kolumna zawiera scalony string, spróbuj naprawić
            if df[col].str.len().max() > 10:
                print(f"  ⚠️  Kolumna {col} jest scalona – ustawiam False dla wszystkich")
                df[col] = "False"

    # zamień Russia na Rosja
    if "fleet" in df.columns:
        df["fleet"] = df["fleet"].replace({"Russia": "Rosja"})
        print(f"  fleet values: {df['fleet'].value_counts().to_dict()}")

    df.to_csv(path, index=False, encoding="utf-8")
    print(f"✅ {path.name}: zapisano {len(df)} wierszy jako UTF-8")


def main():
    print("=== Naprawa plików CSV ===\n")
    print("1. Regeneracja shadow_fleet_combined.csv...")
    fix_shadow_fleet_combined()
    print()
    print("2. Naprawa ais_shadow_matches.csv...")
    fix_ais_matches()
    print("\n✅ Gotowe. Odśwież aplikację Streamlit.")


if __name__ == "__main__":
    main()
