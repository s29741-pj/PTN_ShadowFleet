"""
fetch_equasis.py – pobiera dane statków z Equasis po numerze IMO.

Loguje się przez POST, utrzymuje sesję i odpytuje strony szczegółów
statków. Skrypt jest wznawiany – pomija już pobrane IMO.

Użycie:
    python scripts/fetch_equasis.py --email twoj@email.com --password haslo
    python scripts/fetch_equasis.py --email twoj@email.com --password haslo \
        --input data/shadow_fleet_combined.csv \
        --output data/vessel_details_equasis.csv \
        --delay 5

WAŻNE: Equasis blokuje konta przy zbyt szybkim odpytywaniu.
Używaj --delay minimum 5 sekund. Skrypt sam robi dłuższe przerwy
co 50 statków (30 sekund) żeby zmniejszyć ryzyko blokady.

Wymagania:
    pip install pandas requests beautifulsoup4
"""

import argparse
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ── konfiguracja ──────────────────────────────────────────────────────────────

LOGIN_URL  = "https://www.equasis.org/EquasisWeb/public/HomePage"
SEARCH_URL = "https://www.equasis.org/EquasisWeb/restricted/ShipInfo"

DEFAULT_DELAY     = 5.0   # sekund między requestami
PAUSE_EVERY       = 50    # dłuższa przerwa co N statków
PAUSE_DURATION    = 30    # sekund dłuższej przerwy
TIMEOUT           = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.equasis.org/EquasisWeb/public/HomePage",
}

# stała struktura CSV
FIELDNAMES = [
    "imo", "vessel_name", "ship_type", "flag", "call_sign", "mmsi",
    "year_built", "gross_tonnage", "deadweight", "status",
    "registered_owner", "ship_manager", "ism_manager",
    "classification_society", "p_and_i_club",
    "inspections_total", "deficiencies_total", "detentions_total",
    "error",
]


# ── logowanie ─────────────────────────────────────────────────────────────────

def login(email: str, password: str) -> requests.Session | None:
    """
    Loguje się do Equasis przez POST i zwraca aktywną sesję.
    Zwraca None jeśli logowanie się nie powiodło.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    # pobierz stronę główną żeby zdobyć ciasteczka sesji
    try:
        resp = session.get(LOGIN_URL, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Błąd połączenia ze stroną główną: {e}")
        return None

    # dane logowania
    payload = {
        "j_email":    email,
        "j_password": password,
        "submit":     "Login",
    }

    try:
        resp = session.post(LOGIN_URL, data=payload, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Błąd podczas logowania: {e}")
        return None

    # sprawdź czy logowanie się udało
    if "j_email" in resp.text or "Lost password" in resp.text[:500]:
        # nadal jesteśmy na stronie logowania
        print("❌ Logowanie nie powiodło się. Sprawdź email i hasło.")
        return None

    if "ShipSearch" in resp.url or "restricted" in resp.url or "HomePage" in resp.url:
        print("✅ Zalogowano pomyślnie")
        return session

    # próba alternatywna – sprawdź treść
    if "My Equasis" in resp.text or "Ship Search" in resp.text:
        print("✅ Zalogowano pomyślnie")
        return session

    print("⚠️  Niepewny wynik logowania – kontynuuję")
    return session


# ── pobieranie szczegółów statku ──────────────────────────────────────────────

def fetch_vessel(imo: str, session: requests.Session) -> dict:
    """
    Pobiera dane statku z Equasis po numerze IMO.
    """
    empty = {f: None for f in FIELDNAMES}
    empty["imo"] = imo

    payload = {
        "fs":    "ShipInfo",
        "P_IMO": imo,
    }

    try:
        resp = session.post(SEARCH_URL, data=payload, timeout=TIMEOUT)

        if resp.status_code == 403:
            empty["error"] = "blocked_403"
            return empty
        if resp.status_code != 200:
            empty["error"] = f"http_{resp.status_code}"
            return empty

        # sprawdź czy sesja wygasła
        if "j_email" in resp.text or "please login" in resp.text.lower():
            empty["error"] = "session_expired"
            return empty

        return parse_equasis_page(resp.text, imo)

    except requests.exceptions.Timeout:
        empty["error"] = "timeout"
        return empty
    except requests.RequestException as e:
        empty["error"] = str(e)[:80]
        return empty


# ── parsowanie strony ─────────────────────────────────────────────────────────

def parse_equasis_page(html: str, imo: str) -> dict:
    """
    Parsuje stronę szczegółów statku z Equasis.
    """
    soup = BeautifulSoup(html, "html.parser")
    data = {f: None for f in FIELDNAMES}
    data["imo"] = imo

    # sprawdź czy statek został znaleziony
    if "No ship found" in html or "not found" in html.lower():
        data["error"] = "not_found"
        return data

    # nazwa statku – zwykle w h1 lub nagłówku sekcji
    for tag in soup.find_all(["h1", "h2", "h3"]):
        txt = tag.get_text(strip=True)
        if txt and len(txt) > 2 and not any(k in txt.lower() for k in
                                              ["equasis", "search", "home", "info"]):
            data["vessel_name"] = txt
            break

    # mapowanie etykiet → pola
    label_map = {
        "Ship type":               "ship_type",
        "Type of ship":            "ship_type",
        "Flag":                    "flag",
        "Call sign":               "call_sign",
        "Callsign":                "call_sign",
        "MMSI":                    "mmsi",
        "Year of build":           "year_built",
        "Year of Build":           "year_built",
        "Gross tonnage":           "gross_tonnage",
        "Gross Tonnage":           "gross_tonnage",
        "Deadweight":              "deadweight",
        "Deadweight (t)":          "deadweight",
        "Status":                  "status",
        "Registered owner":        "registered_owner",
        "Registered Owner":        "registered_owner",
        "Ship manager":            "ship_manager",
        "Ship Manager":            "ship_manager",
        "ISM Manager":             "ism_manager",
        "ISM manager":             "ism_manager",
        "Classification society":  "classification_society",
        "P&I":                     "p_and_i_club",
    }

    # przeszukaj wszystkie tabele
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).rstrip(":")
                value = cells[1].get_text(strip=True)
                if label in label_map and value and value != "-":
                    data[label_map[label]] = value

    # inspekcje PSC – szukaj liczb w sekcji inspections
    for tag in soup.find_all(string=lambda t: t and "inspection" in t.lower()):
        parent = tag.find_parent("tr")
        if parent:
            cells = parent.find_all("td")
            nums = [c.get_text(strip=True) for c in cells if c.get_text(strip=True).isdigit()]
            if len(nums) >= 1:
                data["inspections_total"] = nums[0]
            if len(nums) >= 2:
                data["deficiencies_total"] = nums[1]
            if len(nums) >= 3:
                data["detentions_total"] = nums[2]
            break

    return data


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pobierz dane statków z Equasis")
    parser.add_argument("--email",    required=True,  help="Email do Equasis")
    parser.add_argument("--password", required=True,  help="Hasło do Equasis")
    parser.add_argument("--input",    type=Path, default=Path("data/shadow_fleet_combined.csv"))
    parser.add_argument("--output",   type=Path, default=Path("data/vessel_details_equasis.csv"))
    parser.add_argument("--delay",    type=float, default=DEFAULT_DELAY,
                        help=f"Opóźnienie między requestami w sekundach (min. 5, domyślnie: {DEFAULT_DELAY})")
    args = parser.parse_args()

    if args.delay < 3:
        print("⚠️  Opóźnienie poniżej 3s – ryzyko blokady konta. Ustawiam 5s.")
        args.delay = 5.0

    # logowanie
    print(f"Logowanie jako {args.email} ...")
    session = login(args.email, args.password)
    if session is None:
        return

    # wczytaj listę IMO
    df = pd.read_csv(args.input, dtype={"mmsi": str, "imo": str})
    imo_list = [str(i).strip() for i in df["imo"].dropna().unique()
                if str(i).strip() not in ("", "nan")]
    print(f"Liczba statków: {len(imo_list)}")

    # wznowienie
    already_done = set()
    if args.output.exists() and args.output.stat().st_size > 0:
        existing = pd.read_csv(args.output, dtype=str)
        already_done = set(existing["imo"].dropna().tolist())
        print(f"Już pobrano: {len(already_done)} – pomijam")

    to_fetch = [i for i in imo_list if i not in already_done]
    print(f"Do pobrania: {len(to_fetch)} statków")
    print(f"Szacowany czas: {len(to_fetch) * (args.delay + PAUSE_DURATION / PAUSE_EVERY) / 60:.0f} minut\n")

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
                print(f"\n  ⏸️  Przerwa {PAUSE_DURATION}s (co {PAUSE_EVERY} statków)...")
                time.sleep(PAUSE_DURATION)

            result = fetch_vessel(imo, session)

            # przy wygaśnięciu sesji – zaloguj ponownie
            if result.get("error") == "session_expired":
                print("\n  🔄 Sesja wygasła – loguję ponownie...")
                session = login(args.email, args.password)
                if session is None:
                    print("❌ Nie udało się zalogować ponownie. Przerywam.")
                    break
                result = fetch_vessel(imo, session)

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


if __name__ == "__main__":
    main()