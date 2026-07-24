"""RDK 40Pin expansion board support package."""

from .board import ExpansionBoard
from .exceptions import (
    HardwareNotFound,
    RdkExpansionError,
    ResourceBusy,
    UnsafeConfiguration,
    UnsupportedOnHost,
)
from .models import AdcSample, PowerSample

__all__ = [
    "AdcSample",
    "ExpansionBoard",
    "HardwareNotFound",
    "PowerSample",
    "RdkExpansionError",
    "ResourceBusy",
    "UnsafeConfiguration",
    "UnsupportedOnHost",
]

__version__ = "0.1.0"

