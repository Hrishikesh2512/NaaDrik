"""Exception hierarchy. Every user-facing failure raises a subclass with an actionable message."""


class NaadrikError(Exception):
    """Base class for all Naadrik errors."""


class ConfigError(NaadrikError):
    """The configuration file is missing, malformed or holds an invalid value."""


class AudioDeviceError(NaadrikError):
    """The audio output device could not be opened or failed while playing."""


class CameraError(NaadrikError):
    """The camera could not be opened or stopped delivering frames."""


class ModelNotFoundError(NaadrikError):
    """A model file is missing or cannot be loaded."""


class SpeechError(NaadrikError):
    """Offline text-to-speech is unavailable or failed."""
