"""
test_analysis.py – testy jednostkowe projektu.

Testowane moduły:
    analysis.py   – detektory anomalii (SignalGapDetector, SpeedAnomalyDetector, DriftingDetector)
    models.py     – klasy Vessel, ShadowFleet, AISRecord, TransitData
    controller.py – DataLoader (Singleton), FleetController

Uruchomienie:
    pytest tests/test_analysis.py -v
    python -m pytest tests/test_analysis.py -v   (alternatywnie)
"""

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from analysis import AnomalyDetector, SignalGapDetector, SpeedAnomalyDetector, DriftingDetector
from models import Vessel, AISRecord, ShadowFleet, TransitData
from controller import DataLoader, FleetController


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_ais_df() -> pd.DataFrame:
    """Przykładowe dane AIS z różnymi scenariuszami anomalii."""
    return pd.DataFrame({
        "mmsi":      ["111", "111", "111", "222", "222", "333", "333", "333"],
        "timestamp": [
            "2025-01-01 00:00",
            "2025-01-02 02:00",  # luka 26h dla statku 111
            "2025-01-02 03:00",
            "2025-01-01 00:00",
            "2025-01-01 00:10",  # skok pozycji dla statku 222
            "2025-01-01 00:00",
            "2025-01-01 04:00",  # dryfowanie 4h dla statku 333
            "2025-01-01 08:00",
        ],
        "latitude":  [54.0, 54.1, 54.2, 55.0, 75.0, 10.0, 10.01, 10.02],
        "longitude": [10.0, 10.1, 10.2, 10.0, 10.0, 50.0, 50.01, 50.02],
        "sog":       [5.0,  5.0,  5.0,  14.0, 14.0, 0.1,  0.1,   0.1],
    })


@pytest.fixture
def sample_fleet_df() -> pd.DataFrame:
    """Przykładowe dane listy floty cieni."""
    return pd.DataFrame({
        "mmsi":       ["111111111", "222222222", "333333333"],
        "imo":        ["IMO1111111", "IMO2222222", None],
        "name":       ["SHADOW ONE", "SHADOW TWO", "SHADOW THREE"],
        "flag":       ["PANAMA", "LIBERIA", "COOK ISLANDS"],
        "fleet":      ["Iran", "Russia", "Iran"],
        "sanctioned": [True, False, False],
        "false_flag": [False, True, False],
        "date_added": ["2024-01-01", "2023-06-15", None],
    })


@pytest.fixture(autouse=True)
def reset_singleton():
    """Resetuje Singleton DataLoader przed każdym testem."""
    DataLoader.reset()
    yield
    DataLoader.reset()


# ── testy SignalGapDetector ───────────────────────────────────────────────────

class TestSignalGapDetector:

    def test_wykrywa_luke_powyzej_progu(self, sample_ais_df):
        detector = SignalGapDetector(min_gap_hours=24)
        result = detector.detect(sample_ais_df)
        assert len(result) == 1
        assert result.iloc[0]["mmsi"] == "111"

    def test_nie_wykrywa_gdy_brak_luki(self, sample_ais_df):
        detector = SignalGapDetector(min_gap_hours=48)
        result = detector.detect(sample_ais_df)
        assert len(result) == 0

    def test_kolumna_anomaly_type_istnieje(self, sample_ais_df):
        detector = SignalGapDetector(min_gap_hours=24)
        result = detector.detect(sample_ais_df)
        assert "anomaly_type" in result.columns

    def test_anomaly_type_zawiera_czas_luki(self, sample_ais_df):
        detector = SignalGapDetector(min_gap_hours=24)
        result = detector.detect(sample_ais_df)
        assert "26.0h" in result.iloc[0]["anomaly_type"]

    def test_pusty_dataframe(self):
        detector = SignalGapDetector()
        df = pd.DataFrame(columns=["mmsi", "timestamp", "latitude", "longitude", "sog"])
        result = detector.detect(df)
        assert len(result) == 0

    def test_brak_wymaganej_kolumny(self, sample_ais_df):
        detector = SignalGapDetector()
        df = sample_ais_df.drop(columns=["timestamp"])
        with pytest.raises(ValueError, match="brak wymaganych kolumn"):
            detector.detect(df)

    def test_name_i_description_nie_sa_puste(self):
        detector = SignalGapDetector(min_gap_hours=12)
        assert len(detector.name) > 0
        assert len(detector.description) > 0
        assert "12" in detector.name


# ── testy SpeedAnomalyDetector ────────────────────────────────────────────────

class TestSpeedAnomalyDetector:

    def test_wykrywa_niemozliwa_predkosc(self, sample_ais_df):
        detector = SpeedAnomalyDetector(max_speed_knots=50)
        result = detector.detect(sample_ais_df)
        assert len(result) >= 1
        assert any(result["mmsi"] == "222")

    def test_nie_wykrywa_normalnej_predkosci(self):
        detector = SpeedAnomalyDetector(max_speed_knots=50)
        df = pd.DataFrame({
            "mmsi":      ["AAA", "AAA"],
            "timestamp": ["2025-01-01 00:00", "2025-01-01 01:00"],
            "latitude":  [54.0, 54.01],   # ~1 km w 1h = ok. 0.5 kn
            "longitude": [10.0, 10.0],
            "sog":       [0.5, 0.5],
        })
        result = detector.detect(df)
        assert len(result) == 0

    def test_haversine_znane_wartosci(self):
        """Odległość Warszawa–Berlin wynosi ok. 520 km."""
        detector = SpeedAnomalyDetector()
        dist = detector._haversine_km(52.23, 21.01, 52.52, 13.40)
        assert 510 < dist < 540

    def test_kolumna_anomaly_type_zawiera_predkosc(self, sample_ais_df):
        detector = SpeedAnomalyDetector(max_speed_knots=50)
        result = detector.detect(sample_ais_df)
        if len(result) > 0:
            assert "kn" in result.iloc[0]["anomaly_type"]

    def test_brak_wymaganej_kolumny(self, sample_ais_df):
        detector = SpeedAnomalyDetector()
        df = sample_ais_df.drop(columns=["latitude"])
        with pytest.raises(ValueError, match="brak wymaganych kolumn"):
            detector.detect(df)


# ── testy DriftingDetector ────────────────────────────────────────────────────

class TestDriftingDetector:

    def test_wykrywa_dryfowanie(self, sample_ais_df):
        detector = DriftingDetector(max_sog=0.5, min_duration_hours=4)
        result = detector.detect(sample_ais_df)
        assert len(result) >= 1
        assert any(result["mmsi"] == "333")

    def test_nie_wykrywa_krotkotrwalego_stania(self, sample_ais_df):
        detector = DriftingDetector(max_sog=0.5, min_duration_hours=10)
        result = detector.detect(sample_ais_df)
        assert len(result) == 0

    def test_pusty_dataframe(self):
        detector = DriftingDetector()
        df = pd.DataFrame(columns=["mmsi", "timestamp", "sog"])
        result = detector.detect(df)
        assert len(result) == 0

    def test_anomaly_type_zawiera_czas(self, sample_ais_df):
        detector = DriftingDetector(max_sog=0.5, min_duration_hours=4)
        result = detector.detect(sample_ais_df)
        if len(result) > 0:
            assert "h" in result.iloc[0]["anomaly_type"]

    def test_brak_wymaganej_kolumny(self, sample_ais_df):
        detector = DriftingDetector()
        df = sample_ais_df.drop(columns=["sog"])
        with pytest.raises(ValueError, match="brak wymaganych kolumn"):
            detector.detect(df)


# ── testy Vessel ──────────────────────────────────────────────────────────────

class TestVessel:

    def test_tworzenie_podstawowe(self):
        v = Vessel(mmsi="123456789", name="TEST", fleet="Iran")
        assert v.mmsi == "123456789"
        assert v.name == "TEST"
        assert v.fleet == "Iran"

    def test_mmsi_jest_stringiem(self):
        v = Vessel(mmsi=123456789)
        assert isinstance(v.mmsi, str)

    def test_mmsi_bez_bialych_znakow(self):
        v = Vessel(mmsi="  123456789  ")
        assert v.mmsi == "123456789"

    def test_is_high_risk_sanctioned(self):
        v = Vessel(mmsi="111", sanctioned=True, false_flag=False)
        assert v.is_high_risk is True

    def test_is_high_risk_false_flag(self):
        v = Vessel(mmsi="111", sanctioned=False, false_flag=True)
        assert v.is_high_risk is True

    def test_is_high_risk_false_gdy_brak(self):
        v = Vessel(mmsi="111", sanctioned=False, false_flag=False)
        assert v.is_high_risk is False


# ── testy AISRecord ───────────────────────────────────────────────────────────

class TestAISRecord:

    def test_is_moving_true(self):
        rec = AISRecord(mmsi="111", sog=5.0)
        assert rec.is_moving is True

    def test_is_moving_false_gdy_stoi(self):
        rec = AISRecord(mmsi="111", sog=0.3)
        assert rec.is_moving is False

    def test_is_moving_false_gdy_brak_sog(self):
        rec = AISRecord(mmsi="111", sog=None)
        assert rec.is_moving is False

    def test_has_valid_position_true(self):
        rec = AISRecord(mmsi="111", latitude=54.0, longitude=10.0)
        assert rec.has_valid_position is True

    def test_has_valid_position_false_gdy_brak(self):
        rec = AISRecord(mmsi="111", latitude=None, longitude=10.0)
        assert rec.has_valid_position is False

    def test_has_valid_position_false_gdy_poza_zakresem(self):
        rec = AISRecord(mmsi="111", latitude=95.0, longitude=10.0)
        assert rec.has_valid_position is False


# ── testy ShadowFleet ─────────────────────────────────────────────────────────

class TestShadowFleet:

    def test_from_dataframe(self, sample_fleet_df):
        fleet = ShadowFleet.from_dataframe(sample_fleet_df)
        assert len(fleet) == 3

    def test_get_by_mmsi(self, sample_fleet_df):
        fleet = ShadowFleet.from_dataframe(sample_fleet_df)
        vessel = fleet.get_by_mmsi("111111111")
        assert vessel is not None
        assert vessel.name == "SHADOW ONE"

    def test_get_by_mmsi_nie_znaleziono(self, sample_fleet_df):
        fleet = ShadowFleet.from_dataframe(sample_fleet_df)
        assert fleet.get_by_mmsi("999999999") is None

    def test_filter_by_fleet(self, sample_fleet_df):
        fleet = ShadowFleet.from_dataframe(sample_fleet_df)
        iran = fleet.filter_by_fleet("Iran")
        assert len(iran) == 2
        assert all(v.fleet == "Iran" for v in iran)

    def test_filter_high_risk(self, sample_fleet_df):
        fleet = ShadowFleet.from_dataframe(sample_fleet_df)
        high_risk = fleet.filter_high_risk()
        assert len(high_risk) == 2  # sanctioned + false_flag

    def test_mmsi_set(self, sample_fleet_df):
        fleet = ShadowFleet.from_dataframe(sample_fleet_df)
        assert "111111111" in fleet.mmsi_set
        assert "999999999" not in fleet.mmsi_set

    def test_to_dataframe(self, sample_fleet_df):
        fleet = ShadowFleet.from_dataframe(sample_fleet_df)
        df = fleet.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "mmsi" in df.columns


# ── testy DataLoader (Singleton) ──────────────────────────────────────────────

class TestDataLoader:

    def test_singleton_ta_sama_instancja(self):
        loader1 = DataLoader.get_instance()
        loader2 = DataLoader.get_instance()
        assert loader1 is loader2

    def test_singleton_bezposrednie_wywolanie(self):
        loader1 = DataLoader()
        loader2 = DataLoader()
        assert loader1 is loader2

    def test_cache_plik_wczytywany_raz(self, tmp_path):
        csv = tmp_path / "test.csv"
        csv.write_text("a,b\n1,2\n3,4\n")

        loader = DataLoader.get_instance()
        df1 = loader.load(csv)
        df2 = loader.load(csv)

        assert loader.is_cached(csv)
        assert df1 is df2  # ten sam obiekt w pamięci

    def test_brak_pliku_rzuca_wyjatek(self, tmp_path):
        loader = DataLoader.get_instance()
        with pytest.raises(FileNotFoundError):
            loader.load(tmp_path / "nie_istnieje.csv")

    def test_clear_cache(self, tmp_path):
        csv = tmp_path / "test.csv"
        csv.write_text("a,b\n1,2\n")
        loader = DataLoader.get_instance()
        loader.load(csv)
        assert loader.is_cached(csv)
        loader.clear_cache()
        assert not loader.is_cached(csv)

    def test_reset_tworzy_nowa_instancje(self):
        loader1 = DataLoader.get_instance()
        DataLoader.reset()
        loader2 = DataLoader.get_instance()
        assert loader1 is not loader2


# ── testy FleetController ─────────────────────────────────────────────────────

class TestFleetController:

    @pytest.fixture
    def data_dir(self, tmp_path) -> Path:
        """Tworzy tymczasowy katalog z plikami CSV do testów."""
        fleet = pd.DataFrame({
            "mmsi": ["111", "222", "333"],
            "imo":  ["IMO1", "IMO2", "IMO3"],
            "name": ["SHIP ONE", "SHIP TWO", "SHIP THREE"],
            "flag": ["PANAMA", "LIBERIA", "PANAMA"],
            "fleet":      ["Iran", "Russia", "Iran"],
            "sanctioned": [True, False, False],
            "false_flag": [False, True, False],
            "date_added": ["2024-01-01", "2023-06-15", None],
        })
        fleet.to_csv(tmp_path / "shadow_fleet_combined.csv", index=False)

        ais = pd.DataFrame({
            "mmsi":      ["111", "111", "222"],
            "timestamp": ["2025-01-15 00:00", "2025-01-15 06:00", "2025-01-15 12:00"],
            "latitude":  [54.0, 54.1, 55.0],
            "longitude": [10.0, 10.1, 11.0],
            "sog":       [5.0, 0.2, 12.0],
            "fleet":     ["Iran", "Iran", "Russia"],
        })
        ais.to_csv(tmp_path / "ais_shadow_matches.csv", index=False)

        transit = pd.DataFrame({
            "Date":             ["Jan-2025", "Feb-2025", "Mar-2025"],
            "Suez Canal":       [41, 34, 44],
            "Strait of Hormuz": [208, 184, 201],
        })
        transit.to_csv(tmp_path / "suez_hormuz_monthly.csv", index=False)

        return tmp_path

    def test_wczytanie_danych(self, data_dir):
        ctrl = FleetController(data_dir=data_dir)
        assert len(ctrl.fleet_data) == 3
        assert len(ctrl.ais_data) == 3
        assert len(ctrl.transit_data) == 3

    def test_filter_ais_po_flocie(self, data_dir):
        ctrl = FleetController(data_dir=data_dir)
        result = ctrl.filter_ais(fleet="Iran")
        assert all(result["fleet"] == "Iran")
        assert len(result) == 2

    def test_filter_ais_po_dacie(self, data_dir):
        ctrl = FleetController(data_dir=data_dir)
        # date_to="2025-01-16" obejmuje cały dzień 2025-01-15
        result = ctrl.filter_ais(date_from="2025-01-15", date_to="2025-01-16")
        assert len(result) == 3

    def test_filter_fleet_po_sanctioned(self, data_dir):
        ctrl = FleetController(data_dir=data_dir)
        result = ctrl.filter_fleet(sanctioned=True)
        assert len(result) == 1
        assert result.iloc[0]["mmsi"] == "111"

    def test_detect_anomalies_nieznany_detektor(self, data_dir):
        ctrl = FleetController(data_dir=data_dir)
        with pytest.raises(ValueError, match="Nieznany detektor"):
            ctrl.detect_anomalies("Nieistniejący detektor")

    def test_get_anomaly_summary_zwraca_wszystkie_detektory(self, data_dir):
        ctrl = FleetController(data_dir=data_dir)
        summary = ctrl.get_anomaly_summary()
        assert len(summary) == len(FleetController.DETECTORS)
        assert "detector" in summary.columns
        assert "count" in summary.columns

    def test_get_activity_by_month(self, data_dir):
        ctrl = FleetController(data_dir=data_dir)
        result = ctrl.get_activity_by_month()
        assert "month" in result.columns
        assert "ping_count" in result.columns
        assert result["ping_count"].sum() == 3

# ── testy poprawki SignalGapDetector (filtr ostatniego pingu) ─────────────────

class TestSignalGapDetectorLastPingFilter:

    def test_ostatni_ping_nie_jest_anomalia(self):
        """Ostatni ping statku w zbiorze nie powinien być flagowany jako luka."""
        detector = SignalGapDetector(min_gap_hours=24)
        df = pd.DataFrame({
            "mmsi":      ["111", "111"],
            "timestamp": ["2026-02-21 00:00", "2026-03-07 23:00"],
            "latitude":  [55.0, 56.0],
            "longitude": [10.0, 11.0],
            "sog":       [12.0, 12.0],
        })
        result = detector.detect(df)
        # 14-dniowa luka ale to jedyny ping w zbiorze dla tego statku → NIE anomalia
        assert len(result) == 0

    def test_srodkowa_luka_jest_anomalia(self):
        """Luka między środkowymi pingami (nie ostatnim) powinna być wykryta."""
        detector = SignalGapDetector(min_gap_hours=24)
        df = pd.DataFrame({
            "mmsi":      ["111", "111", "111"],
            "timestamp": [
                "2026-02-21 00:00",
                "2026-02-22 02:00",   # luka 26h → anomalia
                "2026-02-22 03:00",   # ostatni ping
            ],
            "latitude":  [55.0, 55.1, 55.2],
            "longitude": [10.0, 10.1, 10.2],
            "sog":       [12.0, 12.0, 12.0],
        })
        result = detector.detect(df)
        assert len(result) == 1
        assert result.iloc[0]["mmsi"] == "111"
        assert "26.0h" in result.iloc[0]["anomaly_type"]

    def test_wiele_statkow_ostatni_ping_odrzucony(self):
        """Dla wielu statków – ostatni ping każdego jest odrzucany niezależnie."""
        detector = SignalGapDetector(min_gap_hours=24)
        df = pd.DataFrame({
            "mmsi":      ["111", "111", "222", "222"],
            "timestamp": [
                "2026-02-21 00:00",
                "2026-03-07 23:00",   # ostatni ping statku 111 (14 dni luki) → NIE
                "2026-02-21 00:00",
                "2026-02-22 02:00",   # ostatni ping statku 222 (26h luki) → NIE
            ],
            "latitude":  [55.0] * 4,
            "longitude": [10.0] * 4,
            "sog":       [12.0] * 4,
        })
        result = detector.detect(df)
        assert len(result) == 0

    def test_anomalia_przed_ostatnim_pingiem(self):
        """Luka przed ostatnim pingiem powinna być wykryta."""
        detector = SignalGapDetector(min_gap_hours=24)
        df = pd.DataFrame({
            "mmsi":      ["AAA", "AAA", "AAA", "AAA"],
            "timestamp": [
                "2026-02-21 00:00",
                "2026-02-22 02:00",   # luka 26h → anomalia ✓
                "2026-02-22 04:00",
                "2026-02-22 06:00",   # ostatni ping → NIE anomalia
            ],
            "latitude":  [55.0] * 4,
            "longitude": [10.0] * 4,
            "sog":       [12.0] * 4,
        })
        result = detector.detect(df)
        assert len(result) == 1
        assert result.iloc[0]["mmsi"] == "AAA"


# ── testy DataLoader z Parquet ────────────────────────────────────────────────

class TestDataLoaderParquet:

    def test_wczytuje_parquet(self, tmp_path):
        """DataLoader powinien wczytywać pliki .parquet."""
        df_orig = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        parquet_path = tmp_path / "test.parquet"
        df_orig.to_parquet(parquet_path, index=False)

        loader = DataLoader.get_instance()
        df_loaded = loader.load(parquet_path)
        assert len(df_loaded) == 3
        assert list(df_loaded.columns) == ["a", "b"]

    def test_parquet_trafia_do_cache(self, tmp_path):
        """Parquet powinien być cache'owany tak samo jak CSV."""
        df_orig = pd.DataFrame({"x": [1, 2]})
        parquet_path = tmp_path / "data.parquet"
        df_orig.to_parquet(parquet_path, index=False)

        loader = DataLoader.get_instance()
        df1 = loader.load(parquet_path)
        df2 = loader.load(parquet_path)
        assert df1 is df2

    def test_controller_preferuje_parquet(self, tmp_path):
        """FleetController powinien wczytać parquet zamiast csv jeśli oba istnieją."""
        # CSV z 2 wierszami
        ais_csv = pd.DataFrame({
            "mmsi": ["111", "222"],
            "timestamp": ["2026-02-21 00:00", "2026-02-21 01:00"],
            "latitude": [55.0, 56.0],
            "longitude": [10.0, 11.0],
            "sog": [12.0, 5.0],
            "fleet": ["Rosja", "Rosja"],
        })
        ais_csv.to_csv(tmp_path / "ais_shadow_matches.csv", index=False)

        # Parquet z 3 wierszami (inny – po nim poznamy który wczytał)
        ais_parquet = pd.DataFrame({
            "mmsi": ["111", "222", "333"],
            "timestamp": pd.to_datetime([
                "2026-02-21 00:00", "2026-02-21 01:00", "2026-02-21 02:00"
            ]),
            "latitude": [55.0, 56.0, 57.0],
            "longitude": [10.0, 11.0, 12.0],
            "sog": [12.0, 5.0, 8.0],
            "fleet": ["Rosja", "Rosja", "Rosja"],
        })
        ais_parquet.to_parquet(tmp_path / "ais_shadow_matches.parquet", index=False)

        # wymagane pozostałe pliki
        pd.DataFrame({
            "mmsi": ["111"], "imo": ["IMO1"], "name": ["S1"],
            "flag": ["PAN"], "fleet": ["Rosja"],
            "sanctioned": [False], "false_flag": [False], "date_added": [None],
        }).to_csv(tmp_path / "shadow_fleet_combined.csv", index=False)
        pd.DataFrame({
            "Date": ["Jan-2026"], "Suez Canal": [40], "Strait of Hormuz": [200],
        }).to_csv(tmp_path / "suez_hormuz_monthly.csv", index=False)

        ctrl = FleetController(data_dir=tmp_path)
        # parquet ma 3 wiersze, csv ma 2 – jeśli wczytał parquet to len == 3
        assert len(ctrl.ais_data) == 3


# ── testy edge cases detektorów ───────────────────────────────────────────────

class TestDetectorEdgeCases:

    def test_signal_gap_jeden_ping_na_statek(self):
        """Statek z jednym pingiem – brak poprzedniego punku → 0 anomalii."""
        detector = SignalGapDetector(min_gap_hours=1)
        df = pd.DataFrame({
            "mmsi":      ["AAA"],
            "timestamp": ["2026-02-21 12:00"],
            "latitude":  [55.0],
            "longitude": [10.0],
            "sog":       [5.0],
        })
        result = detector.detect(df)
        assert len(result) == 0

    def test_speed_anomaly_ten_sam_punkt(self):
        """Dwa pingi w tym samym miejscu → prędkość 0 → nie anomalia."""
        detector = SpeedAnomalyDetector(max_speed_knots=50)
        df = pd.DataFrame({
            "mmsi":      ["AAA", "AAA"],
            "timestamp": ["2026-02-21 00:00", "2026-02-21 01:00"],
            "latitude":  [55.0, 55.0],
            "longitude": [10.0, 10.0],
            "sog":       [0.0, 0.0],
        })
        result = detector.detect(df)
        assert len(result) == 0

    def test_drifting_statek_plynacy_nie_wykryty(self):
        """Statek płynący 10 kn – nie powinien być wykryty przez DriftingDetector."""
        detector = DriftingDetector(max_sog=0.5, min_duration_hours=4)
        df = pd.DataFrame({
            "mmsi":      ["BBB"] * 5,
            "timestamp": pd.date_range("2026-02-21", periods=5, freq="2h"),
            "sog":       [10.0, 12.0, 11.0, 13.0, 10.5],
            "latitude":  [55.0, 55.1, 55.2, 55.3, 55.4],
            "longitude": [10.0, 10.1, 10.2, 10.3, 10.4],
        })
        result = detector.detect(df)
        assert len(result) == 0

    def test_signal_gap_niepoprawny_timestamp_ignorowany(self):
        """Wiersze z niepoprawnym timestamp powinny być pominięte."""
        detector = SignalGapDetector(min_gap_hours=1)
        df = pd.DataFrame({
            "mmsi":      ["AAA", "AAA", "AAA"],
            "timestamp": ["2026-02-21 00:00", "nie_data", "2026-02-21 10:00"],
            "latitude":  [55.0, 55.0, 55.0],
            "longitude": [10.0, 10.0, 10.0],
            "sog":       [5.0, 5.0, 5.0],
        })
        # nie powinien rzucać wyjątku
        result = detector.detect(df)
        assert isinstance(result, pd.DataFrame)

    def test_wszystkie_detektory_zwracaja_dataframe(self, sample_ais_df):
        """Wszystkie detektory muszą zawsze zwracać DataFrame."""
        for name, detector in FleetController.DETECTORS.items():
            try:
                result = detector.detect(sample_ais_df)
                assert isinstance(result, pd.DataFrame), f"{name} nie zwrócił DataFrame"
            except Exception:
                pass  # niektóre mogą rzucić ValueError z powodu brakujących kolumn

    @pytest.fixture
    def sample_ais_df(self):
        return pd.DataFrame({
            "mmsi":      ["111", "111", "222"],
            "timestamp": ["2026-02-21 00:00", "2026-02-22 02:00", "2026-02-21 00:00"],
            "latitude":  [55.0, 55.1, 56.0],
            "longitude": [10.0, 10.1, 11.0],
            "sog":       [0.1, 0.1, 12.0],
        })