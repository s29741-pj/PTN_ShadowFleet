"""
fetch_equasis_selenium.py – pobiera dane statków z Equasis używając Selenium.

Selenium uruchamia prawdziwą przeglądarkę Chrome (w tle), loguje się
i pobiera dane statków po numerze IMO. Omija blokady JavaScript i cookies.

Użycie:
    # test jednego statku:
    python scripts/fetch_equasis_selenium.py --email EMAIL --password HASLO --test

    # pełne pobieranie:
    python scripts/fetch_equasis_selenium.py --email EMAIL --password HASLO

    # z niestandardowym opóźnieniem:
    python scripts/fetch_equasis_selenium.py --email EMAIL --password HASLO --delay 10

Wymagania:
    pip install selenium webdriver-manager beautifulsoup4 pandas
"""

import argparse
import time
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


# ── konfiguracja ──────────────────────────────────────────────────────────────

HOME_URL    = "https://www.equasis.org/EquasisWeb/public/HomePage"
SEARCH_URL  = "https://www.equasis.org/EquasisWeb/restricted/ShipInfo?fs=ShipInfo&P_IMO={imo}"
HISTORY_URL = "https://www.equasis.org/EquasisWeb/restricted/ShipHistory?fs=ShipInfo&P_IMO={imo}"

DEFAULT_DELAY  = 8.0
PAUSE_EVERY    = 50
PAUSE_DURATION = 30
TEST_IMO       = "9314088"  # LYRA

FIELDNAMES = [
    "imo", "vessel_name", "ship_type", "flag", "call_sign", "mmsi",
    "year_built", "gross_tonnage", "deadweight", "status",
    "registered_owner", "ship_manager", "ism_manager",
    "classification_society", "p_and_i_club",
    "inspections_total", "deficiencies_total", "detentions_total",
    # dane historyczne
    "former_names",       # poprzednie nazwy oddzielone " | "
    "former_flags",       # poprzednie bandery oddzielone " | "
    "flag_change_count",  # liczba zmian bandery
    "name_change_count",  # liczba zmian nazwy
    "former_owners",      # poprzedni właściciele
    "error",
]

LABEL_MAP = {
    "Ship type":              "ship_type",
    "Type of ship":           "ship_type",
    "Flag":                   "flag",
    "Call sign":              "call_sign",
    "Callsign":               "call_sign",
    "MMSI":                   "mmsi",
    "Year of build":          "year_built",
    "Year of Build":          "year_built",
    "Gross tonnage":          "gross_tonnage",
    "Gross Tonnage":          "gross_tonnage",
    "Deadweight":             "deadweight",
    "Deadweight (t)":         "deadweight",
    "Status":                 "status",
    "Registered owner":       "registered_owner",
    "Registered Owner":       "registered_owner",
    "Ship manager":           "ship_manager",
    "Ship Manager":           "ship_manager",
    "ISM Manager":            "ism_manager",
    "ISM manager":            "ism_manager",
    "Classification society": "classification_society",
    "P&I":                    "p_and_i_club",
}


# ── przeglądarka ──────────────────────────────────────────────────────────────

def create_driver() -> webdriver.Chrome:
    """Tworzy instancję Chrome w trybie headless (bez okna)."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ── logowanie ─────────────────────────────────────────────────────────────────

def login(driver: webdriver.Chrome, email: str, password: str) -> bool:
    """
    Loguje się do Equasis przez przeglądarkę.
    Zwraca True jeśli logowanie się powiodło.
    """
    print("Otwieranie strony Equasis ...")
    driver.get(HOME_URL)
    time.sleep(3)

    # Equasis ma kilka zestawów pól logowania w HTML (sidebar, mobile, main).
    # Używamy JavaScript żeby wypełnić wszystkie naraz i kliknąć widoczny przycisk.
    email_escaped    = email.replace("'", "\'")
    password_escaped = password.replace("'", "\'")

    try:
        driver.execute_script(f"""
            // wypełnij wszystkie pola email i hasła na stronie
            var emails = document.querySelectorAll('[name="j_email"]');
            var passes = document.querySelectorAll('[name="j_password"]');
            for (var i = 0; i < emails.length; i++) {{
                emails[i].value = '{email_escaped}';
            }}
            for (var i = 0; i < passes.length; i++) {{
                passes[i].value = '{password_escaped}';
            }}
        """)
        time.sleep(1)

        # kliknij pierwszy widoczny przycisk submit
        submitted = driver.execute_script("""
            var buttons = document.querySelectorAll('input[type="submit"], button[type="submit"]');
            for (var i = 0; i < buttons.length; i++) {
                var rect = buttons[i].getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    buttons[i].click();
                    return true;
                }
            }
            // fallback: wyślij formularz bezpośrednio
            var forms = document.querySelectorAll('form');
            for (var i = 0; i < forms.length; i++) {
                if (forms[i].querySelector('[name="j_email"]')) {
                    forms[i].submit();
                    return true;
                }
            }
            return false;
        """)

        if not submitted:
            print("❌ Nie znaleziono przycisku logowania.")
            return False

        time.sleep(4)

    except Exception as e:
        print(f"❌ Błąd podczas logowania: {e}")
        return False

    # sprawdź czy jesteśmy zalogowani
    page_text   = driver.page_source
    current_url = driver.current_url

    # nadal na stronie logowania = błędne dane
    if ('name="j_email"' in page_text
            and "incorrect" in page_text.lower()):
        print("❌ Błędny email lub hasło.")
        return False

    if ("restricted" in current_url
            or "My Equasis" in page_text
            or "Ship Search" in page_text
            or "ShipSubcription" in page_text):
        print("✅ Zalogowano pomyślnie")
        return True

    # Equasis czasem zostaje na HomePage po poprawnym logowaniu
    # sprawdź czy formularz logowania zniknął ze strony aktywnej sekcji
    if 'class="active"' in page_text and 'name="j_email"' in page_text:
        print("⚠️  Niepewny wynik – sprawdzam dostęp do statku testowego ...")
        return True  # sprawdzimy przy pierwszym fetchu

    print("✅ Zalogowano (kontynuuję)")
    return True


# ── pobieranie i parsowanie ───────────────────────────────────────────────────

def fetch_vessel(driver: webdriver.Chrome, imo: str) -> dict:
    """Pobiera i parsuje stronę szczegółów statku."""
    empty = {f: None for f in FIELDNAMES}
    empty["imo"] = imo

    try:
        driver.get(SEARCH_URL.format(imo=imo))
        time.sleep(3)

        current_url = driver.current_url
        page_src    = driver.page_source

        # zapisz HTML do pliku żeby przeanalizować strukturę
        debug_path = Path("debug_equasis.html")
        debug_path.write_text(page_src, encoding="utf-8")
        print(f"  [DEBUG] HTML zapisany do: {debug_path}")

        # sprawdź czy sesja wygasła
        if "j_email" in page_src and "j_password" in page_src:
            empty["error"] = "session_expired"
            return empty

        if "No ship found" in driver.page_source or "not found" in driver.page_source.lower():
            empty["error"] = "not_found"
            return empty

        data = parse_page(driver.page_source, imo)

        # pobierz też stronę historii
        try:
            driver.get(HISTORY_URL.format(imo=imo))
            time.sleep(2)
            if "j_email" not in driver.page_source:
                history = parse_history_page(driver.page_source)
                data.update(history)
        except Exception:
            pass  # historia opcjonalna – nie przerywaj przy błędzie

        return data

    except Exception as e:
        empty["error"] = str(e)[:80]
        return empty


def parse_history_page(html: str) -> dict:
    """Parsuje stronę historii statku z Equasis (ShipHistory)."""
    soup = BeautifulSoup(html, "html.parser")
    data = {}

    tables = soup.find_all("table", class_="tableLS")
    if not tables:
        return data

    # tabela 0 – historia nazw
    if len(tables) >= 1:
        names = []
        for row in tables[0].find_all("tr")[1:]:  # pomiń nagłówek
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if cells and cells[0]:
                names.append(f"{cells[0]} ({cells[1] if len(cells) > 1 else ''})")
        if names:
            data["former_names"]       = " | ".join(names)
            data["name_change_count"]  = str(len(names) - 1)  # pierwsza = aktualna

    # tabela 1 – historia bander
    if len(tables) >= 2:
        flags = []
        for row in tables[1].find_all("tr")[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if cells and cells[0]:
                flags.append(f"{cells[0]} ({cells[1] if len(cells) > 1 else ''})")
        if flags:
            data["former_flags"]       = " | ".join(flags)
            data["flag_change_count"]  = str(len(flags) - 1)

    # tabela 3 – historia właścicieli (registered owner)
    if len(tables) >= 4:
        owners = []
        for row in tables[3].find_all("tr")[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cells) >= 2 and cells[1] == "Registered owner" and cells[0]:
                owners.append(f"{cells[0]} ({cells[2] if len(cells) > 2 else ''})")
        if owners:
            data["former_owners"] = " | ".join(owners)

    return data


def parse_page(html: str, imo: str) -> dict:
    """Parsuje HTML strony statku z Equasis."""
    soup = BeautifulSoup(html, "html.parser")
    data = {f: None for f in FIELDNAMES}
    data["imo"] = imo

    # ── nazwa statku z h4 w sekcji Ship info ──────────────────────────────────
    for h4 in soup.find_all("h4"):
        h4_txt = h4.get_text(strip=True)
        if "IMO" in h4_txt:
            raw = h4_txt.replace(chr(160), " ").strip()
            name_raw = raw.split("-")[0].strip()
            if name_raw:
                data["vessel_name"] = name_raw
            break

    # ── dane statku z div.info-details ────────────────────────────────────────
    info = soup.find("div", class_="info-details")
    if info:
        txt = info.get_text(separator="|||", strip=True)
        lines = [l.strip() for l in txt.split("|||") if l.strip()]

        # iteruj po parach etykieta → wartość
        field_map = {
            "Flag":            "flag",
            "Call Sign":       "call_sign",
            "Gross tonnage":   "gross_tonnage",
            "DWT":             "deadweight",
            "Type of ship":    "ship_type",
            "Year of build":   "year_built",
            "Status":          "status",
        }
        i = 0
        while i < len(lines):
            line = lines[i]
            if line in field_map and i + 1 < len(lines):
                val = lines[i + 1]
                # pomiń "See picture" i etykiety następnej sekcji
                skip = {"See picture on VesselTracker", "See picture on MarineTraffic",
                        "Flag", "Call Sign", "Gross tonnage", "DWT",
                        "Type of ship", "Year of build", "Status"}
                if "See picture" not in val and val not in skip:
                    # jeśli wartość w nawiasie np "(Not Known)" – zachowaj ją
                    data[field_map[line]] = val
            i += 1

    # ── zarządzanie z tabeli tableLS ──────────────────────────────────────────
    mgmt_table = soup.find("table", class_="tableLS")
    if mgmt_table:
        role_map = {
            "Registered owner":              "registered_owner",
            "Ship manager/Commercial manager": "ship_manager",
            "Ship manager":                  "ship_manager",
            "ISM Manager":                   "ism_manager",
        }
        for row in mgmt_table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cells) >= 3:
                role    = cells[1]  # kolumna Role
                company = cells[2]  # kolumna Name of company
                if role in role_map and company:
                    data[role_map[role]] = company

    # ── klasyfikacja z tabeli classification ──────────────────────────────────
    tables = soup.find_all("table", class_="tableLS")
    if len(tables) >= 2:
        class_table = tables[1]
        rows = class_table.find_all("tr")
        if len(rows) >= 2:
            cells = rows[1].find_all("td")
            if cells:
                data["classification_society"] = cells[0].get_text(strip=True)
                if len(cells) >= 5:
                    data["status"] = data["status"] or cells[4].get_text(strip=True)

    # ── inspekcje PSC – liczba w nagłówku sekcji ─────────────────────────────
    for div in soup.find_all("div"):
        txt = div.get_text(strip=True)
        if txt.startswith("Inspections (") and ")" in txt:
            import re
            nums = re.findall(r"\d+", txt)
            if nums:
                data["inspections_total"] = nums[0]
            break

    # deficjencje i zatrzymania z tabeli inspekcji
    for tag in soup.find_all(string=lambda t: t and "deficien" in t.lower()):
        parent = tag.find_parent("tr")
        if parent:
            nums_in_row = [c.get_text(strip=True) for c in parent.find_all("td")
                           if c.get_text(strip=True).isdigit()]
            if len(nums_in_row) >= 1: data["deficiencies_total"] = nums_in_row[0]
            if len(nums_in_row) >= 2: data["detentions_total"]   = nums_in_row[1]
            break

    return data


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pobierz dane statków z Equasis (Selenium)")
    parser.add_argument("--email",    required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--input",    type=Path,  default=Path("data/shadow_fleet_combined.csv"))
    parser.add_argument("--output",   type=Path,  default=Path("data/vessel_details_equasis.csv"))
    parser.add_argument("--delay",    type=float, default=DEFAULT_DELAY)
    parser.add_argument("--test",     action="store_true",
                        help=f"Tryb testowy – pobiera tylko IMO {TEST_IMO}")
    parser.add_argument("--imo-list", type=str,   default=None,
                        help="Lista IMO oddzielona przecinkami, np. 9314088,9222649,9257993")
    parser.add_argument("--imo-file", type=Path,  default=None,
                        help="Plik tekstowy z IMO (jeden per linia lub po przecinku)")
    args = parser.parse_args()

    if args.delay < 5:
        print("⚠️  Delay poniżej 5s – ustawiam 8s dla bezpieczeństwa konta.")
        args.delay = 8.0

    # uruchom przeglądarkę
    print("Uruchamianie Chrome ...")
    driver = create_driver()

    try:
        # logowanie
        if not login(driver, args.email, args.password):
            return

        # tryb testowy
        if args.test:
            print(f"\nTryb testowy – IMO {TEST_IMO}\n")
            result = fetch_vessel(driver, TEST_IMO)
            print(f"{'='*50}")
            if result.get("error"):
                print(f"❌ Błąd: {result['error']}")
            else:
                filled = 0
                for field in FIELDNAMES:
                    val = result.get(field)
                    if val and str(val).strip() not in ("", "None", "nan"):
                        print(f"  {field:<30} {val}")
                        filled += 1
                print(f"\n{'='*50}")
                print(f"Wypełnione pola: {filled}/{len(FIELDNAMES)}")
                if filled > 3:
                    print("✅ Parsowanie działa – możesz uruchomić pełny skrypt.")
                else:
                    print("⚠️  Mało danych – Equasis mógł zmienić strukturę strony.")
            return

        # pełne pobieranie
        if getattr(args, 'imo_file', None) and args.imo_file:
            # wczytaj IMO z pliku tekstowego
            raw = args.imo_file.read_text(encoding="utf-8")
            imo_list = [i.strip() for i in raw.replace(",", "\n").splitlines()
                        if i.strip()]
            print(f"\nLiczba statków (z --imo-file): {len(imo_list)}")
        elif args.imo_list:
            # tryb z ręczną listą IMO
            imo_list = [i.strip() for i in args.imo_list.split(",")
                        if i.strip()]
            print(f"\nLiczba statków (z --imo-list): {len(imo_list)}")
        else:
            # wczytaj z pliku CSV
            df = pd.read_csv(args.input, dtype={"mmsi": str, "imo": str})
            imo_list = [str(i).strip() for i in df["imo"].dropna().unique()
                        if str(i).strip() not in ("", "nan")]
            print(f"\nLiczba statków: {len(imo_list)}")

        already_done = set()
        if args.output.exists() and args.output.stat().st_size > 0:
            existing = pd.read_csv(args.output, dtype=str)
            already_done = set(existing["imo"].dropna().tolist())
            print(f"Już pobrano: {len(already_done)} – pomijam")

        to_fetch = [i for i in imo_list if i not in already_done]
        est_min  = len(to_fetch) * (args.delay + PAUSE_DURATION / PAUSE_EVERY) / 60
        print(f"Do pobrania: {len(to_fetch)} statków")
        print(f"Szacowany czas: {est_min:.0f} minut\n")

        if not to_fetch:
            print("Nic do pobrania.")
            return

        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_header = not args.output.exists() or args.output.stat().st_size == 0
        errors = 0

        with open(args.output, "a", newline="", encoding="utf-8") as f:
            for i, imo in enumerate(to_fetch, 1):

                # dłuższa przerwa co PAUSE_EVERY statków
                if i > 1 and (i - 1) % PAUSE_EVERY == 0:
                    print(f"\n  ⏸️  Przerwa {PAUSE_DURATION}s ...")
                    time.sleep(PAUSE_DURATION)

                result = fetch_vessel(driver, imo)

                # ponowne logowanie przy wygaśnięciu sesji
                if result.get("error") == "session_expired":
                    print("\n  🔄 Sesja wygasła – loguję ponownie ...")
                    if not login(driver, args.email, args.password):
                        print("❌ Nie udało się zalogować ponownie. Przerywam.")
                        break
                    result = fetch_vessel(driver, imo)

                row_df = pd.DataFrame([result], columns=FIELDNAMES)
                row_df.to_csv(f, index=False, header=write_header)
                write_header = False
                f.flush()

                if result.get("error"):
                    errors += 1
                    status = "⚠️ "
                    info   = result["error"]
                else:
                    status = "✅"
                    info   = result.get("vessel_name", "?")

                if i % 10 == 0 or i <= 3:
                    print(f"  [{i}/{len(to_fetch)}] {status} IMO {imo}: {info}")
                else:
                    print(f"  [{i}/{len(to_fetch)}] {status} IMO {imo}: {info}", end="\r")

                time.sleep(args.delay)

        total = len(to_fetch)
        print(f"\n\n✅ Gotowe! Pobrano {total - errors}/{total} statków")
        print(f"   Błędy: {errors}")
        print(f"   Plik:  {args.output}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()