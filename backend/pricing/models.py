from django.db import models


class Barangay(models.Model):
    """A barangay and its center point, used when a customer has no pin.

    The center is stored as latitude and longitude in decimal degrees
    (WGS 84). Distances are worked out by PostGIS in pricing.delivery_fee.
    """

    name = models.CharField(max_length=120, unique=True)
    center_lat = models.DecimalField(max_digits=9, decimal_places=6)
    center_lng = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def center(self) -> tuple[float, float]:
        return (float(self.center_lat), float(self.center_lng))
