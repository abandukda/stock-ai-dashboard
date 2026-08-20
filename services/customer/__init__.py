"""Provider-independent ATLAS customer-domain foundation."""

from .entitlements import ENTITLEMENT_VERSION, entitlements_for
from .models import (
    AlertFrequency,
    AlertType,
    Capability,
    NotificationChannel,
    PlanTier,
)
from .repository import CustomerRepository, InMemoryCustomerRepository
from .service import CustomerService

__all__ = [
    "AlertFrequency", "AlertType", "Capability", "CustomerRepository",
    "CustomerService", "ENTITLEMENT_VERSION", "InMemoryCustomerRepository",
    "NotificationChannel", "PlanTier", "entitlements_for",
]
