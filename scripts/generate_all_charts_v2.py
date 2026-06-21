"""
generate_all_charts.py – generuje wszystkie wykresy aplikacji jako pliki PNG.

Statyczna prezentacja: wszystkie obliczenia (filtrowanie, detekcja anomalii,
agregacje) wykonywane są raz, offline. Aplikacja Streamlit (app.py) tylko
wyświetla gotowe obrazy – brak jakichkolwiek obliczeń przy starcie czy
przy interakcji użytkownika.

Wyjście: katalog data/charts/ z plikami PNG, jeden per wykres.

Użycie:
    python scripts/generate_all_charts.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # backend bez GUI, szybszy do generowania plików
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from controller import FleetController
from visualizer import (
    plot_anomaly_summary,
    plot_anomaly_per_vessel,
    plot_activity_heatmap,
    plot_classification_society,
    plot_flag_changes_vs_age,
    plot_flag_distribution,
    plot_flag_hopping,
    plot_fleet_activity,
    plot_fleet_comparison,
    plot_fleet_growth,
    plot_hourly_activity,
    plot_inspections_analysis,
    plot_anomaly_map,
    plot_sog_boxplot,
    plot_sog_distribution,
    plot_tonnage_distribution,
    plot_transit_trends,
    plot_year_built_histogram,
)

DATA_DIR = Path(__file__).parent.parent / "data"
CHARTS_DIR = DATA_DIR / "charts"
CHARTS_DIR.mkdir(exist_ok=True)

DPI = 120


def save(fig: plt.Figure, name: str) -> None:
    """Zapisuje figurę jako PNG i zamyka ją (zwolnienie pamięci)."""
    path = CHARTS_DIR / f"{name}.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    size_kb = path.stat().st_size / 1024
    print(f"  ✅ {name}.png ({size_kb:.0f} KB)")


def main():
    print("Wczytuję dane...")
    ctrl = FleetController(data_dir=DATA_DIR)
    ctrl.load_all()

    vessel_path = DATA_DIR / "vessel_details_enriched.csv"
    vessels = pd.read_csv(vessel_path, dtype=str) if vessel_path.exists() else pd.DataFrame()

    print(f"  Floty cieni: {len(ctrl.fleet_data)} statków")
    print(f"  AIS: {len(ctrl.ais_data):,} rekordów")
    print(f"  Equasis: {len(vessels)} statków")

    # ── Tab 1: Przegląd ──────────────────────────────────────────────────
    print("\n=== Tab 1: Przegląd ===")
    save(plot_fleet_comparison(ctrl.fleet_data), "overview_fleet_comparison")
    save(plot_fleet_growth(ctrl.fleet_data), "overview_fleet_growth")
    save(plot_flag_distribution(ctrl.get_flag_distribution()), "overview_flag_distribution")

    # ── Tab 2: Trendy ────────────────────────────────────────────────────
    print("\n=== Tab 2: Trendy ===")
    save(plot_transit_trends(ctrl.transit_data), "trends_transit")

    activity = ctrl.get_activity_by_month(fleet="Rosja")
    if not activity.empty:
        save(plot_fleet_activity(activity, fleet="Rosja"), "trends_fleet_activity")
    else:
        print("  ⚠️  Brak danych aktywności – pomijam trends_fleet_activity")

    ais_rosja = ctrl.filter_ais(fleet="Rosja")
    if not ais_rosja.empty and "sog" in ais_rosja.columns:
        save(plot_sog_distribution(ais_rosja), "trends_sog_distribution")
        save(plot_sog_boxplot(ais_rosja), "trends_sog_boxplot")
        save(plot_activity_heatmap(ais_rosja, top_n=20), "trends_activity_heatmap")

    # zapisz też próbkę surowych danych do tabeli
    display_cols = [c for c in ["mmsi", "timestamp", "latitude", "longitude",
                                  "sog", "fleet", "name_x", "ais_source"]
                     if c in ais_rosja.columns]
    ais_rosja[display_cols].head(1000).to_parquet(
        DATA_DIR / "trends_raw_sample.parquet", index=False
    )
    print(f"  ✅ trends_raw_sample.parquet (1000 wierszy, {len(ais_rosja):,} łącznie)")

    # ── Tab 3: Anomalie ──────────────────────────────────────────────────
    print("\n=== Tab 3: Anomalie ===")
    summary = ctrl.get_anomaly_summary(fleet="Rosja")
    save(plot_anomaly_summary(summary), "anomalies_summary")

    anomaly_path = DATA_DIR / "anomaly_map_anomalies.parquet"
    tracks_path = DATA_DIR / "anomaly_map_tracks.parquet"

    if anomaly_path.exists() and tracks_path.exists():
        anomalies = pd.read_parquet(anomaly_path)
        tracks = pd.read_parquet(tracks_path)

        top_mmsi = (
            anomalies.dropna(subset=["latitude", "longitude"])
            .groupby("mmsi").size().nlargest(8).index.tolist()
        )

        save(plot_anomaly_per_vessel(anomalies, top_n=8), "anomalies_per_vessel")

        # wariant "wszystkie statki naraz"
        save(plot_anomaly_map(anomalies, tracks, top_n=8), "anomalies_map_all")

        # warianty per pojedynczy statek (do filtra w aplikacji)
        name_col_tmp = next((c for c in anomalies.columns if c.startswith("name")), None)
        mmsi_to_label = {}
        for mmsi in top_mmsi:
            single_anom = anomalies[anomalies["mmsi"] == mmsi]
            single_tracks = tracks[tracks["mmsi"] == mmsi]
            fig = plot_anomaly_map(single_anom, single_tracks, top_n=1)
            save(fig, f"anomalies_map_{mmsi}")

            label = mmsi
            if name_col_tmp and name_col_tmp in single_anom.columns:
                val = single_anom[name_col_tmp].dropna()
                if len(val) and str(val.iloc[0]).strip() not in ("", "nan", "None"):
                    label = f"{val.iloc[0]} ({mmsi})"
            mmsi_to_label[mmsi] = label

        # zapisz mapowanie mmsi -> etykieta, używane przez selectbox w app.py
        pd.DataFrame(
            [{"mmsi": k, "label": v} for k, v in mmsi_to_label.items()]
        ).to_parquet(DATA_DIR / "anomalies_map_options.parquet", index=False)
        print(f"  ✅ anomalies_map_options.parquet ({len(mmsi_to_label)} statków)")

        # zapisz tabelę top statków jako gotowy plik
        group_cols = ["mmsi"] + ([name_col_tmp] if name_col_tmp else [])
        group_cols = [c for c in group_cols if c in anomalies.columns]

        agg = (
            anomalies.groupby(group_cols)
            .agg(
                liczba_anomalii=("anomaly_type", "count"),
                typy_anomalii=("anomaly_type", lambda x: ", ".join(x.unique())),
                pierwsza_anomalia=("timestamp", "min"),
                ostatnia_anomalia=("timestamp", "max"),
            )
            .reset_index()
            .sort_values("liczba_anomalii", ascending=False)
        )

        if not vessels.empty:
            v = vessels[["mmsi", "vessel_name", "ship_type", "flag", "year_built",
                          "gross_tonnage", "sanctioned", "false_flag"]].copy()
            v["mmsi"] = v["mmsi"].astype(str).str.strip()
            agg["mmsi"] = agg["mmsi"].astype(str).str.strip()
            agg = agg.merge(v, on="mmsi", how="left")

        agg.to_parquet(DATA_DIR / "anomalies_table.parquet", index=False)
        print(f"  ✅ anomalies_table.parquet ({len(agg)} statków)")
    else:
        print("  ⚠️  Brak anomaly_map_*.parquet – uruchom najpierw "
              "generate_anomaly_map_data.py")

    # ── Tab 4: Mapa ──────────────────────────────────────────────────────
    print("\n=== Tab 4: Mapa ===")
    sample_path = DATA_DIR / "ais_map_sample.parquet"
    if sample_path.exists():
        ais_full = ctrl.ais_data.dropna(subset=["latitude", "longitude"])
        save(plot_hourly_activity(ais_full), "map_hourly_activity")
    else:
        print("  ⚠️  Brak ais_map_sample.parquet – uruchom generate_map_sample.py")

    # ── Tab 5: Profil statków ────────────────────────────────────────────
    print("\n=== Tab 5: Profil statków ===")
    if not vessels.empty:
        save(plot_year_built_histogram(vessels), "vessels_year_built")
        save(plot_tonnage_distribution(vessels), "vessels_tonnage")
        save(plot_classification_society(vessels), "vessels_classification")
        save(plot_inspections_analysis(vessels), "vessels_inspections")
        save(plot_flag_changes_vs_age(vessels), "vessels_flag_changes_vs_age")
        if "former_flags" in vessels.columns:
            save(plot_flag_hopping(vessels), "vessels_flag_hopping")

        # statystyki zbiorcze jako mały JSON-podobny parquet
        df_num = vessels.copy()
        for col in ["year_built", "gross_tonnage", "deadweight",
                    "inspections_total", "flag_change_count", "name_change_count"]:
            df_num[col] = pd.to_numeric(df_num[col], errors="coerce")

        stats = pd.DataFrame([{
            "mediana_roku_budowy": int(df_num["year_built"].median())
                if df_num["year_built"].notna().any() else None,
            "mediana_dwt": int(df_num["deadweight"].median())
                if df_num["deadweight"].notna().any() else None,
            "sr_inspekcji": round(float(df_num["inspections_total"].mean()), 1)
                if df_num["inspections_total"].notna().any() else None,
            "sr_zmian_bandery": round(float(df_num["flag_change_count"].mean()), 1)
                if df_num["flag_change_count"].notna().any() else None,
        }])
        stats.to_parquet(DATA_DIR / "vessels_stats.parquet", index=False)
        print(f"  ✅ vessels_stats.parquet")
    else:
        print("  ⚠️  Brak vessel_details_enriched.csv")

    print(f"\n✅ Gotowe. Wykresy zapisane w {CHARTS_DIR}")


if __name__ == "__main__":
    main()
