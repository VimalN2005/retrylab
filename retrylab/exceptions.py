"""
RetryLab Exceptions hierarchy.
"""


class RetryLabError(Exception):
    """Base exception for all RetryLab errors."""


class ScenarioValidationError(RetryLabError):
    """Raised when a fault scenario definition is invalid."""


class FaultInjectionError(RetryLabError):
    """Base exception for simulated faults."""


class SimulatedTimeoutError(FaultInjectionError):
    """Simulated network or read timeout."""


class SimulatedConnectionError(FaultInjectionError):
    """Simulated connection failure or socket reset."""


class SimulatedDNSError(SimulatedConnectionError):
    """Simulated DNS lookup, NXDOMAIN, or name resolution error."""


class SimulatedSSLError(SimulatedConnectionError):
    """Simulated TLS certificate validation or handshake failure."""


class SimulatedTLSHandshakeTimeout(SimulatedTimeoutError):
    """Simulated TLS handshake negotiation stall or timeout."""


class RecoveryAssertionError(RetryLabError):
    """Raised when an application fails to recover as expected."""


class IdempotencyViolationError(RetryLabError):
    """Raised when a retried request violates idempotency constraints."""
