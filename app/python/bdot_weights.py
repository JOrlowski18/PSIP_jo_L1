from bdot_names import NAMES

WEIGHTS = {
    "ADJA":  0.00,  # jednostki administracyjne
    "ADMS":  0.00,  # miejscowości

    "BUBD": -1.00,  # budynki
    "BUHD": -0.90,  # budowle hydrotechniczne
    "BUIB": -0.60,  # inne budowle
    "BIUB": -0.60,  # alias innych budowli
    "BUIN":  0.00,  # budowle inżynierskie
    "BUIT": -0.50,  # urządzenia techniczne
    "BUSP": -0.40,  # budowle sportowe
    "BUTR": -0.30,  # urządzenia transportowe
    "BUUO": -0.90,  # umocnienia
    "BUWT": -0.50,  # wysokie budowle techniczne
    "BUZM": -0.80,  # budowle ziemne
    "BUZT": -1.00,  # zbiorniki techniczne

    "KUHO": -0.30,  # kompleksy hotelarskie
    "KUHU": -0.40,  # bazary i targowiska
    "KUKO":  0.00,  # kompleksy komunikacyjne
    "KUMN": -0.40,  # kompleksy mieszkaniowe
    "KUOS": -0.30,  # kompleksy oświatowe
    "KUOZ": -0.30,  # kompleksy ochrony zdrowia
    "KUPG": -0.60,  # kompleksy przemysłowe
    "KUPW":  0.00,  # poligony wojskowe
    "KUSC": -0.70,  # kompleksy sakralne i cmentarze
    "KUSK": -0.20,  # kompleksy sportowe i rekreacyjne
    "KUZA": -0.40,  # kompleksy zabytkowe

    "OIKM":  0.00,  # obiekty komunikacyjne
    "OIMK": -0.95,  # mokradła
    "OIOR":  0.00,  # obiekty orientacyjne
    "OIPR": -0.30,  # obiekty przyrodnicze
    "OISZ": -0.85,  # szuwary

    "PTGN": -0.20,  # grunty nieużytkowane
    "PTKM":  0.00,  # tereny komunikacyjne
    "PTLZ": -0.80,  # tereny leśne i zadrzewione
    "PTNZ":  0.00,  # pozostałe tereny niezabudowane
    "PTPL":  0.60,  # place
    "PTRK": -0.65,  # roślinność krzewiasta
    "PTSO": -0.85,  # składowiska odpadów
    "PTTR":  0.20,  # trawy i uprawy rolne
    "PTUT": -0.45,  # uprawy trwałe
    "PTWP": -1.00,  # wody powierzchniowe
    "PTWZ": -0.90,  # wyrobiska i zwałowiska
    "PTZB": -0.60,  # zabudowa

    "SKDR":  0.90,  # drogi
    "SKJZ":  1.00,  # jezdnie
    "SKPP":  0.00,  # przeprawy
    "SKRP":  0.20,  # ciągi piesze i rowerowe
    "SKRW":  0.70,  # ronda i węzły
    "SKTR": -0.70,  # tory

    "SULN":  0.00,  # linie napowietrzne
    "SUPR":  0.00,  # przewody rurowe
    "SWKN": -0.95,  # kanały
    "SWRM": -0.60,  # rowy melioracyjne
    "SWRS": -0.90,  # rzeki i strumienie

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