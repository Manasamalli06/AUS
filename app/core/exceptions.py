class GeospatialAPIException(Exception):
    """Base exception for Geospatial API."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class FileProcessingException(GeospatialAPIException):
    """Raised when parsing or extracting geospatial file fails."""
    def __init__(self, message: str):
        super().__init__(message=message, status_code=422)


class InvalidFileFormatException(GeospatialAPIException):
    """Raised when file extension or content is invalid."""
    def __init__(self, message: str):
        super().__init__(message=message, status_code=400)


class FileNotFoundInStorageException(GeospatialAPIException):
    """Raised when a requested file ID is not found."""
    def __init__(self, file_id: str):
        super().__init__(message=f"File with ID '{file_id}' not found.", status_code=404)


class CRSTransformationException(GeospatialAPIException):
    """Raised when coordinate reference system transformation fails."""
    def __init__(self, message: str):
        super().__init__(message=message, status_code=422)
