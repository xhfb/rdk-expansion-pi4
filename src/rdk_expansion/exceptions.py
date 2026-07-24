"""Public exception hierarchy."""


class RdkExpansionError(RuntimeError):
    """Base error for the package."""


class HardwareNotFound(RdkExpansionError):
    """Required hardware or Linux device is unavailable."""


class UnsupportedOnHost(RdkExpansionError):
    """The board signal cannot provide the requested function on this host."""


class UnsafeConfiguration(RdkExpansionError):
    """Configuration could drive the board in an unsafe way."""


class ResourceBusy(RdkExpansionError):
    """A shared hardware resource is already in use."""

