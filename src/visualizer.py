"""
visualizer.py – wykresy i wizualizacje danych dla aplikacji Streamlit.

Wszystkie funkcje przyjmują DataFrame i zwracają obiekt Figure matplotlib,
który Streamlit renderuje przez st.pyplot(fig).

Dostępne wykresy:
    plot_transit_trends()      – ruch przez Suez i Hormuz w czasie
    plot_fleet_activity()      – aktywność floty cieni per miesiąc
    plot_flag_distribution()   – rozkład bander
    plot_anomaly_summary()     – liczba anomalii per typ detektora
    plot_vessel_map()          – pozycje statków na mapie
"""

from __future__ import annotations

from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import seaborn as sns
import numpy as np

# ── styl globalny ─────────────────────────────────────────────────────────────

PALETTE_FLEET = {"Iran": "#e63946", "Rosja": "#457b9d"}
PALETTE_ANOMALY = ["#e63946", "#f4a261", "#2a9d8f"]

sns.set_theme(style="darkgrid", font_scale=1.1)


# ── pomocnicze ────────────────────────────────────────────────────────────────


def _add_crisis_lines(ax: plt.Axes) -> None:
    """
    Dodaje pionowe linie oznaczające kluczowe daty kryzysów.
    Wywoływana na wykresach z osią czasu.
    """
    crises = {
        "Ataki Huti\n(XII 2023)": "2023-12-01",
        "Blokada Ormuzu\n(II 2026)": "2026-02-01",
    }
    for label, date in crises.items():
        ax.axvline(
            pd.Timestamp(date),
            color="#e63946",
            linestyle="--",
            linewidth=1.2,
            alpha=0.7,
        )
        ax.text(
            pd.Timestamp(date),
            ax.get_ylim()[1] * 0.95,
            label,
            fontsize=8,
            color="#e63946",
            ha="center",
            va="top",
        )


# ── wykresy ───────────────────────────────────────────────────────────────────


def plot_transit_trends(df: pd.DataFrame) -> plt.Figure:
    """
    Wykres liniowy miesięcznego ruchu przez Kanał Sueski i Cieśninę Ormuz.

    Parametry:
        df – DataFrame z kolumnami: Date, Suez Canal, Strait of Hormuz
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")

    if "Suez Canal" in df.columns:
        ax.plot(
            df["Date"],
            df["Suez Canal"],
            label="Kanał Sueski (liczba przepraw)",
            color="#e63946",
            linewidth=2,
            marker="o",
            markersize=4,
        )

    if "Strait of Hormuz" in df.columns:
        ax2 = ax.twinx()
        ax2.plot(
            df["Date"],
            df["Strait of Hormuz"],
            label="Cieśnina Ormuz (mln ton brutto)",
            color="#457b9d",
            linewidth=2,
            marker="s",
            markersize=4,
        )
        ax2.set_ylabel("Cieśnina Ormuz (mln ton brutto)", color="#457b9d")
        ax2.tick_params(axis="y", labelcolor="#457b9d")
        ax2.legend(loc="upper right")

    ax.set_title(
        "Miesięczny ruch przez cieśniny morskie", fontsize=14, fontweight="bold"
    )
    ax.set_xlabel("")
    ax.set_ylabel("Kanał Sueski (liczba przepraw)", color="#e63946")
    ax.tick_params(axis="y", labelcolor="#e63946")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax.legend(loc="upper left")

    _add_crisis_lines(ax)

    fig.tight_layout()
    return fig


def plot_fleet_activity(df: pd.DataFrame, fleet: Optional[str] = None) -> plt.Figure:
    """
    Wykres liniowy aktywności floty cieni (liczba pingów AIS per miesiąc).

    Parametry:
        df    – DataFrame z kolumnami: month, ping_count (wynik get_activity_by_month())
        fleet – opcjonalna etykieta floty do tytułu wykresu
    """
    fig, ax = plt.subplots(figsize=(12, 4))

    df = df.copy()
    df = df[(df["month"] >= "2025-01-01") & (df["month"] <= "2025-12-31")]

    color = PALETTE_FLEET.get(fleet, "#2a9d8f") if fleet else "#2a9d8f"

    ax.fill_between(df["month"], df["ping_count"], alpha=0.2, color=color)
    ax.plot(
        df["month"],
        df["ping_count"],
        color=color,
        linewidth=2,
        marker="o",
        markersize=4,
    )

    title = "Aktywność rosyjskiej floty cieni – Bałtyk (luty–marzec 2026)"
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Liczba pingów AIS")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    fig.tight_layout()
    return fig


def plot_flag_distribution(df: pd.DataFrame, top_n: int = 15) -> plt.Figure:
    """
    Poziomy wykres słupkowy rozkładu bander w flocie cieni.

    Parametry:
        df    – DataFrame z kolumnami: flag, count (wynik get_flag_distribution())
        top_n – liczba najczęstszych bander do wyświetlenia
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    df = df.head(top_n).sort_values("count")

    bars = ax.barh(df["flag"], df["count"], color="#457b9d", edgecolor="white")

    for bar, val in zip(bars, df["count"]):
        ax.text(
            bar.get_width() + 0.3,
            bar.get_y() + bar.get_height() / 2,
            str(val),
            va="center",
            fontsize=9,
        )

    ax.set_title(f"Top {top_n} bander w flocie cieni", fontsize=14, fontweight="bold")
    ax.set_xlabel("Liczba statków")
    ax.set_ylabel("")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig


def plot_anomaly_summary(df: pd.DataFrame) -> plt.Figure:
    """
    Wykres słupkowy liczby wykrytych anomalii per typ detektora.

    Parametry:
        df – DataFrame z kolumnami: detector, count
             (wynik get_anomaly_summary())
    """
    fig, ax = plt.subplots(figsize=(8, 4))

    colors = PALETTE_ANOMALY[: len(df)]
    bars = ax.bar(
        df["detector"], df["count"], color=colors, edgecolor="white", width=0.5
    )

    for bar, val in zip(bars, df["count"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(df["count"]) * 0.01,
            str(val),
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    ax.set_title("Wykryte anomalie AIS per typ", fontsize=14, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Liczba anomalii")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=15, ha="right")

    fig.tight_layout()
    return fig


def plot_vessel_map(df: pd.DataFrame) -> plt.Figure:
    """
    Prosta mapa rozrzutu pozycji statków (lat/lon).
    W Streamlit zastąpiona przez st.map() – ta funkcja służy jako fallback.

    Parametry:
        df – DataFrame z kolumnami: latitude, longitude, fleet
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    df = df.dropna(subset=["latitude", "longitude"])

    for fleet, group in df.groupby("fleet"):
        ax.scatter(
            group["longitude"],
            group["latitude"],
            label=fleet,
            color=PALETTE_FLEET.get(fleet, "#2a9d8f"),
            alpha=0.4,
            s=5,
        )

    ax.set_title(
        "Pozycje statków floty cieni w danych AIS", fontsize=14, fontweight="bold"
    )
    ax.set_xlabel("Długość geograficzna")
    ax.set_ylabel("Szerokość geograficzna")
    ax.legend()
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


def plot_fleet_comparison(df: pd.DataFrame) -> plt.Figure:
    """
    Wykres słupkowy porównujący liczebność i cechy obu flot cieni.

    Parametry:
        df – DataFrame floty cieni z kolumnami: fleet, sanctioned, false_flag
    """
    if "fleet" not in df.columns:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(
            0.5,
            0.5,
            "Brak kolumny 'fleet' w danych",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        return fig

    fig, ax = plt.subplots(figsize=(6, 5))

    counts = df.groupby("fleet").size().reset_index(name="count")
    ax.bar(
        counts["fleet"],
        counts["count"],
        color=[PALETTE_FLEET.get(f, "#aaa") for f in counts["fleet"]],
        edgecolor="white",
        width=0.5,
    )

    for bar, val in zip(ax.patches, counts["count"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + counts["count"].max() * 0.01,
            str(val),
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    ax.set_title("Porównanie flot cieni: Iran vs Rosja", fontsize=14, fontweight="bold")
    ax.set_ylabel("Liczba statków")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig


# ── wykresy profilu floty cieni ───────────────────────────────────────────────


def plot_fleet_growth(df: pd.DataFrame) -> plt.Figure:
    """
    Histogram przyrostu floty cieni w czasie (kiedy statki były dodawane do listy).

    Parametry:
        df – DataFrame floty cieni z kolumną date_added
    """
    fig, ax = plt.subplots(figsize=(12, 4))

    date_col = next((c for c in df.columns if "date" in c.lower()), None)
    if not date_col:
        ax.text(
            0.5,
            0.5,
            "Brak kolumny date_added",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        return fig

    # ogranicz do floty irańskiej – tylko UANI ma daty dodania
    df_plot = df[df["fleet"] == "Iran"] if "fleet" in df.columns else df
    dates = pd.to_datetime(df_plot[date_col], errors="coerce").dropna()
    dates_by_month = dates.dt.to_period("M").value_counts().sort_index()
    cumulative = dates_by_month.cumsum()

    ax2 = ax.twinx()
    ax.bar(
        dates_by_month.index.to_timestamp(),
        dates_by_month.values,
        width=25,
        color="#457b9d",
        alpha=0.6,
        label="Nowe statki (miesięcznie)",
    )
    ax2.plot(
        cumulative.index.to_timestamp(),
        cumulative.values,
        color="#e63946",
        linewidth=2,
        label="Łącznie (narastająco)",
    )

    ax.set_title(
        "Przyrost irańskiej floty cieni w czasie (źródło: UANI)",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xlabel("")
    ax.set_ylabel("Nowe statki / miesiąc", color="#457b9d")
    ax2.set_ylabel("Łącznie statków", color="#e63946")
    ax.tick_params(axis="y", labelcolor="#457b9d")
    ax2.tick_params(axis="y", labelcolor="#e63946")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    fig.tight_layout()
    return fig

def plot_flag_hopping(df: pd.DataFrame, top_n: int = 20) -> plt.Figure:
    """
    Poziomy wykres słupkowy statków z największą liczbą zmian bandery.

    Parametry:
        df    – DataFrame z kolumną flag_change_count lub former_flags (dane z Equasis)
        top_n – liczba statków do wyświetlenia
    """
    fig, ax = plt.subplots(figsize=(12, max(5, top_n * 0.35)))

    name_col = (
        "vessel_name"
        if "vessel_name" in df.columns
        else ("name" if "name" in df.columns else None)
    )
    fleet_col = "fleet" if "fleet" in df.columns else None

    df = df.copy()
    if "flag_change_count" in df.columns:
        df["flag_changes"] = (
            pd.to_numeric(df["flag_change_count"], errors="coerce")
            .fillna(0)
            .astype(int)
        )
    elif "former_flags" in df.columns:

        def count_pipe(val):
            if pd.isna(val) or str(val).strip() in ("", "nan"):
                return 0
            return len([v for v in str(val).split("|") if v.strip()]) - 1

        df["flag_changes"] = df["former_flags"].apply(count_pipe)
    else:
        ax.text(
            0.5,
            0.5,
            "Brak danych o zmianach bandery",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        return fig

    top = df[df["flag_changes"] > 0].nlargest(top_n, "flag_changes")

    if len(top) == 0:
        ax.text(
            0.5,
            0.5,
            "Brak statków ze zmianami bandery",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        return fig

    top_sorted = top.sort_values("flag_changes", ascending=True)
    labels = (
        top_sorted[name_col].fillna("?").str[:20].tolist()
        if name_col
        else top_sorted.index.astype(str).tolist()
    )
    bar_colors = (
        [PALETTE_FLEET.get(str(f), "#457b9d") for f in top_sorted[fleet_col].values]
        if fleet_col
        else ["#457b9d"] * len(top_sorted)
    )
    flag_values = top_sorted["flag_changes"].tolist()

    bars = ax.barh(labels, flag_values, color=bar_colors, edgecolor="white", alpha=0.85)

    for bar, val in zip(bars, flag_values):
        ax.text(
            bar.get_width() + 0.1,
            bar.get_y() + bar.get_height() / 2,
            str(val),
            va="center",
            fontsize=8,
        )

    ax.set_title(
        f"Flag hopping – top {top_n} statków z największą liczbą zmian bandery",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Liczba zmian bandery")
    ax.set_ylabel("")
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if fleet_col:
        from matplotlib.patches import Patch

        fleets_present = top_sorted[fleet_col].unique()
        legend_elements = [
            Patch(facecolor=PALETTE_FLEET.get(f, "#457b9d"), label=f)
            for f in fleets_present
            if f in PALETTE_FLEET
        ]
        if legend_elements:
            ax.legend(handles=legend_elements)

    fig.tight_layout()
    return fig


# ── wykresy anomalii AIS ──────────────────────────────────────────────────────


def plot_sog_distribution(df: pd.DataFrame) -> plt.Figure:
    """
    Histogram rozkładu prędkości (SOG).

    Parametry:
        df – DataFrame AIS z kolumną sog
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    df = df.dropna(subset=["sog"])
    df = df[df["sog"] <= 30]

    ax.hist(df["sog"], bins=40, color="#457b9d", edgecolor="white", alpha=0.8)
    ax.axvline(
        0.5,
        color="#e63946",
        linestyle="--",
        linewidth=1.5,
        label="Próg dryfowania (0.5 kn)",
    )
    ax.set_title(
        "Rozkład prędkości SOG – statki rosyjskie", fontsize=13, fontweight="bold"
    )
    ax.set_xlabel("Prędkość (węzły)")
    ax.set_ylabel("Liczba pingów AIS")
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig


def plot_sog_boxplot(df: pd.DataFrame) -> plt.Figure:
    """
    Box plot prędkości SOG per flota – porównanie profili ruchu.

    Parametry:
        df – DataFrame AIS z kolumnami sog i fleet
    """
    fig, ax = plt.subplots(figsize=(8, 5))

    df = df.dropna(subset=["sog"])
    df = df[df["sog"] <= 30]

    if "fleet" in df.columns:
        fleets = df["fleet"].unique()
        data = [df[df["fleet"] == f]["sog"].values for f in fleets]
        colors = [PALETTE_FLEET.get(f, "#2a9d8f") for f in fleets]

        bp = ax.boxplot(data, tick_labels=fleets, patch_artist=True, notch=False)
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        for median in bp["medians"]:
            median.set_color("white")
            median.set_linewidth(2)
    else:
        ax.boxplot(df["sog"].values, patch_artist=True)

    ax.set_title("Profil prędkości SOG per flota", fontsize=14, fontweight="bold")
    ax.set_xlabel("Flota")
    ax.set_ylabel("Prędkość (węzły)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig


def plot_activity_heatmap(df: pd.DataFrame, top_n: int = 20) -> plt.Figure:
    """
    Heatmapa aktywności AIS: statki (wiersze) × miesiące (kolumny).
    Kolor = liczba pingów.

    Parametry:
        df    – DataFrame AIS z kolumnami mmsi, timestamp, i opcjonalnie name
        top_n – liczba najaktywniejszych statków do wyświetlenia
    """
    fig, ax = plt.subplots(figsize=(14, 8))

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["month"] = df["timestamp"].dt.to_period("M").astype(str)

    top_mmsi = df.groupby("mmsi").size().nlargest(top_n).index
    df_top = df[df["mmsi"].isin(top_mmsi)]

    pivot = df_top.pivot_table(
        index="mmsi", columns="month", aggfunc="size", fill_value=0
    )

    name_col = next((c for c in df.columns if "name" in c.lower()), None)
    if name_col:
        mmsi_to_name = df.drop_duplicates("mmsi").set_index("mmsi")[name_col]
        pivot.index = [f"{mmsi_to_name.get(m, m)[:15]}" for m in pivot.index]

    sns.heatmap(
        pivot,
        ax=ax,
        cmap="YlOrRd",
        linewidths=0.3,
        linecolor="white",
        cbar_kws={"label": "Liczba pingów AIS"},
    )

    ax.set_title(
        f"Heatmapa aktywności – top {top_n} statków per miesiąc",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xlabel("Miesiąc")
    ax.set_ylabel("Statek")
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    plt.setp(ax.yaxis.get_majorticklabels(), fontsize=8)

    fig.tight_layout()
    return fig


def plot_anomaly_per_vessel(anomalies: pd.DataFrame, top_n: int = 15) -> plt.Figure:
    """
    Wykres słupkowy liczby anomalii per statek.

    Parametry:
        anomalies – DataFrame wyników detektora z kolumną mmsi i anomaly_type
        top_n     – liczba statków do wyświetlenia
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    if anomalies.empty:
        ax.text(
            0.5,
            0.5,
            "Brak wykrytych anomalii",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=14,
        )
        return fig

    name_col = next((c for c in anomalies.columns if c.startswith("name")), None)
    label_col = name_col if name_col else "mmsi"

    counts = (
        anomalies.groupby(label_col)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(top_n)
    )

    fleet_col = "fleet" if "fleet" in anomalies.columns else None
    if fleet_col:
        fleet_map = anomalies.drop_duplicates(label_col).set_index(label_col)["fleet"]
        colors = [
            PALETTE_FLEET.get(fleet_map.get(v, ""), "#aaa") for v in counts[label_col]
        ]
    else:
        colors = ["#457b9d"] * len(counts)

    bars = ax.barh(counts[label_col], counts["count"], color=colors, edgecolor="white")

    for bar, val in zip(bars, counts["count"]):
        ax.text(
            bar.get_width() + 0.1,
            bar.get_y() + bar.get_height() / 2,
            str(val),
            va="center",
            fontsize=9,
        )

    ax.set_title(f"Anomalie per statek – top {top_n}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Liczba wykrytych anomalii")
    ax.set_ylabel("")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if fleet_col:
        from matplotlib.patches import Patch

        legend_elements = [
            Patch(facecolor=c, label=f) for f, c in PALETTE_FLEET.items()
        ]
        ax.legend(handles=legend_elements)

    fig.tight_layout()
    return fig


# ── wykresy danych Equasis ────────────────────────────────────────────────────


def plot_year_built_histogram(df: pd.DataFrame) -> plt.Figure:
    """
    Histogram roku budowy statków z podziałem na floty.
    Pokazuje wiek floty cieni.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    df = df.copy()
    df["year_built"] = pd.to_numeric(df["year_built"], errors="coerce")
    df = df.dropna(subset=["year_built"])
    df = df[(df["year_built"] >= 1970) & (df["year_built"] <= 2025)]

    if df.empty:
        for ax in axes:
            ax.text(
                0.5,
                0.5,
                "Brak danych dla wybranej floty",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
        fig.tight_layout()
        return fig

    # ogólny histogram
    axes[0].hist(
        df["year_built"], bins=30, color="#457b9d", edgecolor="white", alpha=0.85
    )
    median_year = df["year_built"].median()
    if pd.notna(median_year):
        axes[0].axvline(
            median_year,
            color="#e63946",
            linestyle="--",
            linewidth=1.5,
            label=f"Mediana: {int(median_year)}",
        )
    axes[0].set_title("Rok budowy – wszystkie statki", fontsize=13, fontweight="bold")
    axes[0].set_xlabel("Rok budowy")
    axes[0].set_ylabel("Liczba statków")
    axes[0].legend()
    axes[0].spines["top"].set_visible(False)
    axes[0].spines["right"].set_visible(False)

    # per flota
    if "fleet" in df.columns:
        for fleet, group in df.groupby("fleet"):
            axes[1].hist(
                group["year_built"],
                bins=25,
                alpha=0.6,
                color=PALETTE_FLEET.get(fleet, "#2a9d8f"),
                label=fleet,
                edgecolor="white",
            )
        axes[1].set_title("Rok budowy per flota", fontsize=13, fontweight="bold")
        axes[1].set_xlabel("Rok budowy")
        axes[1].set_ylabel("Liczba statków")
        axes[1].legend()
        axes[1].spines["top"].set_visible(False)
        axes[1].spines["right"].set_visible(False)
    else:
        axes[1].set_visible(False)

    fig.tight_layout()
    return fig


def plot_tonnage_distribution(df: pd.DataFrame) -> plt.Figure:
    """
    Box plot tonażu DWT per typ statku – top 6 najliczniejszych typów.
    """
    fig, ax = plt.subplots(figsize=(13, 6))

    df = df.copy()
    df["deadweight"] = pd.to_numeric(df["deadweight"], errors="coerce")
    df = df.dropna(subset=["deadweight", "ship_type"])

    if df.empty:
        ax.text(
            0.5,
            0.5,
            "Brak danych dla wybranej floty",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        fig.tight_layout()
        return fig

    top_types = df["ship_type"].value_counts().head(6).index.tolist()
    df_top = df[df["ship_type"].isin(top_types)]

    # filtruj tylko typy które mają co najmniej 1 rekord
    data = [df_top[df_top["ship_type"] == t]["deadweight"].values for t in top_types]
    labels = [
        t.replace(" Tanker", "\nTanker").replace(" Ship", "\nShip") for t in top_types
    ]

    # usuń puste serie (mogą pojawić się po filtrowaniu floty)
    non_empty = [(d, l) for d, l in zip(data, labels) if len(d) > 0]
    if not non_empty:
        ax.text(
            0.5,
            0.5,
            "Brak danych DWT dla wybranej floty",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        fig.tight_layout()
        return fig

    data, labels = zip(*non_empty)

    bp = ax.boxplot(
        list(data),
        labels=list(labels),
        patch_artist=True,
        notch=False,
        showfliers=False,
    )

    colors = ["#457b9d", "#e63946", "#2a9d8f", "#f4a261", "#e9c46a", "#a8dadc"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)
    for median in bp["medians"]:
        median.set_color("white")
        median.set_linewidth(2)

    ax.set_title(
        "Rozkład nośności DWT per typ statku (top 6)", fontsize=14, fontweight="bold"
    )
    ax.set_xlabel("Typ statku")
    ax.set_ylabel("Nośność DWT (tony)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1000:.0f}k"))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig


def plot_inspections_analysis(df: pd.DataFrame) -> plt.Figure:
    """
    Analiza inspekcji PSC:
    - scatter: liczba inspekcji vs rok budowy (starsze = więcej inspekcji?)
    - bar: średnia liczba inspekcji per flota
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    df = df.copy()
    df["inspections_total"] = pd.to_numeric(df["inspections_total"], errors="coerce")
    df["year_built"] = pd.to_numeric(df["year_built"], errors="coerce")
    df = df.dropna(subset=["inspections_total", "year_built"])
    df = df[df["year_built"] >= 1970]

    if "fleet" in df.columns:
        for fleet, group in df.groupby("fleet"):
            axes[0].scatter(
                group["year_built"],
                group["inspections_total"],
                color=PALETTE_FLEET.get(fleet, "#2a9d8f"),
                alpha=0.3,
                s=15,
                label=fleet,
            )
        axes[0].legend()
    else:
        axes[0].scatter(
            df["year_built"], df["inspections_total"], color="#457b9d", alpha=0.3, s=15
        )

    axes[0].set_title("Inspekcje PSC vs rok budowy", fontsize=13, fontweight="bold")
    axes[0].set_xlabel("Rok budowy")
    axes[0].set_ylabel("Liczba inspekcji PSC")
    axes[0].spines["top"].set_visible(False)
    axes[0].spines["right"].set_visible(False)

    if "fleet" in df.columns:
        avg = (
            df.groupby("fleet")["inspections_total"]
            .agg(["mean", "median"])
            .reset_index()
        )
        x = range(len(avg))
        width = 0.35
        axes[1].bar(
            [i - width / 2 for i in x],
            avg["mean"],
            width,
            label="Średnia",
            color="#457b9d",
            alpha=0.8,
        )
        axes[1].bar(
            [i + width / 2 for i in x],
            avg["median"],
            width,
            label="Mediana",
            color="#e63946",
            alpha=0.8,
        )
        axes[1].set_xticks(list(x))
        axes[1].set_xticklabels(avg["fleet"])
        axes[1].set_title("Inspekcje PSC per flota", fontsize=13, fontweight="bold")
        axes[1].set_ylabel("Liczba inspekcji")
        axes[1].legend()
        axes[1].spines["top"].set_visible(False)
        axes[1].spines["right"].set_visible(False)
    else:
        axes[1].set_visible(False)

    fig.tight_layout()
    return fig


def plot_classification_society(df: pd.DataFrame, top_n: int = 10) -> plt.Figure:
    """
    Poziomy wykres słupkowy – towarzystwa klasyfikacyjne z podziałem na floty.
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    df = df.dropna(subset=["classification_society"])
    date_pattern = r"^(January|February|March|April|May|June|July|August|September|October|November|December|[0-9]{4})"
    df = df[~df["classification_society"].str.match(date_pattern, case=False, na=True)]
    df = df[
        df["classification_society"]
        .str.strip()
        .str.lower()
        .isin(["none", "nan", "unknown", ""])
        == False
    ]

    top = df["classification_society"].value_counts().head(top_n).index

    if "fleet" in df.columns:
        pivot = (
            df[df["classification_society"].isin(top)]
            .groupby(["classification_society", "fleet"])
            .size()
            .unstack(fill_value=0)
        )
        pivot = pivot.loc[top]
        bottom = None
        for fleet in pivot.columns:
            color = PALETTE_FLEET.get(fleet, "#2a9d8f")
            ax.barh(
                pivot.index,
                pivot[fleet],
                left=bottom,
                label=fleet,
                color=color,
                alpha=0.8,
            )
            if bottom is None:
                bottom = pivot[fleet].values.copy().astype(float)
            else:
                bottom += pivot[fleet].values
        ax.legend()
    else:
        counts = df["classification_society"].value_counts().head(top_n)
        ax.barh(counts.index[::-1], counts.values[::-1], color="#457b9d")

    ax.set_title(
        f"Top {top_n} towarzystw klasyfikacyjnych", fontsize=14, fontweight="bold"
    )
    ax.set_xlabel("Liczba statków")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig

def plot_hourly_activity(df: pd.DataFrame) -> plt.Figure:
    """
    Histogram aktywności AIS per godzina doby.
    Pokazuje czy rosyjska flota cieni jest bardziej aktywna nocą.

    Parametry:
        df – DataFrame AIS z kolumną timestamp
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])

    if df.empty:
        ax.text(
            0.5,
            0.5,
            "Brak danych z timestampem",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        fig.tight_layout()
        return fig

    hours = df["timestamp"].dt.hour

    ax.hist(
        hours, bins=24, range=(0, 24), color="#457b9d", edgecolor="white", alpha=0.85
    )

    # zaznacz noc (22:00–06:00)
    ax.axvspan(0, 6, alpha=0.08, color="#e63946", label="Noc (00–06)")
    ax.axvspan(22, 24, alpha=0.08, color="#e63946")

    # linia średniej
    mean_hour = hours.mean()
    ax.axvline(
        mean_hour,
        color="#e63946",
        linestyle="--",
        linewidth=1.5,
        label=f"Średnia: {mean_hour:.1f}h",
    )

    ax.set_title(
        "Aktywność AIS per godzina doby – rosyjska flota cieni",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xlabel("Godzina (UTC)")
    ax.set_ylabel("Liczba pingów AIS")
    ax.set_xticks(range(0, 25, 2))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 2)], rotation=45)
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig


def plot_anomaly_map(
    anomalies: pd.DataFrame, all_ais: pd.DataFrame, top_n: int = 15
) -> plt.Figure:
    """
    Mapa tras podejrzanych statków z zaznaczonymi anomaliami i podkladem geograficznym.

    Parametry:
        anomalies – DataFrame wynikow detektora
        all_ais   – DataFrame wszystkich pingow AIS (do rysowania tras)
        top_n     – liczba statkow z najwieksza liczba anomalii
    """
    import matplotlib.cm as cm
    import contextily as cx
    from pyproj import Transformer

    fig, ax = plt.subplots(figsize=(14, 9))

    # wybierz top N statkow
    top_mmsi = (
        anomalies.dropna(subset=["latitude", "longitude"])
        .groupby("mmsi")
        .size()
        .nlargest(top_n)
        .index.tolist()
    )

    if not top_mmsi:
        ax.text(
            0.5,
            0.5,
            "Brak danych pozycyjnych dla anomalii",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        fig.tight_layout()
        return fig

    # kolory per statek
    cmap = cm.get_cmap("tab20", len(top_mmsi))
    color_map = {mmsi: cmap(i) for i, mmsi in enumerate(top_mmsi)}

    # etykiety: nazwa z Equasis lub MMSI
    name_col = (
        "vessel_name"
        if "vessel_name" in anomalies.columns
        else (next((c for c in anomalies.columns if c.startswith("name")), None))
    )

    label_map = {}
    for mmsi in top_mmsi:
        rows = anomalies[anomalies["mmsi"] == mmsi]
        label = mmsi
        if name_col and name_col in rows.columns:
            val = rows[name_col].dropna()
            if len(val) and str(val.iloc[0]).strip() not in ("", "nan", "None"):
                label = str(val.iloc[0])[:20]
        label_map[mmsi] = label

    # transformacja WGS84 -> Web Mercator (wymagane przez contextily)
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

    def to_mercator(lon, lat):
        return transformer.transform(lon, lat)

    # rysuj pelne trasy
    ais_subset = all_ais[all_ais["mmsi"].isin(top_mmsi)].copy()
    ais_subset = ais_subset.dropna(subset=["latitude", "longitude"])

    all_x, all_y = [], []

    for mmsi in top_mmsi:
        color = color_map[mmsi]
        track = (
            ais_subset[ais_subset["mmsi"] == mmsi]
            .sort_values("timestamp")
            .dropna(subset=["latitude", "longitude"])
        )

        if track.empty:
            continue

        x, y = to_mercator(track["longitude"].values, track["latitude"].values)
        all_x.extend(x)
        all_y.extend(y)

        ax.plot(x, y, color=color, linewidth=1.2, alpha=0.55, zorder=2)
        ax.scatter(x, y, color=color, s=5, alpha=0.35, zorder=3)

    # rysuj anomalie jako gwiazdki
    anom_subset = anomalies[anomalies["mmsi"].isin(top_mmsi)].dropna(
        subset=["latitude", "longitude"]
    )

    for mmsi in top_mmsi:
        color = color_map[mmsi]
        anom = anom_subset[anom_subset["mmsi"] == mmsi]
        if anom.empty:
            continue
        x, y = to_mercator(anom["longitude"].values, anom["latitude"].values)
        ax.scatter(
            x,
            y,
            color=color,
            s=150,
            marker="*",
            edgecolors="white",
            linewidths=0.6,
            zorder=5,
            label=label_map[mmsi],
        )

    # dopasuj zakres osi do danych z marginesem
    if all_x and all_y:
        margin_x = (max(all_x) - min(all_x)) * 0.05 or 50000
        margin_y = (max(all_y) - min(all_y)) * 0.05 or 50000
        ax.set_xlim(min(all_x) - margin_x, max(all_x) + margin_x)
        ax.set_ylim(min(all_y) - margin_y, max(all_y) + margin_y)

    # podklad geograficzny – zoom=6 żeby nie pobierać za dużo kafelków
    try:
        cx.add_basemap(
            ax,
            crs="EPSG:3857",
            source=cx.providers.CartoDB.DarkMatter,
            zoom=6,
            alpha=0.85,
        )
    except Exception as e1:
        try:
            cx.add_basemap(
                ax,
                crs="EPSG:3857",
                source=cx.providers.OpenStreetMap.Mapnik,
                zoom=6,
                alpha=0.7,
            )
        except Exception as e2:
            # fallback: ciemne tło bez kafelków
            ax.set_facecolor("#1a1a2e")
            print(f"contextily: {e1} | {e2}")

    ax.set_title(
        f"Trasy podejrzanych rejsow – top {top_n} statkow z anomaliami\n"
        "Linie = pelna trasa AIS  |  \u2605 = wykryta anomalia",
        fontsize=13,
        fontweight="bold",
        color="white" if True else "black",
        pad=12,
    )
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_xticks([])
    ax.set_yticks([])

    # legenda
    ax.legend(
        loc="upper left",
        fontsize=8,
        markerscale=1.4,
        title="Statki (\u2605 = anomalia)",
        title_fontsize=9,
        framealpha=0.85,
        facecolor="#1a1a2e",
        labelcolor="white",
        edgecolor="gray",
        ncol=2 if len(top_mmsi) > 8 else 1,
    )

    fig.patch.set_facecolor("#1a1a2e")
    ax.title.set_color("white")
    fig.tight_layout()
    return fig


def plot_flag_changes_vs_age(df: pd.DataFrame) -> plt.Figure:
    """
    Scatter: liczba zmian bandery vs wiek statku.
    Pokazuje czy starsze statki częściej zmieniają banderę.
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    df = df.copy()
    df["flag_change_count"] = pd.to_numeric(df["flag_change_count"], errors="coerce")
    df["year_built"] = pd.to_numeric(df["year_built"], errors="coerce")
    df = df.dropna(subset=["flag_change_count", "year_built"])
    df["age"] = 2025 - df["year_built"]

    if "fleet" in df.columns:
        for fleet, group in df.groupby("fleet"):
            ax.scatter(
                group["age"],
                group["flag_change_count"],
                color=PALETTE_FLEET.get(fleet, "#2a9d8f"),
                alpha=0.35,
                s=20,
                label=fleet,
            )
        ax.legend()
    else:
        ax.scatter(
            df["age"], df["flag_change_count"], color="#457b9d", alpha=0.35, s=20
        )

    valid = df.dropna(subset=["age", "flag_change_count"])
    if len(valid) > 10:
        z = np.polyfit(valid["age"], valid["flag_change_count"], 1)
        p = np.poly1d(z)
        x_line = np.linspace(valid["age"].min(), valid["age"].max(), 100)
        ax.plot(
            x_line,
            p(x_line),
            color="#e63946",
            linewidth=1.5,
            linestyle="--",
            label="Trend",
        )
        ax.legend()

    ax.set_title("Zmiany bandery vs wiek statku", fontsize=14, fontweight="bold")
    ax.set_xlabel("Wiek statku (lata)")
    ax.set_ylabel("Liczba zmian bandery")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig
