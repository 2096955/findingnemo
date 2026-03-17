"""Whale Agent constants — API URLs, port mappings, domain routing."""

# MCP server ports
MCP_PORTS = {
    "noaa": 9001,
    "whale_alert": 9002,
    "marine_cadastre": 9003,
    "open_meteo": 9004,
    "gbif": 9005,
    "iucn": 9006,
}

# API base URLs
NOAA_WEATHER_BASE_URL = "https://api.weather.gov"
NOAA_NDBC_BASE_URL = "https://www.ndbc.noaa.gov/data/realtime2"
WHALE_ALERT_BASE_URL = "https://www.whalealert.org/api/v1"
MARINE_CADASTRE_BASE_URL = "https://marinecadastre.gov/ais"
OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
GBIF_API_BASE_URL = "https://api.gbif.org/v1"
IUCN_API_BASE_URL = "https://apiv3.iucnredlist.org/api/v3"

CETACEA_TAXON_KEY = 733

WHALE_SPECIES = {
    "blue_whale": {"scientific": "Balaenoptera musculus", "iucn": "EN"},
    "humpback_whale": {"scientific": "Megaptera novaeangliae", "iucn": "LC"},
    "north_atlantic_right_whale": {"scientific": "Eubalaena glacialis", "iucn": "CR"},
    "fin_whale": {"scientific": "Balaenoptera physalus", "iucn": "VU"},
    "gray_whale": {"scientific": "Eschrichtius robustus", "iucn": "LC"},
    "sperm_whale": {"scientific": "Physeter macrocephalus", "iucn": "VU"},
    "bowhead_whale": {"scientific": "Balaena mysticetus", "iucn": "LC"},
    "sei_whale": {"scientific": "Balaenoptera borealis", "iucn": "EN"},
    "minke_whale": {"scientific": "Balaenoptera acutorostrata", "iucn": "LC"},
}

DOMAIN_AGENT_ROUTING = {
    "route_optimization": {
        "agent": "RouteOptimizer",
        "keywords": ["route", "path", "navigate", "waypoint", "shipping lane", "port", "voyage", "course", "detour", "diversion", "shortest", "safest", "optimal", "efficient"],
    },
    "risk_assessment": {
        "agent": "RiskAssessor",
        "keywords": ["risk", "collision", "strike", "probability", "danger", "hazard", "threat", "impact", "likelihood", "score"],
    },
    "weather": {
        "agent": "WeatherAnalyst",
        "keywords": ["weather", "storm", "wind", "wave", "current", "temperature", "forecast", "sea state", "swell", "visibility", "fog", "climate", "ocean", "marine weather"],
    },
    "vessel_traffic": {
        "agent": "VesselTrafficMonitor",
        "keywords": ["vessel", "ship", "traffic", "ais", "tanker", "cargo", "container", "fleet", "density", "lane", "shipping", "maritime", "port", "harbor"],
    },
    "whale_migration": {
        "agent": "WhaleMigrationTracker",
        "keywords": ["migration", "migration pattern", "seasonal", "breeding", "calving", "feeding ground", "migratory", "range", "movement", "corridor", "pathway"],
    },
    "habitat": {
        "agent": "HabitatAnalyst",
        "keywords": ["habitat", "krill", "plankton", "feeding", "prey", "ecosystem", "environment", "upwelling", "nutrient", "biodiversity", "marine habitat"],
    },
    "species": {
        "agent": "SpeciesIdentifier",
        "keywords": ["species", "whale", "cetacean", "baleen", "toothed", "endangered", "conservation", "population", "iucn", "protected", "threatened", "vulnerable"],
    },
    "incidents": {
        "agent": "IncidentAnalyst",
        "keywords": ["incident", "strike", "collision", "historical", "accident", "record", "database", "trend", "fatality", "injury", "mortality", "report"],
    },
}
