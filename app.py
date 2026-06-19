"""
app.py – główny plik aplikacji Streamlit.

Uruchomienie:
    streamlit run app.py

Struktura interfejsu:
    Sidebar  – filtry: flota, zakres dat, typ detektora
    Tab 1    – Przegląd: statystyki i porównanie flot
    Tab 2    – Trendy: ruch przez cieśniny + aktywność floty
    Tab 3    – Anomalie: wyniki detektorów
    Tab 4    – Mapa: pozycje statków
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# dodaj src do ścieżki – pliki klas są w podkatalogu src/
sys.path.insert(0, str(Path(__file__).parent / "src"))

from controller import DataLoader, FleetController
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
    plot_inspections_analysis,
    plot_sog_boxplot,
    plot_sog_distribution,
    plot_tonnage_distribution,
    plot_transit_trends,
    plot_vessel_map,
    plot_hourly_activity,
    plot_anomaly_map,
    plot_year_built_histogram,
)

# ── konfiguracja strony ───────────────────────────────────────────────────────

st.set_page_config(
    page_title="Flota Cieni – Analiza AIS",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── wczytanie danych (cache Streamlit + Singleton DataLoader) ─────────────────


@st.cache_data
def load_controller() -> FleetController:
    """
    Wczytuje dane i zwraca kontroler.
    @st.cache_data gwarantuje że dane są ładowane tylko raz per sesja.
    """
    ctrl = FleetController(data_dir=Path(__file__).parent / "data")
    ctrl.load_all()
    return ctrl


@st.cache_data
def load_vessel_details() -> pd.DataFrame:
    """Wczytuje dane statków z Equasis (vessel_details_enriched.csv)."""
    path = Path(__file__).parent / "data" / "vessel_details_enriched.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str)


# ── sidebar ───────────────────────────────────────────────────────────────────


def render_sidebar(ctrl: FleetController) -> dict:
    """Renderuje sidebar z filtrami. Zwraca słownik wybranych wartości."""
    st.sidebar.title("🚢 Flota Cieni")
    st.sidebar.markdown(
        "Analiza aktywności AIS rosyjskiej i irańskiej floty cieni (2025–2026)"
    )
    st.sidebar.divider()

    fleet       = None
    fleet_label = "Wszystkie"

    st.sidebar.divider()
    if st.sidebar.button("🔄 Odśwież dane"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown(
        "**Źródła danych:**\n"
        "- AIS: [DMA – Bałtyk](http://aisdata.ais.dk/?prefix=)\n"
        "- Flota irańska: [UANI Ghost Armada](https://www.unitedagainstnucleariran.com/blog/stop-hop-ii-ghost-armada-grows)\n"
        "- Flota rosyjska: [GUR / FormerLab](https://github.com/FormerLab/shadow-fleet-tracker-light)\n"
        "- Tranzyt: [UNCTAD 2025](https://unctad.org/publication/review-maritime-transport-2025)\n"
        "- Dane statków: [Kaggle – Global Cargo Ships](https://www.kaggle.com/datasets/ibrahimonmars/global-cargo-ships-dataset)"
    )

    return {
        "fleet": fleet,
        "fleet_label": fleet_label,
        "date_from": None,
        "date_to": None,
        "detector_name": None,
    }


# ── metryki pomocnicze ────────────────────────────────────────────────────────


def render_metrics(ctrl: FleetController, filters: dict) -> None:
    """Wyświetla metryki w górnej części strony."""
    fleet = filters["fleet"]
    date_from = filters["date_from"]
    date_to = filters["date_to"]

    ais_filtered = ctrl.filter_ais(fleet=fleet, date_from=date_from, date_to=date_to)
    fleet_filtered = ctrl.filter_fleet(fleet=fleet)

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Statki na liście", len(fleet_filtered))
    col2.metric("Unikalne MMSI w AIS", ais_filtered["mmsi"].nunique())
    col3.metric("Rekordów AIS", f"{len(ais_filtered):,}")
    col4.metric(
        "Objętych sankcjami",
        int(fleet_filtered.get("sanctioned", pd.Series([False])).sum()),
    )
    col5.metric(
        "Z fałszywą banderą",
        int(fleet_filtered.get("false_flag", pd.Series([False])).sum()),
    )


# ── zakładki ─────────────────────────────────────────────────────────────────


def render_tab_overview(ctrl: FleetController, filters: dict) -> None:
    """Tab 1 – Przegląd floty cieni."""
    fleet = filters["fleet"]

    st.subheader("Porównanie flot cieni")
    fig = plot_fleet_comparison(ctrl.fleet_data)
    st.pyplot(fig)

    st.divider()

    st.subheader("Przyrost floty cieni w czasie")
    fig = plot_fleet_growth(ctrl.fleet_data)
    st.pyplot(fig)

    st.divider()

    st.subheader("Rozkład bander")
    fig = plot_flag_distribution(ctrl.get_flag_distribution(fleet=fleet))
    st.pyplot(fig)

    st.divider()

    st.subheader("Lista statków")
    df_fleet = ctrl.filter_fleet(fleet=fleet)
    display_cols = [
        c
        for c in [
            "mmsi",
            "name",
            "vessel_name",
            "flag",
            "current_flag_clean",
            "fleet",
            "sanctioned",
            "false_flag",
            "date_added",
        ]
        if c in df_fleet.columns
    ]
    st.dataframe(
        df_fleet[display_cols].reset_index(drop=True),
        use_container_width=True,
        height=400,
    )


def render_tab_trends(ctrl: FleetController, filters: dict) -> None:
    """Tab 2 – Trendy w czasie."""
    fleet = "Rosja"  # dane AIS tylko dla Rosji (DMA Bałtyk)
    date_from = filters["date_from"]
    date_to = filters["date_to"]

    st.subheader("Ruch przez cieśniny morskie")
    st.caption("Źródło: UNCTAD / Clarksons Research 2025")
    fig = plot_transit_trends(ctrl.transit_data)
    st.pyplot(fig)

    st.divider()

    st.subheader("Aktywność floty cieni w danych AIS")
    activity = ctrl.get_activity_by_month(fleet=fleet)
    if activity.empty:
        st.info("Brak danych AIS dla wybranych filtrów.")
    else:
        fig = plot_fleet_activity(activity, fleet=fleet)
        st.pyplot(fig)

    st.divider()

    st.divider()

    st.subheader("Rozkład prędkości SOG")
    ais_filtered = ctrl.filter_ais(fleet=fleet, date_from=date_from, date_to=date_to)
    if not ais_filtered.empty and "sog" in ais_filtered.columns:
        col1, col2 = st.columns(2)
        with col1:
            fig = plot_sog_distribution(ais_filtered)
            st.pyplot(fig)
        with col2:
            fig = plot_sog_boxplot(ais_filtered)
            st.pyplot(fig)

    st.divider()

    st.subheader("Heatmapa aktywności per statek")
    st.caption("Liczba pingów AIS per statek per miesiąc")
    if not ais_filtered.empty:
        fig = plot_activity_heatmap(ais_filtered, top_n=20)
        st.pyplot(fig)

    st.divider()

    st.subheader("Surowe dane AIS")
    ais = ctrl.filter_ais(fleet=fleet, date_from=date_from, date_to=date_to)
    display_cols = [
        c
        for c in [
            "mmsi",
            "timestamp",
            "latitude",
            "longitude",
            "sog",
            "fleet",
            "name",
            "name_x",
            "ais_source",
        ]
        if c in ais.columns
    ]
    st.dataframe(
        ais[display_cols].head(1000).reset_index(drop=True), use_container_width=True
    )
    st.caption(f"Wyświetlono pierwsze 1000 z {len(ais):,} rekordów")


def render_tab_anomalies(ctrl: FleetController, filters: dict) -> None:
    """Tab 3 – Wykrywanie anomalii."""
    # anomalie wykrywamy tylko dla Rosji – mamy dane AIS z Bałtyku (DMA)
    fleet = "Rosja"
    st.info("Dane anomalii AIS dotyczą wyłącznie rosyjskiej floty cieni "
            "(źródło: Danish Maritime Authority, Bałtyk, luty–marzec 2026).")

    # zakres dat i detektor – widoczne tylko w tej zakładce
    col1, col2 = st.columns(2)
    with col1:
        ais = ctrl.ais_data
        if "timestamp" in ais.columns and ais["timestamp"].notna().any():
            min_date = ais["timestamp"].min().date()
            max_date = ais["timestamp"].max().date()
        else:
            min_date = pd.Timestamp("2025-01-01").date()
            max_date = pd.Timestamp("2026-06-01").date()
        date_from = st.date_input(
            "Od",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
            key="anomaly_date_from",
        )
        date_to = st.date_input(
            "Do",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
            key="anomaly_date_to",
        )
    with col2:
        detector_name = st.selectbox(
            "Detektor anomalii",
            list(FleetController.DETECTORS.keys()),
            key="anomaly_detector",
        )
        detector_obj = FleetController.DETECTORS[detector_name]
        st.caption(detector_obj.description)

    date_from = str(date_from)
    date_to = str(date_to)

    st.divider()

    # podsumowanie wszystkich detektorów
    st.subheader("Podsumowanie anomalii – wszystkie detektory")
    summary = ctrl.get_anomaly_summary(fleet=fleet)
    fig = plot_anomaly_summary(summary)
    st.pyplot(fig)

    st.divider()

    # wyniki wybranego detektora
    st.subheader(f"Wyniki: {detector_name}")
    detector = FleetController.DETECTORS[detector_name]
    st.caption(detector.description)

    with st.spinner("Wykrywanie anomalii..."):
        anomalies = ctrl.detect_anomalies(
            detector_name=detector_name,
            fleet=fleet,
            date_from=date_from,
            date_to=date_to,
        )

    if anomalies.empty:
        st.success("Nie wykryto anomalii dla wybranych filtrów.")
    else:
        st.warning(
            f"Wykryto **{len(anomalies)}** anomalii "
            f"dla **{anomalies['mmsi'].nunique()}** unikalnych statków."
        )

        display_cols = [
            c
            for c in [
                "mmsi",
                "timestamp",
                "latitude",
                "longitude",
                "sog",
                "fleet",
                "anomaly_type",
                "ais_source",
            ]
            if c in anomalies.columns
        ]
        st.dataframe(
            anomalies[display_cols].reset_index(drop=True),
            use_container_width=True,
        )

        # wykres per statek
        st.subheader("Statki z największą liczbą anomalii")
        fig = plot_anomaly_per_vessel(anomalies, top_n=15)
        st.pyplot(fig)

        # tabela podejrzanych statków z detalami
        st.subheader("🔍 Najbardziej podejrzane statki")
        name_col = next((c for c in anomalies.columns if c.startswith("name")), None)
        group_cols = ["mmsi"] + ([name_col] if name_col else [])
        group_cols = [c for c in group_cols if c in anomalies.columns]

        # agreguj anomalie per statek
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
            .head(20)
        )

        # wzbogać o dane z vessel_details jeśli dostępne
        vessel_path = Path(__file__).parent / "data" / "vessel_details_enriched.csv"
        if vessel_path.exists():
            vessels = pd.read_csv(vessel_path, dtype=str)[
                ["mmsi", "vessel_name", "ship_type", "flag", "year_built",
                 "gross_tonnage", "sanctioned", "false_flag"]
            ]
            vessels["mmsi"] = vessels["mmsi"].astype(str).str.strip()
            agg["mmsi"] = agg["mmsi"].astype(str).str.strip()
            agg = agg.merge(vessels, on="mmsi", how="left")

        st.dataframe(agg.reset_index(drop=True), use_container_width=True)
        st.caption("Statki posortowane malejąco według liczby wykrytych anomalii. "
                   "Dane wzbogacone o informacje z Equasis.")

        # mapa podejrzanych rejsów
        st.divider()
        st.subheader("🗺️ Mapa podejrzanych rejsów")
        st.caption("Pozycje statków z wykrytymi anomaliami – każdy kolor to inny typ anomalii")

        map_anomalies = anomalies.dropna(subset=["latitude", "longitude"])

        if not map_anomalies.empty:
            # wzbogać o nazwy statków z vessel_details jeśli dostępne
            vessel_path = Path(__file__).parent / "data" / "vessel_details_enriched.csv"
            if vessel_path.exists():
                vessels = pd.read_csv(vessel_path, dtype=str)[["mmsi", "vessel_name"]]
                vessels["mmsi"] = vessels["mmsi"].astype(str).str.strip()
                map_anomalies = map_anomalies.copy()
                map_anomalies["mmsi"] = map_anomalies["mmsi"].astype(str).str.strip()
                map_anomalies = map_anomalies.merge(vessels, on="mmsi", how="left")

            # wszystkie pingi AIS dla podejrzanych statków (do rysowania tras)
            all_ais = ctrl.ais_data.copy()
            all_ais["mmsi"] = all_ais["mmsi"].astype(str).str.strip()

            fig = plot_anomaly_map(map_anomalies, all_ais, top_n=15)
            st.pyplot(fig)
        else:
            st.info("Brak danych pozycyjnych dla wykrytych anomalii.")


def render_tab_map(ctrl: FleetController, filters: dict) -> None:
    """Tab 4 – Mapa pozycji statków."""
    st.subheader("Pozycje statków floty cieni")

    # dane pełne – potrzebne do histogramu godzinowego niezależnie od próbki mapy
    ais = ctrl.ais_data.dropna(subset=["latitude", "longitude"])

    # zafiksowana próbka wygenerowana raz przez scripts/generate_map_sample.py
    # (szybsze ładowanie niż losowanie 50k z 924k wierszy przy każdym starcie)
    sample_path = Path(__file__).parent / "data" / "ais_map_sample.parquet"

    if sample_path.exists():
        map_sample = pd.read_parquet(sample_path)
        st.caption(f"Wyświetlono {len(map_sample):,} rekordów "
                   f"(zafiksowana próbka, luty–marzec 2026)")
        map_df = map_sample[["latitude", "longitude"]].rename(
            columns={"latitude": "lat", "longitude": "lon"}
        )
    else:
        # fallback: losowanie na żywo, jeśli próbka nie została wygenerowana
        st.caption(f"Wyświetlono {min(len(ais), 50_000):,} z {len(ais):,} rekordów "
                   f"(próbka losowa – uruchom scripts/generate_map_sample.py "
                   f"dla szybszego ładowania)")
        map_df = (
            ais[["latitude", "longitude"]]
            .rename(columns={"latitude": "lat", "longitude": "lon"})
            .sample(n=min(50_000, len(ais)), random_state=42)
        )

    st.map(map_df)

    st.divider()

    with st.expander("ℹ️ Jak dane AIS dowodzą spoofingu pozycji?", expanded=False):
        st.markdown("""
**Spoofing pozycji GPS/AIS** polega na fałszowaniu sygnału nawigacyjnego tak, 
aby system AIS raportował inną lokalizację niż rzeczywista.

**Jak to wykrywamy:**
Nasz detektor (`SpeedAnomalyDetector`) porównuje kolejne pingi AIS tego samego statku.
Oblicza odległość między pozycjami wzorem **Haversine** i dzieli przez czas między pingami.
Jeśli obliczona prędkość przekracza **50 węzłów** – jest to fizycznie niemożliwe dla tankowca
(maksymalna prędkość to ok. 16–18 węzłów) i wskazuje na sfałszowaną pozycję.

**Co widać na mapie:**
Przerywane ślady AIS w okolicach Cieśnin Duńskich (Sund, Wielki Bełt) to efekt 
**wyłączania transpondera** przy przejściu przez kluczowy punkt monitoringu NATO/UE.
Statek znika z radaru w jednym miejscu i pojawia się setki mil dalej – 
tworząc pozornie niemożliwy "skok pozycji".

**Dlaczego Cieśniny Duńskie?**
To wąskie gardło między Bałtykiem a Morzem Północnym, intensywnie monitorowane przez 
Danię i NATO. Rosyjskie tankowce wyłączają AIS właśnie tu, aby utrudnić śledzenie 
tras i identyfikację ładunku (ropa objęta sankcjami).
        """)

    st.divider()

    st.subheader("Aktywność per godzina doby")
    st.caption("Czy rosyjska flota cieni jest bardziej aktywna nocą?")
    fig = plot_hourly_activity(ais)
    st.pyplot(fig)


# ── Tab: Profil statków ──────────────────────────────────────────────────────


def render_tab_vessels(df: pd.DataFrame, filters: dict) -> None:
    """Tab 5 – Profil statków na podstawie danych Equasis."""
    if df.empty:
        st.warning(
            "Brak pliku data/vessel_details_enriched.csv. "
            "Uruchom fetch_equasis_selenium.py żeby pobrać dane."
        )
        return

    # filtr floty dostępny tylko tutaj
    fleet_options = ["Wszystkie", "Iran", "Rosja"]
    fleet_label = st.selectbox("Filtruj flotę", fleet_options, key="vessels_fleet")
    fleet = None if fleet_label == "Wszystkie" else fleet_label

    if fleet and "fleet" in df.columns:
        df = df[df["fleet"] == fleet]

    st.subheader("Wiek floty cieni")
    fig = plot_year_built_histogram(df)
    st.pyplot(fig)

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Nośność DWT per typ statku")
        fig = plot_tonnage_distribution(df)
        st.pyplot(fig)
    with col2:
        st.subheader("Towarzystwa klasyfikacyjne")
        fig = plot_classification_society(df)
        st.pyplot(fig)

    st.divider()

    st.subheader("Inspekcje PSC")
    st.caption("Kontrole bezpieczeństwa przez Port State Control")
    fig = plot_inspections_analysis(df)
    st.pyplot(fig)

    st.divider()

    st.subheader("Zmiany bandery vs wiek statku")
    st.caption("Czy starsze statki częściej zmieniają banderę?")
    fig = plot_flag_changes_vs_age(df)
    st.pyplot(fig)

    st.divider()

    st.subheader("Flag hopping – historia zmian bandery")
    st.caption("Statki z największą liczbą poprzednich bander (dane Equasis)")
    # vessel_details_enriched ma kolumnę former_flags z historią Equasis
    if "former_flags" in df.columns:
        fig = plot_flag_hopping(df)
        st.pyplot(fig)
    else:
        st.info("Brak kolumny former_flags w danych.")

    st.divider()

    # metryki zbiorcze
    st.subheader("Statystyki zbiorcze")
    df_num = df.copy()
    for col in [
        "year_built",
        "gross_tonnage",
        "deadweight",
        "inspections_total",
        "flag_change_count",
        "name_change_count",
    ]:
        df_num[col] = pd.to_numeric(df_num[col], errors="coerce")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Mediana roku budowy",
        (
            f"{int(df_num['year_built'].median())}"
            if df_num["year_built"].notna().any()
            else "—"
        ),
    )
    col2.metric(
        "Mediana DWT",
        (
            f"{int(df_num['deadweight'].median()):,}"
            if df_num["deadweight"].notna().any()
            else "—"
        ),
    )
    col3.metric(
        "Śr. inspekcji PSC",
        (
            f"{df_num['inspections_total'].mean():.1f}"
            if df_num["inspections_total"].notna().any()
            else "—"
        ),
    )
    col4.metric(
        "Śr. zmian bandery",
        (
            f"{df_num['flag_change_count'].mean():.1f}"
            if df_num["flag_change_count"].notna().any()
            else "—"
        ),
    )

    st.divider()

    # tabela danych surowych
    st.subheader("Dane statków")
    display_cols = [
        c
        for c in [
            "imo",
            "vessel_name",
            "ship_type",
            "flag",
            "year_built",
            "gross_tonnage",
            "deadweight",
            "inspections_total",
            "flag_change_count",
            "fleet",
            "sanctioned",
            "false_flag",
            "classification_society",
            "registered_owner",
        ]
        if c in df.columns
    ]
    st.dataframe(
        df[display_cols].reset_index(drop=True), use_container_width=True, height=400
    )


# ── główna pętla aplikacji ────────────────────────────────────────────────────


def main() -> None:
    try:
        ctrl = load_controller()
    except FileNotFoundError as e:
        st.error(f"Nie znaleziono pliku danych: {e}")
        st.info("Upewnij się że katalog `data/` zawiera wymagane pliki CSV.")
        st.stop()
    except Exception as e:
        st.error(f"Błąd podczas wczytywania danych: {e}")
        st.stop()

    # sidebar
    filters = render_sidebar(ctrl)

    # tytuł
    st.title("🚢 Analiza Floty Cieni")
    st.markdown(
        f"Aktywność irańskiej i rosyjskiej floty cieni w danych AIS (2025–2026) "
        f"| Filtr: **{filters['fleet_label']}** "
        f"| {filters['date_from']} – {filters['date_to']}"
    )

    # metryki
    render_metrics(ctrl, filters)
    st.divider()

    # zakładki
    vessel_df = load_vessel_details()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "📊 Przegląd",
            "📈 Trendy",
            "⚠️ Anomalie",
            "🗺️ Mapa",
            "🚢 Profil statków",
        ]
    )

    with tab1:
        render_tab_overview(ctrl, filters)
    with tab2:
        render_tab_trends(ctrl, filters)
    with tab3:
        render_tab_anomalies(ctrl, filters)
    with tab4:
        render_tab_map(ctrl, filters)
    with tab5:
        render_tab_vessels(vessel_df, filters)


if __name__ == "__main__":
    main()