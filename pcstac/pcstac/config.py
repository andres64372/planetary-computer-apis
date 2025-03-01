from functools import lru_cache
from urllib.parse import urljoin

from fastapi import Request
from pydantic import BaseModel, BaseSettings, Field
from stac_fastapi.extensions.core import (
    FieldsExtension,
    FilterExtension,
    QueryExtension,
    SortExtension,
    TokenPaginationExtension,
)
from stac_fastapi.extensions.core.filter.filter import FilterConformanceClasses

from pccommon.config.core import ENV_VAR_PCAPIS_PREFIX, PCAPIsConfig
from pcstac.filter import PCFiltersClient

API_VERSION = "1.2"
STAC_API_VERSION = "v1.0.0-rc.1"

API_LANDING_PAGE_ID = "microsoft-pc"
API_TITLE = "Microsoft Planetary Computer STAC API"
API_DESCRIPTION = (
    "Searchable spatiotemporal metadata describing Earth science datasets "
    "hosted by the Microsoft Planetary Computer"
)

TILER_HREF_ENV_VAR = "TILER_HREF"
DB_MIN_CONN_ENV_VAR = "DB_MIN_CONN_SIZE"
DB_MAX_CONN_ENV_VAR = "DB_MAX_CONN_SIZE"
REQUEST_TIMEOUT_ENV_VAR = "REQUEST_TIMEOUT"

EXTENSIONS = [
    # STAC API Extensions
    QueryExtension(),
    SortExtension(),
    FieldsExtension(),
    FilterExtension(
        client=PCFiltersClient(),
        conformance_classes=[
            FilterConformanceClasses.FILTER,
            FilterConformanceClasses.ITEM_SEARCH_FILTER,
            FilterConformanceClasses.BASIC_CQL2,
            FilterConformanceClasses.CQL2_JSON,
            FilterConformanceClasses.CQL2_TEXT,
        ],
    ),
    # stac_fastapi extensions
    TokenPaginationExtension(),
]


class RateLimits(BaseModel):
    collections: int = 500
    collection: int = 500
    item: int = 500
    items: int = 100
    search: int = 100


class BackPressureConfig(BaseModel):
    req_per_sec: int = 50
    inc_ms: int = 10


class BackPressures(BaseSettings):
    collections: BackPressureConfig
    collection: BackPressureConfig
    item: BackPressureConfig
    items: BackPressureConfig
    search: BackPressureConfig


class Settings(BaseSettings):
    """Class for specifying application parameters

    ...

    Attributes
    ----------
    tiler_href : str
        URL root for tiling endpoints
    openapi_url : str
        relative path to JSON document which describes the application's API
    debug : bool
        flag directing the application to operate in debugging mode
    api_version : str
        version of application
    """

    api = PCAPIsConfig.from_environment()

    debug: bool = False
    tiler_href: str = Field(env=TILER_HREF_ENV_VAR, default="")
    db_max_conn_size: int = Field(env=DB_MAX_CONN_ENV_VAR, default=1)
    db_min_conn_size: int = Field(env=DB_MIN_CONN_ENV_VAR, default=1)
    openapi_url: str = "/openapi.json"
    api_version: str = f"v{API_VERSION}"
    rate_limits: RateLimits
    back_pressures: BackPressures
    request_timout: int = Field(env=REQUEST_TIMEOUT_ENV_VAR, default=30)

    def get_tiler_href(self, request: Request) -> str:
        """Generates the tiler HREF.

        if the setting for the tiler HREF
        is relative, then use the request's base URL to generate the
        absolute URL.
        """
        if request:
            base_hostname = f"{request.url.scheme}://{request.url.netloc}/"
            return urljoin(base_hostname, self.tiler_href)
        else:
            return self.tiler_href

    class Config:
        env_prefix = ENV_VAR_PCAPIS_PREFIX
        extra = "ignore"
        env_nested_delimiter = "__"


@lru_cache
def get_settings() -> Settings:
    return Settings()
