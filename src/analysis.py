"""
analysis.py – detektory anomalii AIS oparte na Strategy Pattern.

Wzorzec Strategy pozwala na wymienne stosowanie różnych algorytmów
wykrywania anomalii bez modyfikacji reszty kodu. Każdy detektor
implementuje wspólny interfejs AnomalyDetector.

Dostępne strategie:
    SignalGapDetector     – wykrywa luki w sygnale AIS > N godzin
    SpeedAnomalyDetector  – wykrywa fizycznie niemożliwe prędkości między pingami
    DriftingDetector      – wykrywa dryfowanie w miejscu (potencjalny transfer STS)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


# ── interfejs bazowy (Strategy) ───────────────────────────────────────────────

class AnomalyDetector(ABC):
    """
    Abstrakcyjna klasa bazowa dla detektorów anomalii AIS.
    Definiuje interfejs wspólny dla wszystkich strategii.
    """

    @abstractmethod
    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Wykrywa anomalie w danych AIS.

        Parametry:
            df – DataFrame z kolumnami: mmsi, timestamp, latitude,
                 longitude, sog (wymagane przez większość detektorów)

        Zwraca:
            DataFrame zawierający tylko wiersze z wykrytymi anomaliami,
            z dodatkową kolumną 'anomaly_type' opisującą typ anomalii.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Nazwa detektora wyświetlana w interfejsie."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Opis działania detektora."""

    def _validate_columns(self, df: pd.DataFrame, required: list[str]) -> None:
        """Sprawdza czy DataFrame zawiera wymagane kolumny."""
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(
                f"{self.__class__.__name__}: brak wymaganych kolumn: {missing}. "
                f"Dostępne: {list(df.columns)}"
            )


# ── SignalGapDetector ─────────────────────────────────────────────────────────

class SignalGapDetector(AnomalyDetector):
    """
    Wykrywa luki w sygnale AIS przekraczające zadany próg.

    Długa przerwa w transmisji może oznaczać celowe wyłączenie
    transpondera AIS – klasyczna taktyka floty cieni.

    Filtruje fałszywe alarmy:
    - ostatni ping statku w zbiorze (koniec okresu danych, nie wyłączenie)
    """

    def __init__(self, min_gap_hours: float = 24.0):
        """
        Parametry:
            min_gap_hours – minimalna przerwa w sygnale (w godzinach)
                            uznawana za anomalię. Domyślnie 24h.
        """
        self.min_gap_hours = min_gap_hours

    @property
    def name(self) -> str:
        return f"Luka w sygnale (>{self.min_gap_hours:.0f}h)"

    @property
    def description(self) -> str:
        return (f"Wykrywa statki które nie wysyłały sygnału AIS "
                f"przez ponad {self.min_gap_hours:.0f} godzin z rzędu. "
                f"Może oznaczać celowe wyłączenie transpondera.")

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate_columns(df, ["mmsi", "timestamp"])

        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])
        df = df.sort_values(["mmsi", "timestamp"])

        # oblicz przerwę między kolejnymi pingami tego samego statku
        df["gap_hours"] = (
            df.groupby("mmsi")["timestamp"]
            .diff()
            .dt.total_seconds()
            / 3600
        )

        # ostatni ping każdego statku – luka PO nim to koniec danych,
        # nie wyłączenie transpondera → wyklucz z anomalii
        if df.empty:
            return pd.DataFrame(columns=list(df.columns) + ["anomaly_type"])

        last_ping_per_vessel = df.groupby("mmsi")["timestamp"].max()
        df["is_last_ping"] = df.apply(
            lambda r: r["timestamp"] == last_ping_per_vessel[r["mmsi"]], axis=1
        )

        # anomalia = luka > próg I nie jest to ostatni ping statku
        mask = (df["gap_hours"] > self.min_gap_hours) & (~df["is_last_ping"])
        anomalies = df[mask].copy()
        anomalies["anomaly_type"] = (
            anomalies["gap_hours"].apply(lambda h: f"Luka sygnału: {h:.1f}h")
        )

        return anomalies.drop(columns=["gap_hours", "is_last_ping"])


# ── SpeedAnomalyDetector ──────────────────────────────────────────────────────

class SpeedAnomalyDetector(AnomalyDetector):
    """
    Wykrywa fizycznie niemożliwe prędkości między kolejnymi pingami AIS.

    Jeśli statek "przeskoczył" setki kilometrów w krótkim czasie,
    oznacza to spoofing pozycji – fałszowanie sygnału GPS/AIS.
    Maksymalna prędkość tankowca to ~17 węzłów (~31 km/h).
    """

    def __init__(self, max_speed_knots: float = 50.0):
        """
        Parametry:
            max_speed_knots – maksymalna fizycznie możliwa prędkość (węzły).
                              Domyślnie 50 węzłów – dwukrotność max prędkości
                              szybkiego statku, margines na błędy GPS.
        """
        self.max_speed_knots = max_speed_knots

    @property
    def name(self) -> str:
        return f"Niemożliwa prędkość (>{self.max_speed_knots:.0f} kn)"

    @property
    def description(self) -> str:
        return (f"Wykrywa statki których obliczona prędkość między pingami "
                f"przekracza {self.max_speed_knots:.0f} węzłów. "
                f"Może oznaczać spoofing pozycji GPS.")

    @staticmethod
    def _haversine_km(lat1, lon1, lat2, lon2) -> float:
        """Oblicza odległość między dwoma punktami w km (wzór Haversine)."""
        r = 6371.0  # promień Ziemi w km
        phi1, phi2 = np.radians(lat1), np.radians(lat2)
        dphi = np.radians(lat2 - lat1)
        dlambda = np.radians(lon2 - lon1)
        a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
        return 2 * r * np.arcsin(np.sqrt(a))

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate_columns(df, ["mmsi", "timestamp", "latitude", "longitude"])

        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp", "latitude", "longitude"])
        df = df.sort_values(["mmsi", "timestamp"])

        # poprzednia pozycja i czas dla tego samego statku
        df["prev_lat"] = df.groupby("mmsi")["latitude"].shift(1)
        df["prev_lon"] = df.groupby("mmsi")["longitude"].shift(1)
        df["prev_ts"]  = df.groupby("mmsi")["timestamp"].shift(1)

        # oblicz czas w godzinach między pingami
        df["dt_hours"] = (
            (df["timestamp"] - df["prev_ts"]).dt.total_seconds() / 3600
        )

        # oblicz odległość i prędkość tylko tam gdzie mamy poprzednią pozycję
        mask = df["prev_lat"].notna() & (df["dt_hours"] > 0)
        df.loc[mask, "dist_km"] = df[mask].apply(
            lambda r: self._haversine_km(
                r["prev_lat"], r["prev_lon"], r["latitude"], r["longitude"]
            ),
            axis=1,
        )

        # prędkość: km/h → węzły (1 węzeł = 1.852 km/h)
        df.loc[mask, "calc_speed_knots"] = (
            df.loc[mask, "dist_km"] / df.loc[mask, "dt_hours"] / 1.852
        )

        anomalies = df[df["calc_speed_knots"] > self.max_speed_knots].copy()
        anomalies["anomaly_type"] = anomalies["calc_speed_knots"].apply(
            lambda s: f"Spoofing pozycji: {s:.0f} kn"
        )

        return anomalies.drop(columns=["prev_lat", "prev_lon", "prev_ts",
                                        "dt_hours", "dist_km", "calc_speed_knots"],
                               errors="ignore")


# ── DriftingDetector ──────────────────────────────────────────────────────────

class DriftingDetector(AnomalyDetector):
    """
    Wykrywa statki dryfujące w miejscu przez dłuższy czas.

    Tankowiec stojący w miejscu na otwartym morzu (nie w porcie,
    nie na kotwicowisku) może prowadzić transfer ropy statek-statek (STS)
    – kluczowa metoda omijania sankcji.
    """

    def __init__(self, max_sog: float = 0.5, min_duration_hours: float = 4.0):
        """
        Parametry:
            max_sog             – maksymalna prędkość uznawana za "stanie"
                                  (węzły). Domyślnie 0.5 kn.
            min_duration_hours  – minimalny czas stania w miejscu (godziny).
                                  Domyślnie 4h.
        """
        self.max_sog = max_sog
        self.min_duration_hours = min_duration_hours

    @property
    def name(self) -> str:
        return f"Dryfowanie w miejscu (>{self.min_duration_hours:.0f}h)"

    @property
    def description(self) -> str:
        return (f"Wykrywa statki stojące w miejscu (SOG < {self.max_sog} kn) "
                f"przez ponad {self.min_duration_hours:.0f} godziny z rzędu. "
                f"Może oznaczać transfer ropy statek-statek (STS).")

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate_columns(df, ["mmsi", "timestamp", "sog"])

        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp", "sog"])
        df = df.sort_values(["mmsi", "timestamp"])

        # oznacz pingi gdzie statek stoi
        df["is_stopped"] = df["sog"] < self.max_sog

        results = []
        for mmsi, group in df.groupby("mmsi"):
            group = group.reset_index(drop=True)
            # znajdź ciągłe okresy stania
            group["block"] = (group["is_stopped"] != group["is_stopped"].shift()).cumsum()

            for _, block in group[group["is_stopped"]].groupby("block"):
                t_start = block["timestamp"].min()
                t_end   = block["timestamp"].max()
                duration = (t_end - t_start).total_seconds() / 3600

                if duration >= self.min_duration_hours:
                    # zwróć tylko pierwszy ping każdego okresu dryfowania
                    row = block.iloc[0].copy()
                    row["anomaly_type"] = f"Dryfowanie STS: {duration:.1f}h"
                    results.append(row)

        if not results:
            return pd.DataFrame(columns=list(df.columns) + ["anomaly_type"])

        return (pd.DataFrame(results)
                  .drop(columns=["is_stopped", "block"], errors="ignore"))