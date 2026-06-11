"""
controller.py – logika biznesowa aplikacji i Singleton DataLoader.

Wzorzec Singleton zapewnia że dane CSV są wczytywane do pamięci tylko raz,
niezależnie od liczby wywołań w aplikacji Streamlit. Każde kolejne odwołanie
zwraca już wczytane dane bez ponownego odczytu z dysku.

Klasy:
    DataLoader      – Singleton zarządzający wczytywaniem plików CSV
    FleetController – logika filtrowania i agregacji danych dla widoku
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from models import ShadowFleet, TransitData
from analysis import AnomalyDetector, SignalGapDetector, SpeedAnomalyDetector, DriftingDetector


# ── DataLoader (Singleton) ────────────────────────────────────────────────────

class DataLoader:
    """
    Singleton odpowiedzialny za wczytywanie i cache'owanie plików CSV.

    Gwarantuje że każdy plik jest wczytywany z dysku dokładnie raz.
    Kolejne wywołania load() zwracają dane z pamięci.

    Użycie:
        loader = DataLoader.get_instance()
        df = loader.load("data/ais_shadow_matches.csv")
    """

    _instance: Optional[DataLoader] = None

    def __new__(cls) -> DataLoader:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache: dict[str, pd.DataFrame] = {}
        return cls._instance

    @classmethod
    def get_instance(cls) -> DataLoader:
        """Zwraca jedyną instancję DataLoader (tworzy ją przy pierwszym wywołaniu)."""
        return cls()

    @classmethod
    def reset(cls) -> None:
        """
        Resetuje instancję i czyści cache.
        Używane głównie w testach jednostkowych.
        """
        cls._instance = None

    def load(self, path: str | Path, **read_csv_kwargs) -> pd.DataFrame:
        """
        Wczytuje plik CSV lub Parquet i zapisuje w cache.
        Przy kolejnych wywołaniach zwraca dane z pamięci.

        Parametry:
            path            – ścieżka do pliku CSV lub Parquet
            read_csv_kwargs – dodatkowe argumenty przekazywane do pd.read_csv()

        Zwraca:
            DataFrame z zawartością pliku.
        """
        key = str(path)

        if key not in self._cache:
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"Nie znaleziono pliku: {path}")
            print(f"[DataLoader] Wczytywanie: {p.name}")
            if p.suffix == ".parquet":
                self._cache[key] = pd.read_parquet(p)
            else:
                self._cache[key] = pd.read_csv(p, **read_csv_kwargs)
        else:
            print(f"[DataLoader] Cache: {Path(path).name}")

        return self._cache[key]

    def is_cached(self, path: str | Path) -> bool:
        """Sprawdza czy plik jest już w cache."""
        return str(path) in self._cache

    def clear_cache(self) -> None:
        """Czyści cache bez resetowania instancji."""
        self._cache.clear()

    @property
    def cached_files(self) -> list[str]:
        """Lista plików aktualnie w cache."""
        return list(self._cache.keys())


# ── FleetController ───────────────────────────────────────────────────────────

class FleetController:
    """
    Główna logika biznesowa aplikacji.

    Odpowiada za:
    - wczytanie i udostępnienie danych przez DataLoader
    - filtrowanie danych według kryteriów użytkownika
    - uruchamianie detektorów anomalii (Strategy Pattern)
    - agregację danych dla wykresów
    """

    # dostępne detektory anomalii – dodaj tu nowe strategie
    DETECTORS: dict[str, AnomalyDetector] = {
        "Luka w sygnale":       SignalGapDetector(min_gap_hours=24),
        "Spoofing pozycji":     SpeedAnomalyDetector(max_speed_knots=50),
        "Dryfowanie STS":       DriftingDetector(max_sog=0.5, min_duration_hours=4),
    }

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self._loader  = DataLoader.get_instance()

        # główne DataFrames – wczytywane leniwie przy pierwszym dostępie
        self._ais:     Optional[pd.DataFrame] = None
        self._fleet:   Optional[pd.DataFrame] = None
        self._transit: Optional[pd.DataFrame] = None

    # ── wczytywanie danych ────────────────────────────────────────────────────

    def load_all(self) -> None:
        """Wczytuje wszystkie pliki danych naraz (np. przy starcie aplikacji)."""
        self.ais_data
        self.fleet_data
        self.transit_data

    @property
    def ais_data(self) -> pd.DataFrame:
        """Dane AIS dopasowane do floty cieni.
        Preferuje ais_shadow_matches.parquet (mniejszy, szybszy).
        Fallback na ais_shadow_matches.csv jeśli parquet niedostępny.
        """
        if self._ais is None:
            parquet_path = self.data_dir / "ais_shadow_matches.parquet"
            csv_path     = self.data_dir / "ais_shadow_matches.csv"

            if parquet_path.exists():
                df = self._loader.load(parquet_path)
            else:
                df = self._loader.load(csv_path, dtype={"mmsi": str},
                                       low_memory=False)
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

            df["mmsi"] = df["mmsi"].astype(str).str.strip()
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            self._ais = df
        return self._ais

    @property
    def fleet_data(self) -> pd.DataFrame:
        """Połączona lista floty cieni (shadow_fleet_combined.csv)."""
        if self._fleet is None:
            self._fleet = self._loader.load(
                self.data_dir / "shadow_fleet_combined.csv",
                dtype={"mmsi": str},
            )
        return self._fleet

    @property
    def transit_data(self) -> pd.DataFrame:
        """Miesięczne dane o przeprawach (suez_hormuz_monthly.csv)."""
        if self._transit is None:
            df = self._loader.load(self.data_dir / "suez_hormuz_monthly.csv")
            df["Date"] = pd.to_datetime(df["Date"], format="%b-%Y", errors="coerce")
            self._transit = df
        return self._transit

    @property
    def shadow_fleet(self) -> ShadowFleet:
        """Obiekt ShadowFleet zbudowany z fleet_data."""
        return ShadowFleet.from_dataframe(self.fleet_data)

    # ── filtrowanie ───────────────────────────────────────────────────────────

    def filter_ais(
        self,
        fleet:      Optional[str]  = None,
        date_from:  Optional[str]  = None,
        date_to:    Optional[str]  = None,
        mmsi_list:  Optional[list] = None,
    ) -> pd.DataFrame:
        """
        Filtruje dane AIS według kryteriów użytkownika.

        Parametry:
            fleet     – "Iran" | "Russia" | None (oba)
            date_from – data początkowa (YYYY-MM-DD)
            date_to   – data końcowa (YYYY-MM-DD)
            mmsi_list – lista konkretnych MMSI do filtrowania
        """
        df = self.ais_data.copy()

        if fleet:
            df = df[df["fleet"] == fleet]

        if date_from:
            df = df[df["timestamp"] >= pd.Timestamp(date_from)]

        if date_to:
            df = df[df["timestamp"] <= pd.Timestamp(date_to)]

        if mmsi_list:
            df = df[df["mmsi"].isin([str(m) for m in mmsi_list])]

        return df

    def filter_fleet(
        self,
        fleet:      Optional[str]  = None,
        sanctioned: Optional[bool] = None,
        false_flag: Optional[bool] = None,
    ) -> pd.DataFrame:
        """
        Filtruje listę floty cieni według kryteriów.

        Parametry:
            fleet      – "Iran" | "Russia" | None (oba)
            sanctioned – True = tylko objęte sankcjami
            false_flag – True = tylko z fałszywą banderą
        """
        df = self.fleet_data.copy()

        if fleet:
            df = df[df["fleet"] == fleet]

        if sanctioned is not None:
            df = df[df["sanctioned"] == sanctioned]

        if false_flag is not None:
            df = df[df["false_flag"] == false_flag]

        return df

    # ── detekcja anomalii ─────────────────────────────────────────────────────

    def detect_anomalies(
        self,
        detector_name: str,
        fleet:         Optional[str] = None,
        date_from:     Optional[str] = None,
        date_to:       Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Uruchamia wybrany detektor anomalii na przefiltrowanych danych AIS.

        Parametry:
            detector_name – klucz z FleetController.DETECTORS
            fleet         – opcjonalne filtrowanie po flocie
            date_from     – opcjonalne filtrowanie po dacie
            date_to       – opcjonalne filtrowanie po dacie
        """
        if detector_name not in self.DETECTORS:
            raise ValueError(
                f"Nieznany detektor: {detector_name!r}. "
                f"Dostępne: {list(self.DETECTORS.keys())}"
            )

        detector = self.DETECTORS[detector_name]
        df = self.filter_ais(fleet=fleet, date_from=date_from, date_to=date_to)
        return detector.detect(df)

    # ── agregacje dla wykresów ────────────────────────────────────────────────

    def get_activity_by_month(self, fleet: Optional[str] = None) -> pd.DataFrame:
        """
        Zwraca liczbę pingów AIS per miesiąc.
        Używane do wykresu liniowego aktywności floty cieni w czasie.
        """
        df = self.filter_ais(fleet=fleet)
        df = df.dropna(subset=["timestamp"])
        df["month"] = df["timestamp"].dt.to_period("M").dt.to_timestamp()
        return df.groupby("month").size().reset_index(name="ping_count")

    def get_flag_distribution(self, fleet: Optional[str] = None) -> pd.DataFrame:
        """
        Zwraca rozkład bander w flocie cieni.
        Używane do wykresu słupkowego.
        """
        df = self.filter_fleet(fleet=fleet)
        # kolumna bandery może się różnić: flag / current_flag_clean / current_flag
        flag_col = next(
            (c for c in df.columns
             if "flag" in c and "false" not in c and "former" not in c),
            None
        )
        if not flag_col:
            return pd.DataFrame(columns=["flag", "count"])
        return (df.groupby(flag_col)
                  .size()
                  .reset_index(name="count")
                  .rename(columns={flag_col: "flag"})
                  .sort_values("count", ascending=False))

    def get_anomaly_summary(self, fleet: Optional[str] = None) -> pd.DataFrame:
        """
        Uruchamia wszystkie detektory i zwraca zbiorczy wynik.
        Używane do wykresu porównawczego liczby anomalii per typ.
        """
        results = []
        df = self.filter_ais(fleet=fleet)

        for name, detector in self.DETECTORS.items():
            try:
                anomalies = detector.detect(df)
                results.append({
                    "detector":    name,
                    "count":       len(anomalies),
                    "description": detector.description,
                })
            except Exception as e:
                results.append({
                    "detector":    name,
                    "count":       0,
                    "description": f"Błąd: {e}",
                })

        return pd.DataFrame(results)