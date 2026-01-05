"""Compatibility shim for SPA data helpers.

This module used to contain all SPA URL/network/extraction functions.
It now re-exports the implementation from smaller modules.
"""

from src.services.spa_client import fetch_data_from_api, get_url_spa
from src.services.spa_extract import (
    get_data_actual,
    get_data_range,
    get_line_performance_details,
    process_data,
)

__all__ = [
    "get_url_spa",
    "fetch_data_from_api",
    "process_data",
    "get_line_performance_details",
    "get_data_actual",
    "get_data_range",
]
