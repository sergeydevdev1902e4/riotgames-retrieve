from enum import Enum
from typing import Dict


class RegionalRoute(str, Enum):
    AMERICAS = "americas"
    ASIA = "asia"
    EUROPE = "europe"
    SEA = "sea"
    ESPORTS = "esports"


class Platform(str, Enum):
    BR1 = "br1"
    EUN1 = "eun1"
    EUW1 = "euw1"
    JP1 = "jp1"
    KR = "kr"
    LA1 = "la1"
    LA2 = "la2"
    NA1 = "na1"
    OC1 = "oc1"
    TR1 = "tr1"
    RU = "ru"
    PH2 = "ph2"
    SG2 = "sg2"
    TH2 = "th2"
    TW2 = "tw2"
    VN2 = "vn2"


# Match-v5 and account-v1 use regional routes, while summoner-v4/league-v4 use platform hosts
PLATFORM_TO_REGION: Dict[Platform, RegionalRoute] = {
    Platform.BR1: RegionalRoute.AMERICAS,
    Platform.EUN1: RegionalRoute.EUROPE,
    Platform.EUW1: RegionalRoute.EUROPE,
    Platform.JP1: RegionalRoute.ASIA,
    Platform.KR: RegionalRoute.ASIA,
    Platform.LA1: RegionalRoute.AMERICAS,
    Platform.LA2: RegionalRoute.AMERICAS,
    Platform.NA1: RegionalRoute.AMERICAS,
    Platform.OC1: RegionalRoute.SEA,
    Platform.TR1: RegionalRoute.EUROPE,
    Platform.RU: RegionalRoute.EUROPE,
    # Post-Garena SEA platforms
    Platform.PH2: RegionalRoute.SEA,
    Platform.SG2: RegionalRoute.SEA,
    Platform.TH2: RegionalRoute.SEA,
    Platform.TW2: RegionalRoute.SEA,
    Platform.VN2: RegionalRoute.SEA,
}


def get_regional_route(value: str) -> RegionalRoute:
    clean = value.strip().lower()
    # Allow passing 'americas', 'europe', etc. directly
    for reg in RegionalRoute:
        if reg.value == clean:
            return reg
    try:
        plat = Platform(clean)
        return PLATFORM_TO_REGION[plat]
    except ValueError:
        valid_plats = ", ".join(p.value for p in Platform)
        valid_regs = ", ".join(r.value for r in RegionalRoute)
        raise ValueError(f"Unknown platform or region '{value}'. Expected one of: {valid_plats}, {valid_regs}")


def platform_host(platform: Platform) -> str:
    return f"{platform.value}.api.riotgames.com"


def regional_host(region: RegionalRoute) -> str:
    return f"{region.value}.api.riotgames.com"
