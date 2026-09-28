class DomainError(Exception):
    """Business-rule violation. Mapped to an HTTP error with a stable code."""

    status_code = 400

    def __init__(self, message: str, code: str = "domain_error", status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFound(DomainError):
    status_code = 404

    def __init__(self, what: str):
        super().__init__(f"{what} not found", "not_found")


class Forbidden(DomainError):
    status_code = 403

    def __init__(self, message: str = "Not permitted", code: str = "forbidden"):
        super().__init__(message, code)


class Conflict(DomainError):
    status_code = 409

    def __init__(self, message: str, code: str = "conflict"):
        super().__init__(message, code)
