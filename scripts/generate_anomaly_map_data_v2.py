"""
generate_anomaly_map_data.py – generuje prekalkulowane dane do mapy anomalii.

Uruchamia SpeedAnomalyDetector (najbardziej obciążający detektor) na pełnych
danych AIS, wybiera top 15 statków z największą liczbą anomalii i zapisuje
zarówno same anomalie jak i pełne trasy tych statków – gotowe do narysowania
przez plot_anomaly_map() bez żadnych obliczeń przy starcie aplikacji.

Wyjście:
    data/anomaly_map_anomalies.parquet  – wykryte anomalie (top 15 statków)
    data/anomaly_map_tracks.parquet     – pełne trasy AIS tych statków

Użycie:
    python scripts/generate_anomaly_map_data.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from controller import FleetController

DATA_DIR = Path(__file__).parent.parent / "data"
TOP_N = 8


def main():
    print("Wczytuję dane AIS...")
    ctrl = FleetController(data_dir=DATA_DIR)
    ctrl.load_all()

    ais = ctrl.filter_ais(fleet="Rosja")
    print(f"  Rekordów AIS (Rosja): {len(ais):,}")

    print("\nUruchamiam SpeedAnomalyDetector...")
    detector = FleetController.DETECTORS["Spoofing pozycji"]
    anomalies = detector.detect(ais)
    print(f"  Wykrytych anomalii: {len(anomalies):,}")

    if anomalies.empty:
        print("Brak anomalii – przerywam.")
        return

    # top N statków z największą liczbą anomalii
    top_mmsi = (
        anomalies.dropna(subset=["latitude", "longitude"])
        .groupby("mmsi").size().nlargest(TOP_N).index.tolist()
    )
    print(f"  Top {TOP_N} statków: {top_mmsi}")

    anomalies_top = anomalies[anomalies["mmsi"].isin(top_mmsi)].copy()

    # wzbogać o nazwy z vessel_details_enriched
    vessel_path = DATA_DIR / "vessel_details_enriched.csv"
    if vessel_path.exists():
        vessels = pd.read_csv(vessel_path, dtype=str)[["mmsi", "vessel_name"]]
        vessels["mmsi"] = vessels["mmsi"].astype(str).str.strip()
        anomalies_top["mmsi"] = anomalies_top["mmsi"].astype(str).str.strip()
        anomalies_top = anomalies_top.merge(vessels, on="mmsi", how="left")

    # pełne trasy tych statków (do narysowania linii na mapie)
    tracks = ais[ais["mmsi"].isin(top_mmsi)].copy()
    tracks["mmsi"] = tracks["mmsi"].astype(str).str.strip()

    out_anomalies = DATA_DIR / "anomaly_map_anomalies.parquet"
    out_tracks = DATA_DIR / "anomaly_map_tracks.parquet"

    anomalies_top.to_parquet(out_anomalies, index=False, compression="snappy")
    tracks.to_parquet(out_tracks, index=False, compression="snappy")

    print(f"\n✅ {out_anomalies.name}: {len(anomalies_top):,} wierszy "
          f"({out_anomalies.stat().st_size / 1e6:.2f} MB)")
    print(f"✅ {out_tracks.name}: {len(tracks):,} wierszy "
          f"({out_tracks.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
