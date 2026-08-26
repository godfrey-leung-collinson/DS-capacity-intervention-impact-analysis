"""Custom exceptions for capacity intervention impact analysis."""


class DataError(Exception):
    """Base exception for data-related failures in the analysis pipeline."""

    pass


class DataMissing(DataError):
    """Raised when required input data or columns are absent."""

    pass


class DataInvalid(DataError):
    """Raised when input data fails validation or business-rule checks."""

    pass


class DataInconsistent(DataError):
    """Raised when related data values conflict across records or sources."""

    pass


class InvalidSQL(Exception):
    """Raised when a SQL template cannot be rendered safely."""

    pass


class InvalidParameter(Exception):
    """Raised when an invalid parameter is provided."""

    pass


class MissingParameter(Exception):
    """Raised when a required parameter is missing."""

    pass