from bdot_names import NAMES

# Wagi eksperymentalne dla oceny przejezdności.
# -1 = największe utrudnienie, 0 = neutralnie, +1 = największe ułatwienie.

WEIGHTS = {
    # Jednostki administracyjne i miejscowości
    "ADJA":  0.00,  # jednostki administracyjne
    "ADMS":  0.00,  # miejscowości

    # Budynki, budowle i urządzenia
    "BUBD": -1.00,  # budynki
    "BUHD": -0.95,  # budowle hydrotechniczne
    "BUIB": -0.80,  # inne budowle
    "BIUB": -0.80,  # alias innych budowli
    "BUIN":  0.30,  # budowle inżynierskie
    "BUIT": -0.70,  # urządzenia techniczne
    "BUSP": -0.60,  # budowle sportowe
    "BUTR": -0.60,  # urządzenia transportowe
    "BUUO": -1.00,  # umocnienia
    "BUWT": -0.70,  # wysokie budowle techniczne
    "BUZM": -0.95,  # budowle ziemne
    "BUZT": -1.00,  # zbiorniki techniczne

    # Kompleksy użytkowania terenu
    "KUHO": -0.60,  # kompleksy hotelarskie
    "KUHU": -0.70,  # bazary i targowiska
    "KUKO":  0.25,  # kompleksy komunikacyjne
    "KUMN": -0.75,  # kompleksy mieszkaniowe
    "KUOS": -0.60,  # kompleksy oświatowe
    "KUOZ": -0.60,  # kompleksy ochrony zdrowia
    "KUPG": -0.90,  # kompleksy przemysłowe
    "KUPW":  0.00,  # poligony wojskowe
    "KUSC": -0.90,  # kompleksy sakralne i cmentarze
    "KUSK": -0.50,  # kompleksy sportowe i rekreacyjne
    "KUZA": -0.70,  # kompleksy zabytkowe

    # Inne obiekty
    "OIKM":  0.15,  # obiekty komunikacyjne
    "OIMK": -1.00,  # mokradła
    "OIOR":  0.00,  # obiekty orientacyjne
    "OIPR": -0.60,  # obiekty przyrodnicze
    "OISZ": -0.95,  # szuwary

    # Pokrycie terenu
    "PTGN":  0.70,  # grunty nieużytkowane
    "PTKM":  0.40,  # tereny komunikacyjne
    "PTLZ": -0.95,  # tereny leśne i zadrzewione
    "PTNZ":  0.50,  # pozostałe tereny niezabudowane
    "PTPL":  0.90,  # place
    "PTRK": -0.85,  # roślinność krzewiasta
    "PTSO": -1.00,  # składowiska odpadów
    "PTTR":  0.70,  # trawy i uprawy rolne
    "PTUT":  0.20,  # uprawy trwałe
    "PTWP": -1.00,  # wody powierzchniowe
    "PTWZ": -1.00,  # wyrobiska i zwałowiska
    "PTZB": -0.90,  # zabudowa

    # Sieć komunikacyjna
    "SKDR":  1.00,  # drogi
    "SKJZ":  1.00,  # jezdnie
    "SKPP":  0.40,  # przeprawy
    "SKRP":  0.60,  # ciągi piesze i rowerowe
    "SKRW":  0.90,  # ronda i węzły
    "SKTR":  0.40,  # tory

    # Sieć uzbrojenia terenu
    "SULN":  0.00,  # linie napowietrzne
    "SUPR":  0.00,  # przewody rurowe

    # Sieć wodna
    "SWKN": -0.60,  # kanały
    "SWRM": -0.85,  # rowy melioracyjne
    "SWRS": -0.60,  # rzeki i strumienie

    # Tereny chronione
    "TCON":  0.00,  # Natura 2000
    "TCPN":  0.00,  # parki narodowe
    "TCPK":  0.00,  # parki krajobrazowe
    "TCRZ":  0.00,  # rezerwaty
}

missing = set(NAMES) - set(WEIGHTS)
if missing:
    raise ValueError(f"Brak wag dla klas: {sorted(missing)}")

if any(not -1 <= value <= 1 for value in WEIGHTS.values()):
    raise ValueError("Wagi muszą należeć do przedziału [-1, 1].")