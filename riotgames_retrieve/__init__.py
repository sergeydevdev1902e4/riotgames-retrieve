"""CLI tool and library for bulk archiving Riot Games API match data."""

from riotgames_retrieve.client import RiotClient
from riotgames_retrieve.regions import Platform, RegionalRoute, get_regional_route

__version__ = "0.2.1"
__all__ = ["RiotClient", "Platform", "RegionalRoute", "get_regional_route", "__version__"]
