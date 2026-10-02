"""Exception hierarchy. Every user-facing failure raises a subclass with an actionable message."""


class NaadrikError(Exception):
    """Base class for all Naadrik errors."""


class ConfigError(NaadrikError):
    """The configuration file is missing, malformed or holds an invalid value."""


class AudioDeviceError(NaadrikError):
    """The audio output device could not be opened or failed while playing."""
