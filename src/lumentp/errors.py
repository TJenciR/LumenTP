"""Custom exceptions for protocol parsing and runtime issues."""


class LumenTPError(Exception):
    """Base exception for LumenTP errors."""


class ParseError(LumenTPError):
    """Raised when a message cannot be parsed."""


class ValidationError(LumenTPError):
    """Raised when a message contains invalid fields."""
