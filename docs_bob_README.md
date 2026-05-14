# Basel III RWA Calculator

Aplikacja backendu w Pythonie do kalkulacji Risk-Weighted Assets (RWA) zgodnie z reformami Basel III.

## Funkcjonalności

- ✅ Kalkulacja RWA dla różnych klas ekspozycji (Sovereign, Bank, Corporate, Retail, PSE, MDB, FI)
- ✅ Mapowanie ratingów NCCR do PD (Probability of Default)
- ✅ Implementacja standardowego podejścia do ryzyka kredytowego
- ✅ Obsługa wag ryzyka według ratingów zewnętrznych
- ✅ REST API (FastAPI)
- ✅ CLI dla przetwarzania wsadowego
- ✅ Walidacja danych wejściowych i wyjściowych (Pydantic)
- ✅ Szczegółowe ślady kalkulacji

## Struktura Projektu

```
basel3_final_reforms/
├── __init__.py           # Główny moduł pakietu
├── models.py             # Modele danych (Pydantic)
├── reference_data.py     # Dane referencyjne i wagi ryzyka
├── calculator.py         # Silnik kalkulacji RWA
├── engine.py             # Główny orkiestrator
├── api.py                # REST API (FastAPI)
└── cli.py                # Interfejs wiersza poleceń

test_rwa_calculator.py    # Skrypt testowy
requirements.txt          # Zależności
```

## Instalacja

```bash
# Zainstaluj zależności
pip install -r requirements.txt

# Lub zainstaluj ręcznie
pip install pydantic pandera fastapi uvicorn
```

## Użycie

### 1. CLI - Przetwarzanie Wsadowe

```bash
# Podstawowe użycie
python -m basel3_final_reforms.cli \
    --core-info preprod_core_info_1000.csv \
    --country-info preprod_country_info.csv \
    --output results.json \
    --format json \
    --verbose

# Z niestandardową ścieżką do mapowania NCCR
python -m basel3_final_reforms.cli \
    --core-info preprod_core_info_1000.csv \
    --country-info preprod_country_info.csv \
    --nccr-mapping custom_nccr_mapping.csv \
    --output results.csv \
    --format csv
```

### 2. REST API

```bash
# Uruchom serwer API
python -m basel3_final_reforms.api

# Lub z uvicorn
uvicorn basel3_final_reforms.api:app --reload --host 0.0.0.0 --port 8000
```

API będzie dostępne pod adresem: `http://localhost:8000`

#### Endpointy API:

- `GET /` - Informacje o API
- `GET /health` - Health check
- `GET /api/v1/reference-data` - Informacje o danych referencyjnych
- `POST /api/v1/calculate` - Kalkulacja RWA
- `POST /api/v1/calculate-with-trace` - Kalkulacja z szczegółowymi śladami

#### Przykład użycia API:

```python
import requests

# Przygotuj dane
request_data = {
    "core_info": [
        {
            "id": "EXP000001",
            "counterparty_gid": "CP00001",
            "entity_class": "CORP",
            "exposure_amount": "1000000",
            # ... inne pola
        }
    ],
    "country_info": [
        {
            "incorporation_country": "PL",
            "local_currency": "PLN",
            # ... inne pola
        }
    ]
}

# Wywołaj API
response = requests.post(
    "http://localhost:8000/api/v1/calculate",
    json=request_data
)

results = response.json()
print(f"Total RWA: {results['summary']['output_successful_records']}")
```

### 3. Użycie Programistyczne

```python
from basel3_final_reforms import RwaEngine
from rwa_pydantic_schemas import CoreInfoRecord, CountryInfoRecord

# Inicjalizuj silnik
engine = RwaEngine(nccr_mapping_path="nccr_mapping.csv")

# Przygotuj dane
core_info = [
    CoreInfoRecord(
        id="EXP001",
        counterparty_gid="CP001",
        entity_class="CORP",
        exposure_amount="1000000.00",
        # ... inne pola
    )
]

country_info = [
    CountryInfoRecord(
        incorporation_country="PL",
        local_currency="PLN",
        # ... inne pola
    )
]

# Wykonaj kalkulację
results = engine.calculate_with_trace(core_info, country_info)

# Wyświetl wyniki
print(f"Total RWA Basel 3.0: {results['summary']['total_rwa_basel_3_0']}")
print(f"Total RWA Basel 3.1: {results['summary']['total_rwa_basel_3_1']}")
```

### 4. Test z Danymi Preprod

```bash
# Uruchom test z dostarczonymi danymi
python test_rwa_calculator.py
```

## Dane Wejściowe

### Core Info (preprod_core_info_1000.csv)
Zawiera informacje o ekspozycjach:
- ID ekspozycji
- Klasa podmiotu (SOV, BANK, CORP, RETAIL, PSE, MDB, FI, OTHER)
- Ratinigi wewnętrzne i zewnętrzne
- Kwota ekspozycji
- Terminy zapadalności
- DLGD (Downturn Loss Given Default)
- Flagi (gwarancje rządowe, AVC, itp.)

### Country Info (preprod_country_info.csv)
Zawiera informacje o krajach:
- Kod kraju
- Waluta lokalna
- Ratinigi kraju
- Flagi EEA
- DLGD kraju

### NCCR Mapping (nccr_mapping.csv)
Mapowanie ratingów NCCR do PD dla różnych klas podmiotów (SOV, CORP, BANK).

## Dane Wyjściowe

Aplikacja generuje następujące wyniki:

### Dla każdej ekspozycji:
- `basel_3_0_rw_final` - Waga ryzyka Basel 3.0
- `basel_3_0_rwa` - RWA Basel 3.0
- `basel_3_1_rw_final` - Waga ryzyka Basel 3.1
- `basel_3_1_rwa_final` - RWA Basel 3.1
- `basel_3_0_pd` - Prawdopodobieństwo niewypłacalności
- `basel_3_0_dlgd` - Downturn LGD
- Szczegółowe ślady kalkulacji (w trybie verbose)

### Podsumowanie portfela:
- Całkowita liczba ekspozycji
- Liczba udanych kalkulacji
- Liczba błędów
- Suma RWA dla Basel 3.0 i 3.1

## Implementowane Wagi Ryzyka

### Sovereign (Suwerenne)
- AAA do AA-: 0%
- A+ do A-: 20%
- BBB+ do BBB-: 50%
- BB+ do B-: 100%
- Poniżej B-: 150%
- Bez ratingu: 100%

### Bank (ECRA)
- AAA do AA-: 20%
- A+ do A-: 30% (20% krótkoterminowe)
- BBB+ do BBB-: 50% (20% krótkoterminowe)
- BB+ do B-: 100% (50% krótkoterminowe)
- Poniżej B-: 150%

### Corporate (Korporacyjne)
- AAA do AA-: 20%
- A+ do A-: 50%
- BBB+ do BB-: 100%
- B+ do B-: 100%
- Poniżej B-: 150%
- Bez ratingu: 100%

### Retail (Detaliczne)
- Standardowa waga: 75%

### PSE (Public Sector Entities)
- Opcja 1: Oparta na ratingu suwerena
- Opcja 2: Oparta na ratingu PSE

### MDB (Multilateral Development Banks)
- Kwalifikowane: 0%
- Inne z ratingiem: 20-150% (zależnie od ratingu)
- Bez ratingu: 50%

## Architektura

### Moduły:

1. **reference_data.py** - Zarządza danymi referencyjnymi:
   - Ładowanie mapowania NCCR
   - Wagi ryzyka dla różnych klas ekspozycji
   - Logika wyboru wag

2. **calculator.py** - Silnik kalkulacji:
   - Klasyfikacja ekspozycji
   - Obliczanie wag ryzyka
   - Kalkulacja RWA
   - Generowanie śladów

3. **engine.py** - Orkiestrator:
   - Koordynacja procesu kalkulacji
   - Agregacja wyników
   - Obsługa błędów

4. **api.py** - REST API:
   - Endpointy FastAPI
   - Walidacja requestów
   - Serializacja odpowiedzi

5. **cli.py** - Interfejs CLI:
   - Ładowanie CSV
   - Przetwarzanie wsadowe
   - Eksport wyników

## Ograniczenia i Uproszczenia

Obecna implementacja zawiera następujące uproszczenia:

1. **Credit Risk Mitigation (CRM)** - Nie w pełni zaimplementowane
2. **IRB Approach** - Nie zaimplementowane (tylko standardowe podejście)
3. **CVA Risk** - Nie zaimplementowane
4. **Operational Risk** - Nie zaimplementowane
5. **Output Floor** - Nie zaimplementowane
6. **Leverage Ratio** - Nie zaimplementowane
7. **Off-Balance Sheet Items** - Uproszczone
8. **Securitisation** - Nie zaimplementowane

## Rozwój

Aby rozszerzyć aplikację:

1. Dodaj nowe moduły w katalogu `basel3_final_reforms/`
2. Rozszerz `calculator.py` o dodatkowe metody kalkulacji
3. Zaktualizuj `reference_data.py` o nowe parametry regulacyjne
4. Dodaj nowe endpointy w `api.py`
5. Rozszerz CLI w `cli.py` o nowe opcje

## Testowanie

```bash
# Uruchom test z danymi preprod
python test_rwa_calculator.py

# Uruchom testy jednostkowe (jeśli dostępne)
pytest tests/

# Sprawdź pokrycie kodu
pytest --cov=basel3_final_reforms tests/
```

## Licencja

Projekt stworzony dla celów edukacyjnych i demonstracyjnych.

## Kontakt

Dla pytań i wsparcia, skontaktuj się z zespołem rozwoju.