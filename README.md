# 🚢 Analiza Floty Cieni – Monitoring AIS

Projekt zaliczeniowy z przedmiotu **Podstawy Technologii Nowych (Python)**, PJATK, semestr 6.

Interaktywna aplikacja Streamlit do analizy aktywności rosyjskiej i irańskiej **floty cieni** w danych AIS (Automatic Identification System). Projekt koncentruje się na okresie **21 lutego – 7 marca 2026** – dwóch tygodniach obejmujących atak USA na Iran i zamknięcie Cieśniny Ormuz (28 lutego 2026), który miał potencjalny wpływ na aktywność tankowców na Morzu Bałtyckim.

---

## Struktura projektu

```
projekt/
├── app.py                          – główna aplikacja Streamlit
├── requirements.txt                – zależności Python
├── data/
│   ├── ais_shadow_matches.parquet  – dopasowane dane AIS (21 MB, po redukcji)
│   ├── shadow_fleet_combined.csv   – połączona lista floty cieni (1 313 statków)
│   ├── ghost_armada_iran.csv       – lista irańskiej floty cieni (UANI, 136 statków)
│   ├── shadow_fleet_russia.csv     – lista rosyjskiej floty cieni (GUR, 1 206 statków)
│   ├── vessel_details_enriched.csv – dane techniczne statków z Equasis (1 304 statki)
│   ├── suez_hormuz_monthly.csv     – miesięczny ruch przez Suez i Ormuz (UNCTAD)
│   └── ais_dma/                    – przefiltrowane dane AIS (15 plików dziennych)
├── src/
│   ├── analysis.py                 – detektory anomalii (Strategy Pattern)
│   ├── controller.py               – logika biznesowa (Singleton DataLoader)
│   ├── models.py                   – modele danych (Vessel, AISRecord, ShadowFleet)
│   └── visualizer.py               – wykresy matplotlib/seaborn
├── scripts/
│   ├── parse_uani.py               – parsowanie listy irańskiej (HTML → CSV)
│   ├── parse_gur.py                – eksport listy rosyjskiej (SQLite → CSV)
│   ├── filter_ais_dma.py           – filtrowanie tankowców z danych DMA
│   ├── merge_shadow_fleet.py       – łączenie list flot + dopasowanie do AIS
│   ├── fetch_equasis_selenium.py   – pobieranie danych statków z Equasis
│   ├── reduce_ais.py               – redukcja rozmiaru pliku AIS do wdrożenia
│   └── fix_excel_csv.py            – naprawa kodowania CSV po edycji w Excelu
└── tests/
    └── tests_analysis.py           – testy jednostkowe detektorów anomalii
```

---

## Źródła danych

| Dane | Źródło | Format |
|---|---|---|
| AIS – Bałtyk | [Danish Maritime Authority](http://aisdata.ais.dk/?prefix=) | CSV (~0.5 GB/dzień) |
| Flota irańska | [UANI Ghost Armada](https://www.unitedagainstnucleariran.com/blog/stop-hop-ii-ghost-armada-grows) | HTML → CSV |
| Flota rosyjska | [GUR / FormerLab](https://github.com/FormerLab/shadow-fleet-tracker-light) | SQLite → CSV |
| Tranzyt Suez/Ormuz | [UNCTAD 2025](https://unctad.org/publication/review-maritime-transport-2025) | CSV |
| Dane techniczne statków | [Equasis](https://www.equasis.org) (Selenium) | CSV |
| Dane statyczne statków | [Kaggle – Global Cargo Ships](https://www.kaggle.com/datasets/ibrahimonmars/global-cargo-ships-dataset) | CSV |

---

## Architektura

Projekt stosuje wzorce projektowe **MVC**, **Strategy** i **Singleton**:

**Strategy Pattern – detektory anomalii** (`src/analysis.py`)

Każdy detektor implementuje interfejs `AnomalyDetector` z metodą `detect(df)`. Nowe strategie można dodawać bez modyfikacji reszty kodu.

```python
# trzy wymienne strategie wykrywania anomalii
DETECTORS = {
    "Luka w sygnale":   SignalGapDetector(min_gap_hours=24),
    "Spoofing pozycji": SpeedAnomalyDetector(max_speed_knots=50),
    "Dryfowanie STS":   DriftingDetector(max_sog=0.5, min_duration_hours=4),
}
```

**Singleton Pattern – DataLoader** (`src/controller.py`)

Gwarantuje jednokrotne wczytanie danych CSV/Parquet niezależnie od liczby wywołań w sesji Streamlit.

---

## Instalacja i uruchomienie

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/UZYTKOWNIK/shadow-fleet-ais.git
cd shadow-fleet-ais

# 2. Utwórz i aktywuj środowisko wirtualne
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/macOS

# 3. Zainstaluj zależności
pip install -r requirements.txt

# 4. Uruchom aplikację
streamlit run app.py
```

---

## Pipeline danych

Dane przygotowuje się jednorazowo przed uruchomieniem aplikacji:

```bash
# 1. Pobierz i sparsuj listy floty cieni
python scripts/parse_uani.py
python scripts/parse_gur.py

# 2. Przefiltruj dane AIS do tankowców (powtórz dla każdego dnia)
python scripts/filter_ais_dma.py --input data/raw/aisdk-2026-02-21.csv \
                                  --output data/ais_dma/tankers_2026-02-21.csv

# 3. Scal listy flot i dopasuj do danych AIS
python scripts/merge_shadow_fleet.py

# 4. (Opcjonalnie) Pobierz dane techniczne statków z Equasis
python scripts/fetch_equasis_selenium.py --email EMAIL --password HASLO

# 5. Zredukuj rozmiar pliku AIS do wdrożenia
python scripts/reduce_ais.py
```

---

## Detektory anomalii

### SignalGapDetector
Wykrywa przerwy w sygnale AIS przekraczające 24 godziny. Celowe wyłączenie transpondera to klasyczna taktyka floty cieni przy przejściu przez monitorowane cieśniny. Filtruje fałszywe alarmy: ostatni ping statku w zbiorze danych jest odrzucany (koniec okresu próbkowania, nie wyłączenie urządzenia).

### SpeedAnomalyDetector
Oblicza odległość między kolejnymi pingami wzorem **Haversine** i przelicza na prędkość. Jeśli wynik przekracza 50 węzłów – fizycznie niemożliwe dla tankowca (max ~17 kn) – wykrywa spoofing pozycji GPS/AIS.

### DriftingDetector
Szuka ciągłych okresów gdy SOG < 0.5 węzła przez ponad 4 godziny. Tankowiec unieruchomiony na otwartym morzu poza kotwicowiskiem może prowadzić transfer ropy statek-statek (STS) – kluczową metodę omijania sankcji.

---

## Zakres danych AIS

Dane obejmują **14 dni ciągłych**: 21 lutego – 7 marca 2026 (Morze Bałtyckie, stacja DMA). Okres celowo obejmuje zamknięcie Cieśniny Ormuz przez Iran (28 lutego 2026) jako naturalny eksperyment – analiza czy event geopolityczny wpłynął na aktywność rosyjskiej floty cieni na Bałtyku.

Surowe pliki DMA (~0.5 GB/dzień) są filtrowane do samych tankowców (`Ship type = Tanker`), następnie dopasowywane do listy floty cieni po MMSI.

---

## Testy

```bash
pytest tests/tests_analysis.py -v
```

---

## Ograniczenia metodologiczne

- Dane AIS z DMA obejmują wyłącznie Morze Bałtyckie – irańska flota cieni operuje przy Cieśninie Ormuz i nie jest widoczna w tych danych. Zakładka **Anomalie** prezentuje tylko flotę rosyjską.
- Lista floty cieni (GUR/UANI) może być niekompletna – część statków operuje bez rejestracji lub pod wieloma MMSI.
- Kolumna `date_added` dostępna tylko dla floty irańskiej (UANI) – wykres przyrostu floty dotyczy wyłącznie tej listy.
- Dane Equasis pobierano przy użyciu konta zarejestrowanego użytkownika. Masowe pobieranie może naruszać regulamin serwisu.
