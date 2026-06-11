"""
models.py – klasy reprezentujące elementy logiczne projektu.

Hierarchia klas:
    Vessel          – pojedynczy statek (dane statyczne)
    AISRecord       – pojedynczy ping AIS (dane dynamiczne)
    ShadowFleet     – kolekcja statków floty cieni
    TransitData     – miesięczne dane o przeprawach przez cieśniny
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd

# ── Vessel ────────────────────────────────────────────────────────────────────


@dataclass
class Vessel:
    """
    Reprezentuje pojedynczy statek z danymi statycznymi.
    Odpowiada wierszowi z shadow_fleet_combined.csv.
    """

    mmsi: str
    imo: Optional[str] = None
    name: Optional[str] = None
    flag: Optional[str] = None
    fleet: Optional[str] = None  # "Iran" | "Russia"
    sanctioned: bool = False
    false_flag: bool = False
    date_added: Optional[datetime] = None

    def __post_init__(self):
        # MMSI zawsze jako string bez białych znaków
        self.mmsi = str(self.mmsi).strip()
        if self.imo:
            self.imo = str(self.imo).strip()

    @property
    def is_high_risk(self) -> bool:
        """Statek wysokiego ryzyka: objęty sankcjami LUB używający fałszywej bandery."""
        return self.sanctioned or self.false_flag

    def __repr__(self) -> str:
        return f"Vessel(mmsi={self.mmsi}, name={self.name!r}, fleet={self.fleet})"


# ── AISRecord ─────────────────────────────────────────────────────────────────


@dataclass
class AISRecord:
    """
    Reprezentuje pojedynczy ping AIS – pozycję statku w danym momencie.
    Odpowiada wierszowi z ais_shadow_matches.csv.
    """

    mmsi: str
    timestamp: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sog: Optional[float] = None  # Speed Over Ground (węzły)
    cog: Optional[float] = None  # Course Over Ground (stopnie)
    heading: Optional[float] = None
    status: Optional[str] = None
    ais_source: Optional[str] = None  # "DMA" | "NOAA"

    def __post_init__(self):
        self.mmsi = str(self.mmsi).strip()

    @property
    def is_moving(self) -> bool:
        """Czy statek się porusza (SOG > 0.5 węzła)."""
        return self.sog is not None and self.sog > 0.5

    @property
    def has_valid_position(self) -> bool:
        """Czy rekord ma prawidłowe współrzędne geograficzne."""
        return (
            self.latitude is not None
            and self.longitude is not None
            and -90 <= self.latitude <= 90
            and -180 <= self.longitude <= 180
        )

    def __repr__(self) -> str:
        return (
            f"AISRecord(mmsi={self.mmsi}, "
            f"timestamp={self.timestamp}, "
            f"lat={self.latitude}, lon={self.longitude})"
        )


# ── ShadowFleet ───────────────────────────────────────────────────────────────


class ShadowFleet:
    """
    Kolekcja statków floty cieni.
    Umożliwia filtrowanie, wyszukiwanie i podstawowe statystyki.
    """

    def __init__(self, vessels: list[Vessel]):
        self._vessels = vessels
        # indeks po MMSI dla szybkiego wyszukiwania O(1)
        self._mmsi_index: dict[str, Vessel] = {v.mmsi: v for v in vessels}

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> ShadowFleet:
        """Tworzy ShadowFleet z DataFrame (np. shadow_fleet_combined.csv)."""
        vessels = []
        for _, row in df.iterrows():
            vessels.append(
                Vessel(
                    mmsi=str(row.get("mmsi", "")).strip(),
                    imo=str(row["imo"]) if pd.notna(row.get("imo")) else None,
                    name=row.get("name") if pd.notna(row.get("name")) else None,
                    flag=row.get("flag") if pd.notna(row.get("flag")) else None,
                    fleet=row.get("fleet") if pd.notna(row.get("fleet")) else None,
                    sanctioned=bool(row.get("sanctioned", False)),
                    false_flag=bool(row.get("false_flag", False)),
                    date_added=(
                        pd.to_datetime(row["date_added"], errors="coerce")
                        if pd.notna(row.get("date_added"))
                        else None
                    ),
                )
            )
        return cls(vessels)

    def get_by_mmsi(self, mmsi: str) -> Optional[Vessel]:
        """Zwraca statek po MMSI lub None jeśli nie znaleziono."""
        return self._mmsi_index.get(str(mmsi).strip())

    def filter_by_fleet(self, fleet: str) -> ShadowFleet:
        """Zwraca nową kolekcję zawierającą tylko statki danej floty."""
        return ShadowFleet([v for v in self._vessels if v.fleet == fleet])

    def filter_high_risk(self) -> ShadowFleet:
        """Zwraca tylko statki wysokiego ryzyka (sanctioned lub false_flag)."""
        return ShadowFleet([v for v in self._vessels if v.is_high_risk])

    def to_dataframe(self) -> pd.DataFrame:
        """Konwertuje kolekcję z powrotem do DataFrame."""
        return pd.DataFrame(
            [
                {
                    "mmsi": v.mmsi,
                    "imo": v.imo,
                    "name": v.name,
                    "flag": v.flag,
                    "fleet": v.fleet,
                    "sanctioned": v.sanctioned,
                    "false_flag": v.false_flag,
                    "date_added": v.date_added,
                }
                for v in self._vessels
            ]
        )

    @property
    def mmsi_set(self) -> set[str]:
        """Zbiór wszystkich MMSI w kolekcji – do szybkiego sprawdzania przynależności."""
        return set(self._mmsi_index.keys())

    def __len__(self) -> int:
        return len(self._vessels)

    def __iter__(self):
        return iter(self._vessels)

    def __repr__(self) -> str:
        return f"ShadowFleet({len(self._vessels)} vessels)"


# ── TransitData ───────────────────────────────────────────────────────────────


@dataclass
class TransitData:
    """
    Miesięczne dane o przeprawach przez cieśniny (Suez, Hormuz).
    Odpowiada wierszowi z suez_hormuz_monthly.csv.
    """

    month: datetime
    suez_transits: Optional[float] = None
    hormuz_transits: Optional[float] = None

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> list[TransitData]:
        """Tworzy listę TransitData z DataFrame."""
        records = []
        df = df.copy()
        df["Date"] = pd.to_datetime(df["Date"], format="%b-%Y", errors="coerce")

        for _, row in df.iterrows():
            if pd.isna(row["Date"]):
                continue
            records.append(
                cls(
                    month=row["Date"],
                    suez_transits=(
                        row.get("Suez Canal")
                        if pd.notna(row.get("Suez Canal"))
                        else None
                    ),
                    hormuz_transits=(
                        row.get("Strait of Hormuz")
                        if pd.notna(row.get("Strait of Hormuz"))
                        else None
                    ),
                )
            )
        return records

    def __repr__(self) -> str:
        return (
            f"TransitData(month={self.month.strftime('%Y-%m')}, "
            f"suez={self.suez_transits}, hormuz={self.hormuz_transits})"
        )
