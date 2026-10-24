"""The fictional business DuckShop 10K describes: Mallard & Co. after a decade of growth.

Everything here is invented. Instance codes are built from country codes, city names, product
categories and generic channel words, so no code names a real company, brand or product.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    code: str
    name: str
    timezone: str


@dataclass(frozen=True)
class Storefront:
    country: str
    region: str
    timezone: str
    currency: str
    platform: str

    @property
    def code(self) -> str:
        return f"shop_{self.country.lower()}"


@dataclass(frozen=True)
class Instance:
    """One deployment of a source system: a marketplace, a warehouse, a carrier and so on."""

    system: str
    code: str
    region: str
    timezone: str
    currency: str
    platform: str
    label: str


REGIONS: tuple[Region, ...] = (
    Region("eu_west", "Western Europe", "Europe/Berlin"),
    Region("eu_south", "Southern Europe", "Europe/Madrid"),
    Region("eu_north", "Northern Europe", "Europe/Stockholm"),
    Region("eu_east", "Central and Eastern Europe", "Europe/Warsaw"),
    Region("uk_ie", "United Kingdom and Ireland", "Europe/London"),
    Region("north_america", "North America", "America/New_York"),
    Region("latam", "Latin America", "America/Sao_Paulo"),
    Region("asia", "Asia", "Asia/Tokyo"),
    Region("oceania", "Oceania", "Australia/Sydney"),
    Region("mea", "Middle East and Africa", "Asia/Dubai"),
)
REGION_BY_CODE: dict[str, Region] = {region.code: region for region in REGIONS}

CURRENCY_EXPONENT: dict[str, int] = {
    "AED": 2,
    "AUD": 2,
    "BHD": 3,
    "BRL": 2,
    "CAD": 2,
    "CHF": 2,
    "CLP": 0,
    "COP": 2,
    "CZK": 2,
    "DKK": 2,
    "EUR": 2,
    "GBP": 2,
    "HUF": 2,
    "INR": 2,
    "JPY": 0,
    "KRW": 0,
    "KWD": 3,
    "MXN": 2,
    "NOK": 2,
    "NZD": 2,
    "PLN": 2,
    "QAR": 2,
    "SAR": 2,
    "SEK": 2,
    "SGD": 2,
    "THB": 2,
    "TWD": 2,
    "USD": 2,
    "ZAR": 2,
}

# Platform generations of the storefront software. `classic` is the original monolith with
# legacy column names, local timestamps and JSON kept as text; `nest` is the columnar rewrite;
# `flock` is the document store that newer storefronts launched on.
PLATFORMS: tuple[str, ...] = ("classic", "nest", "flock")

_STOREFRONT_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    ("DE", "eu_west", "Europe/Berlin", "EUR", "classic"),
    ("FR", "eu_west", "Europe/Paris", "EUR", "classic"),
    ("NL", "eu_west", "Europe/Amsterdam", "EUR", "classic"),
    ("AT", "eu_west", "Europe/Vienna", "EUR", "nest"),
    ("CH", "eu_west", "Europe/Zurich", "CHF", "nest"),
    ("BE", "eu_west", "Europe/Brussels", "EUR", "nest"),
    ("LU", "eu_west", "Europe/Luxembourg", "EUR", "flock"),
    ("ES", "eu_south", "Europe/Madrid", "EUR", "nest"),
    ("PT", "eu_south", "Europe/Lisbon", "EUR", "nest"),
    ("IT", "eu_south", "Europe/Rome", "EUR", "nest"),
    ("GR", "eu_south", "Europe/Athens", "EUR", "flock"),
    ("SE", "eu_north", "Europe/Stockholm", "SEK", "nest"),
    ("NO", "eu_north", "Europe/Oslo", "NOK", "nest"),
    ("DK", "eu_north", "Europe/Copenhagen", "DKK", "nest"),
    ("FI", "eu_north", "Europe/Helsinki", "EUR", "flock"),
    ("PL", "eu_east", "Europe/Warsaw", "PLN", "nest"),
    ("CZ", "eu_east", "Europe/Prague", "CZK", "flock"),
    ("HU", "eu_east", "Europe/Budapest", "HUF", "flock"),
    ("GB", "uk_ie", "Europe/London", "GBP", "classic"),
    ("IE", "uk_ie", "Europe/Dublin", "EUR", "nest"),
    ("US", "north_america", "America/New_York", "USD", "classic"),
    ("CA", "north_america", "America/Toronto", "CAD", "nest"),
    ("MX", "north_america", "America/Mexico_City", "MXN", "flock"),
    ("BR", "latam", "America/Sao_Paulo", "BRL", "flock"),
    ("CL", "latam", "America/Santiago", "CLP", "flock"),
    ("CO", "latam", "America/Bogota", "COP", "flock"),
    ("JP", "asia", "Asia/Tokyo", "JPY", "classic"),
    ("KR", "asia", "Asia/Seoul", "KRW", "nest"),
    ("SG", "asia", "Asia/Singapore", "SGD", "nest"),
    ("IN", "asia", "Asia/Kolkata", "INR", "flock"),
    ("TW", "asia", "Asia/Taipei", "TWD", "flock"),
    ("TH", "asia", "Asia/Bangkok", "THB", "flock"),
    ("AU", "oceania", "Australia/Sydney", "AUD", "classic"),
    ("NZ", "oceania", "Pacific/Auckland", "NZD", "nest"),
    ("AE", "mea", "Asia/Dubai", "AED", "nest"),
    ("SA", "mea", "Asia/Riyadh", "SAR", "flock"),
    ("KW", "mea", "Asia/Kuwait", "KWD", "classic"),
    ("BH", "mea", "Asia/Bahrain", "BHD", "flock"),
    ("QA", "mea", "Asia/Qatar", "QAR", "flock"),
    ("ZA", "mea", "Africa/Johannesburg", "ZAR", "flock"),
)

STOREFRONTS: tuple[Storefront, ...] = tuple(Storefront(*row) for row in _STOREFRONT_ROWS)

# Duck species name the product lines, as in the base DuckShop project.
PRODUCT_LINES: tuple[str, ...] = (
    "mallard",
    "pintail",
    "teal",
    "eider",
    "merganser",
    "wigeon",
    "shoveler",
    "gadwall",
    "garganey",
    "goldeneye",
    "scaup",
    "pochard",
)

TEAMS: tuple[str, ...] = ("finance", "marketing", "operations", "support", "merchandising")


def _storefront_for(country: str) -> Storefront:
    return next(storefront for storefront in STOREFRONTS if storefront.country == country)


def _instance(system: str, code: str, country: str, platform: str, label: str) -> Instance:
    storefront = _storefront_for(country)
    return Instance(
        system=system,
        code=code,
        region=storefront.region,
        timezone=storefront.timezone,
        currency=storefront.currency,
        platform=platform,
        label=label,
    )


def _cycle(values: tuple[str, ...], index: int) -> str:
    return values[index % len(values)]


_MARKETPLACE_CATEGORIES: tuple[str, ...] = ("bazaar", "crafts", "home", "gifts", "toys", "garden")
_MARKETPLACE_COUNTRIES: tuple[str, ...] = ("DE", "GB", "US", "JP", "FR", "BR", "AU", "AE")

_WAREHOUSE_SITES: tuple[tuple[str, str, str], ...] = (
    ("pond", "leipzig", "DE"),
    ("nest", "columbus", "US"),
    ("marsh", "osaka", "JP"),
    ("reed", "venlo", "NL"),
    ("brook", "lyon", "FR"),
    ("delta", "zaragoza", "ES"),
    ("lagoon", "verona", "IT"),
    ("fen", "goteborg", "SE"),
    ("mere", "poznan", "PL"),
    ("tarn", "coventry", "GB"),
    ("creek", "reno", "US"),
    ("bayou", "dallas", "US"),
    ("estuary", "toronto", "CA"),
    ("shoal", "monterrey", "MX"),
    ("spring", "campinas", "BR"),
    ("rill", "santiago", "CL"),
    ("weir", "incheon", "KR"),
    ("cove", "jurong", "SG"),
    ("beck", "pune", "IN"),
    ("loch", "dublin", "IE"),
    ("haven", "melbourne", "AU"),
    ("sound", "auckland", "NZ"),
    ("oasis", "jebel_ali", "AE"),
    ("wadi", "dammam", "SA"),
    ("vlei", "midrand", "ZA"),
    ("kanal", "brno", "CZ"),
)

_STORE_CITIES: tuple[tuple[str, str], ...] = (
    ("berlin", "DE"),
    ("hamburg", "DE"),
    ("munich", "DE"),
    ("cologne", "DE"),
    ("paris", "FR"),
    ("bordeaux", "FR"),
    ("amsterdam", "NL"),
    ("vienna", "AT"),
    ("zurich", "CH"),
    ("madrid", "ES"),
    ("barcelona", "ES"),
    ("lisbon", "PT"),
    ("milan", "IT"),
    ("rome", "IT"),
    ("stockholm", "SE"),
    ("oslo", "NO"),
    ("copenhagen", "DK"),
    ("warsaw", "PL"),
    ("london", "GB"),
    ("manchester", "GB"),
    ("edinburgh", "GB"),
    ("bristol", "GB"),
    ("dublin", "IE"),
    ("new_york", "US"),
    ("boston", "US"),
    ("chicago", "US"),
    ("seattle", "US"),
    ("austin", "US"),
    ("toronto", "CA"),
    ("vancouver", "CA"),
    ("tokyo", "JP"),
    ("kyoto", "JP"),
    ("seoul", "KR"),
    ("singapore", "SG"),
    ("sydney", "AU"),
    ("melbourne", "AU"),
    ("auckland", "NZ"),
    ("dubai", "AE"),
    ("sao_paulo", "BR"),
    ("cape_town", "ZA"),
)

_SUPPLIER_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("rubber", "TH"),
    ("textile", "PT"),
    ("decoy", "CZ"),
    ("garden", "NL"),
    ("bath", "IT"),
    ("ceramics", "ES"),
    ("packaging", "PL"),
    ("print", "DE"),
)

_GATEWAYS: tuple[tuple[str, str], ...] = (
    ("pay_card_eu", "DE"),
    ("pay_card_us", "US"),
    ("pay_card_apac", "SG"),
    ("pay_wallet", "GB"),
    ("pay_instalments", "SE"),
    ("pay_bank_transfer", "NL"),
)

_AD_NETWORKS: tuple[tuple[str, str], ...] = (
    ("ads_search_global", "US"),
    ("ads_search_asia", "JP"),
    ("ads_social_global", "US"),
    ("ads_social_latam", "BR"),
    ("ads_video_global", "US"),
    ("ads_display_global", "GB"),
    ("ads_display_eu", "DE"),
    ("ads_shopping_global", "US"),
    ("ads_retail_media_us", "US"),
    ("ads_retail_media_eu", "FR"),
    ("ads_podcast_global", "GB"),
    ("ads_outdoor_eu", "NL"),
    ("ads_creator_global", "US"),
    ("ads_price_comparison_eu", "DE"),
)

_MESSAGING: tuple[tuple[str, str], ...] = (
    ("msg_email_lifecycle", "GB"),
    ("msg_email_bulk", "DE"),
    ("msg_sms", "US"),
    ("msg_push", "SG"),
)

_SUPPORT_TOOLS: tuple[tuple[str, str], ...] = (
    ("support_desk", "GB"),
    ("support_chat", "DE"),
    ("support_voice", "US"),
)

_LEGAL_ENTITY_COUNTRIES: tuple[str, ...] = (
    "GB",
    "DE",
    "FR",
    "NL",
    "ES",
    "IT",
    "SE",
    "PL",
    "US",
    "CA",
    "JP",
    "AU",
    "AE",
    "BR",
)

_COLLECTORS: tuple[str, ...] = tuple(f"web_{region.code}" for region in REGIONS) + (
    "app_phone",
    "app_tablet",
)
_COLLECTOR_HOME: dict[str, str] = {
    "web_eu_west": "DE",
    "web_eu_south": "ES",
    "web_eu_north": "SE",
    "web_eu_east": "PL",
    "web_uk_ie": "GB",
    "web_north_america": "US",
    "web_latam": "BR",
    "web_asia": "JP",
    "web_oceania": "AU",
    "web_mea": "AE",
    "app_phone": "GB",
    "app_tablet": "GB",
}


def _region_home(region: str) -> str:
    return next(storefront.country for storefront in STOREFRONTS if storefront.region == region)


def instances() -> dict[str, tuple[Instance, ...]]:
    """Every deployed source system, grouped by system kind, in a fixed order."""
    marketplaces = tuple(
        _instance(
            "marketplace",
            f"mkt_{_cycle(_MARKETPLACE_CATEGORIES, index)}_{country.lower()}",
            country,
            _cycle(("nest", "flock"), index),
            f"{_cycle(_MARKETPLACE_CATEGORIES, index)} marketplace partner in {country}",
        )
        for index, country in enumerate(
            _MARKETPLACE_COUNTRIES + _MARKETPLACE_COUNTRIES[:4] + ("IT", "ES", "MX", "KR")
        )
    )
    # Make marketplace codes unique when a category repeats in one country.
    seen: dict[str, int] = {}
    unique_marketplaces: list[Instance] = []
    for marketplace in marketplaces:
        count = seen.get(marketplace.code, 0)
        seen[marketplace.code] = count + 1
        if count:
            marketplace = Instance(
                **{**marketplace.__dict__, "code": f"{marketplace.code}_{count}"}
            )
        unique_marketplaces.append(marketplace)
    carriers = (
        _instance("carrier", "carrier_flapwing", "GB", "nest", "Flapwing Parcels"),
        _instance("carrier", "carrier_wingbeat", "DE", "nest", "Wingbeat Couriers"),
        _instance("carrier", "carrier_webfoot", "US", "classic", "Webfoot Freight"),
        *(
            _instance("carrier", f"carrier_postal_{country.lower()}", country, "classic", "post")
            for country in ("GB", "DE", "FR", "US", "JP", "AU", "BR", "AE")
        ),
        *(
            _instance(
                "carrier",
                f"carrier_courier_{region.code}",
                _region_home(region.code),
                "flock",
                f"regional courier for {region.name}",
            )
            for region in REGIONS[3:10]
        ),
    )
    warehouses = tuple(
        _instance(
            "warehouse",
            f"wh_{name}_{city}",
            country,
            _cycle(("classic", "nest"), index),
            f"The {name.title()} fulfilment centre",
        )
        for index, (name, city, country) in enumerate(_WAREHOUSE_SITES)
    )
    stores = tuple(
        _instance("store", f"store_{city}", country, "nest", f"retail store in {city}")
        for city, country in _STORE_CITIES
    )
    suppliers = tuple(
        _instance(
            "supplier",
            f"sup_{category}_{number:02d}",
            country,
            _cycle(("nest", "flock", "classic"), number),
            f"{category} goods supplier {number}",
        )
        for category, country in _SUPPLIER_CATEGORIES
        for number in range(1, 6)
    )
    gateways = tuple(
        _instance("gateway", code, country, "nest", code.replace("_", " "))
        for code, country in _GATEWAYS
    )
    ad_networks = tuple(
        _instance("ad_network", code, country, "flock", code.replace("_", " "))
        for code, country in _AD_NETWORKS
    )
    messaging = tuple(
        _instance("messaging", code, country, "nest", code.replace("_", " "))
        for code, country in _MESSAGING
    )
    affiliates = tuple(
        _instance(
            "affiliate",
            f"aff_{region.code}",
            _region_home(region.code),
            "nest",
            f"affiliate network for {region.name}",
        )
        for region in REGIONS[:8]
    )
    collectors = tuple(
        _instance("collector", code, _COLLECTOR_HOME[code], "flock", code.replace("_", " "))
        for code in _COLLECTORS
    )
    support_tools = tuple(
        _instance("support", code, country, "nest", code.replace("_", " "))
        for code, country in _SUPPORT_TOOLS
    )
    legal_entities = tuple(
        _instance(
            "ledger",
            f"le_{country.lower()}",
            country,
            "classic" if country in ("GB", "DE", "US") else "nest",
            f"Mallard & Co. legal entity in {country}",
        )
        for country in _LEGAL_ENTITY_COUNTRIES
    )
    wholesale = tuple(
        _instance(
            "wholesale",
            f"b2b_{region.code}",
            _region_home(region.code),
            "nest",
            f"wholesale desk for {region.name}",
        )
        for region in REGIONS
    )
    returns_portals = tuple(
        _instance(
            "returns",
            f"returns_{region.code}",
            _region_home(region.code),
            "flock",
            f"returns portal for {region.name}",
        )
        for region in REGIONS
    )
    catalogue = (_instance("catalogue", "pim", "GB", "nest", "product information system"),)
    return {
        "marketplace": tuple(unique_marketplaces),
        "carrier": carriers,
        "warehouse": warehouses,
        "store": stores,
        "supplier": suppliers,
        "gateway": gateways,
        "ad_network": ad_networks,
        "messaging": messaging,
        "affiliate": affiliates,
        "collector": collectors,
        "support": support_tools,
        "ledger": legal_entities,
        "wholesale": wholesale,
        "returns": returns_portals,
        "catalogue": catalogue,
    }


def storefront_instances() -> tuple[Instance, ...]:
    return tuple(
        Instance(
            system="storefront",
            code=storefront.code,
            region=storefront.region,
            timezone=storefront.timezone,
            currency=storefront.currency,
            platform=storefront.platform,
            label=f"storefront for {storefront.country}",
        )
        for storefront in STOREFRONTS
    )
