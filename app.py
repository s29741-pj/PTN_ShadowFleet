"""
app.py – główny plik aplikacji Streamlit.

Uruchomienie:
    streamlit run app.py

W PEŁNI STATYCZNA prezentacja danych floty cieni AIS (luty–marzec 2026).
Wszystkie wykresy są gotowymi plikami PNG wygenerowanymi przez
scripts/generate_all_charts.py. Aplikacja nie wykonuje żadnych obliczeń
przy starcie ani przy interakcji – tylko wyświetla.

Wymagane przed pierwszym uruchomieniem:
    python scripts/generate_map_sample.py
    python scripts/generate_anomaly_map_data.py
    python scripts/generate_all_charts.py

Struktura interfejsu:
    Sidebar  – tytuł, opis, źródła danych
    Tab 1    – Przegląd: statystyki i porównanie flot
    Tab 2    – Trendy: ruch przez cieśniny + aktywność floty
    Tab 3    – Anomalie: podsumowanie + tabela podejrzanych statków + mapa
    Tab 4    – Mapa: pozycje statków
    Tab 5    – Profil statków: dane techniczne z Equasis
"""

from pathlib import Path

import pandas as pd
import streamlit as st

CHARTS_DIR = Path(__file__).parent / "data" / "charts"
DATA_DIR = Path(__file__).parent / "data"

# ── konfiguracja strony ───────────────────────────────────────────────────────

st.set_page_config(
    page_title="Flota Cieni – Analiza AIS",
    page_icon="",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── pomocnicze ────────────────────────────────────────────────────────────────


def chart(name: str, caption: str | None = None) -> None:
    """Wyświetla gotowy wykres PNG. Pokazuje ostrzeżenie jeśli plik nie istnieje."""
    path = CHARTS_DIR / f"{name}.png"
    if path.exists():
        st.image(str(path), use_container_width=True)
        if caption:
            st.caption(caption)
    else:
        st.warning(
            f"Brak wygenerowanego wykresu: {name}.png. "
            f"Uruchom scripts/generate_all_charts.py."
        )


@st.cache_data
def load_parquet(name: str) -> pd.DataFrame:
    """Wczytuje gotowy plik Parquet z katalogu data/."""
    path = DATA_DIR / f"{name}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


@st.cache_data
def load_basic_stats() -> dict:
    """Wczytuje podstawowe liczby do metryk – z lekkich plików, bez obliczeń."""
    fleet = load_parquet_csv("shadow_fleet_combined")
    ais_sample = load_parquet("ais_map_sample")

    stats = {
        "statki_na_liscie": len(fleet),
        "sankcje": (
            int(
                fleet.get("sanctioned", pd.Series([False]))
                .astype(str)
                .isin(["True", "true", "1"])
                .sum()
            )
            if not fleet.empty
            else 0
        ),
        "falszywa_bandera": (
            int(
                fleet.get("false_flag", pd.Series([False]))
                .astype(str)
                .isin(["True", "true", "1"])
                .sum()
            )
            if not fleet.empty
            else 0
        ),
    }
    return stats


@st.cache_data
def load_parquet_csv(name: str) -> pd.DataFrame:
    """Wczytuje plik CSV z katalogu data/ (dla małych plików list flot)."""
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str)


# ── sidebar ───────────────────────────────────────────────────────────────────


def render_sidebar() -> None:
    """Renderuje sidebar – tytuł, opis i linki do źródeł."""
    st.sidebar.title("Flota Cieni")
    st.sidebar.title("Flota Cieni")
    st.sidebar.markdown(
        "Analiza aktywności AIS rosyjskiej i irańskiej floty cieni (2025–2026)"
    )
    st.sidebar.divider()
    st.sidebar.markdown(
        "**Źródła danych:**\n"
        "- AIS: [DMA – Bałtyk](http://aisdata.ais.dk/?prefix=)\n"
        "- Flota irańska: [UANI Ghost Armada](https://www.unitedagainstnucleariran.com/blog/stop-hop-ii-ghost-armada-grows)\n"
        "- Flota rosyjska: [GUR / FormerLab](https://github.com/FormerLab/shadow-fleet-tracker-light)\n"
        "- Tranzyt: [UNCTAD 2025](https://unctad.org/publication/review-maritime-transport-2025)\n"
        "- Dane statków: [Kaggle – Global Cargo Ships](https://www.kaggle.com/datasets/ibrahimonmars/global-cargo-ships-dataset)"
    )


# ── zakładki ─────────────────────────────────────────────────────────────────


def render_tab_overview() -> None:
    """Tab 1 – Przegląd floty cieni."""
    st.subheader("Porównanie flot cieni")
    chart("overview_fleet_comparison")

    st.divider()

    st.subheader("Przyrost floty cieni w czasie")
    chart("overview_fleet_growth")

    st.divider()

    st.subheader("Rozkład bander")
    chart("overview_flag_distribution")

    st.divider()

    st.subheader("Lista statków")
    df_fleet = load_parquet_csv("shadow_fleet_combined")
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


def render_tab_trends() -> None:
    """Tab 2 – Trendy w czasie."""
    st.subheader("Ruch przez cieśniny morskie")
    st.caption("Źródło: UNCTAD / Clarksons Research 2025")
    chart("trends_transit")

    st.divider()

    st.subheader("Aktywność floty cieni w danych AIS")
    chart("trends_fleet_activity")

    st.divider()

    st.subheader("Rozkład prędkości SOG")
    col1, col2 = st.columns(2)
    with col1:
        chart("trends_sog_distribution")
    with col2:
        chart("trends_sog_boxplot")

    st.divider()

    st.subheader("Heatmapa aktywności per statek")
    st.caption("Liczba pingów AIS per statek per miesiąc")
    chart("trends_activity_heatmap")

    st.divider()

    st.subheader("Surowe dane AIS")
    ais_sample = load_parquet("trends_raw_sample")
    if not ais_sample.empty:
        st.dataframe(ais_sample.reset_index(drop=True), use_container_width=True)
        st.caption(f"Wyświetlono próbkę {len(ais_sample):,} rekordów")
    else:
        st.info("Brak próbki danych AIS.")


def render_tab_anomalies() -> None:
    """Tab 3 – Anomalie AIS (statyczny widok)."""
    st.info(
        "Dane anomalii AIS dotyczą wyłącznie rosyjskiej floty cieni "
        "(źródło: Danish Maritime Authority, Bałtyk, luty–marzec 2026)."
    )

    st.subheader("Podsumowanie anomalii – wszystkie detektory")
    chart("anomalies_summary")

    st.divider()

    st.subheader("Najbardziej podejrzane statki")
    st.subheader("Najbardziej podejrzane statki")
    st.caption(
        "Na podstawie detektora spoofingu pozycji (niemożliwa prędkość między pingami)"
    )

    chart("anomalies_per_vessel")

    agg = load_parquet("anomalies_table")
    if not agg.empty:
        st.dataframe(agg.reset_index(drop=True), use_container_width=True)
        st.caption(
            "Statki posortowane malejąco według liczby wykrytych anomalii. "
            "Dane wzbogacone o informacje z Equasis."
        )
    else:
        st.warning("Brak tabeli anomalii. Uruchom scripts/generate_all_charts.py.")

    st.divider()

    st.subheader("🗺️ Mapa podejrzanych rejsów")

    options = load_parquet("anomalies_map_options")
    if not options.empty:
        choice_labels = ["Wszystkie statki"] + options["label"].tolist()
        choice = st.selectbox("Wybierz statek", choice_labels, key="anomaly_map_choice")

        if choice == "Wszystkie statki":
            st.caption("Trasy AIS top 8 statków z anomaliami")
            chart("anomalies_map_all")
        else:
            mmsi = options.loc[options["label"] == choice, "mmsi"].iloc[0]
            st.caption(f"Trasa AIS statku {choice}")
            chart(f"anomalies_map_{mmsi}")
    else:
        st.caption("Trasy AIS top 8 statków z anomaliami")
        chart("anomalies_map_all")


def render_tab_map() -> None:
    """Tab 4 – Mapa pozycji statków."""
    st.subheader("Pozycje statków floty cieni")

    map_sample = load_parquet("ais_map_sample")
    if not map_sample.empty:
        st.caption(
            f"Wyświetlono {len(map_sample):,} rekordów "
            f"(zafiksowana próbka, luty–marzec 2026)"
        )
        map_df = map_sample[["latitude", "longitude"]].rename(
            columns={"latitude": "lat", "longitude": "lon"}
        )
        st.map(map_df)
    else:
        st.warning("Brak próbki danych mapy. Uruchom scripts/generate_map_sample.py.")

    st.divider()

    st.subheader("Aktywność per godzina doby")
    st.caption("Czy rosyjska flota cieni jest bardziej aktywna nocą?")
    chart("map_hourly_activity")


def render_tab_vessels() -> None:
    """Tab 5 – Profil statków na podstawie danych Equasis (wszystkie floty)."""
    vessels_path = DATA_DIR / "vessel_details_enriched.csv"
    if not vessels_path.exists():
        st.warning(
            "Brak pliku data/vessel_details_enriched.csv. "
            "Uruchom fetch_equasis_selenium.py żeby pobrać dane."
        )
        return

    st.subheader("Wiek floty cieni")
    chart("vessels_year_built")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Nośność DWT per typ statku")
        chart("vessels_tonnage")
    with col2:
        st.subheader("Towarzystwa klasyfikacyjne")
        chart("vessels_classification")

    st.divider()

    st.subheader("Inspekcje PSC")
    st.caption("Kontrole bezpieczeństwa przez Port State Control")
    chart("vessels_inspections")

    st.divider()

    st.subheader("Zmiany bandery vs wiek statku")
    st.caption("Czy starsze statki częściej zmieniają banderę?")
    chart("vessels_flag_changes_vs_age")

    st.divider()

    st.subheader("Flag hopping – historia zmian bandery")
    st.caption("Statki z największą liczbą poprzednich bander (dane Equasis)")
    chart("vessels_flag_hopping")

    st.divider()

    st.subheader("Statystyki zbiorcze")
    stats = load_parquet("vessels_stats")
    if not stats.empty:
        row = stats.iloc[0]
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "Mediana roku budowy",
            (
                str(int(row["mediana_roku_budowy"]))
                if pd.notna(row["mediana_roku_budowy"])
                else "—"
            ),
        )
        col2.metric(
            "Mediana DWT",
            f"{int(row['mediana_dwt']):,}" if pd.notna(row["mediana_dwt"]) else "—",
        )
        col3.metric(
            "Śr. inspekcji PSC",
            f"{row['sr_inspekcji']:.1f}" if pd.notna(row["sr_inspekcji"]) else "—",
        )
        col4.metric(
            "Śr. zmian bandery",
            (
                f"{row['sr_zmian_bandery']:.1f}"
                if pd.notna(row["sr_zmian_bandery"])
                else "—"
            ),
        )

    st.divider()

    st.subheader("Dane statków")
    vessels = pd.read_csv(vessels_path, dtype=str)
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
        if c in vessels.columns
    ]
    st.dataframe(
        vessels[display_cols].reset_index(drop=True),
        use_container_width=True,
        height=400,
    )


# ── główna pętla aplikacji ────────────────────────────────────────────────────


def main() -> None:
    render_sidebar()

    st.title("Analiza Floty Cieni")
    st.title("Analiza Floty Cieni")
    st.markdown(
        "Statyczna prezentacja aktywności irańskiej i rosyjskiej floty cieni "
        "w danych AIS (luty–marzec 2026)."
    )

    # metryki – z lekkich plików, bez przeliczania
    fleet = load_parquet_csv("shadow_fleet_combined")
    ais_sample = load_parquet("ais_map_sample")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Statki na liście", len(fleet))
    col2.metric(
        "Statków w próbce AIS",
        ais_sample["mmsi"].nunique() if not ais_sample.empty else "—",
    )
    col3.metric(
        "Rekordów w próbce", f"{len(ais_sample):,}" if not ais_sample.empty else "—"
    )
    st.divider()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Przegląd", "Trendy", "Anomalie", "Mapa", "Profil statków"]
    )

    with tab1:
        render_tab_overview()
    with tab2:
        render_tab_trends()
    with tab3:
        render_tab_anomalies()
    with tab4:
        render_tab_map()
    with tab5:
        render_tab_vessels()


if __name__ == "__main__":
    main()
