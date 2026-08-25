
class DataError(Exception):
    """Base class for data errors."""
    pass

class DataMissing(DataError):
    """Data is missing."""
    pass

class DataInvalid(DataError):
    """Data is invalid."""
    pass

class DataInconsistent(DataError):
    """Data is inconsistent."""
    pass

class InvalidSQL(Exception):
    """SQL is invalid."""
    pass