from django.db import models


class TripSubmission(models.Model):
    """Persists driver context for each planned trip."""

    driver_name = models.CharField(max_length=255, blank=True)
    log_date = models.DateField()
    duty_start = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.log_date} {self.duty_start} — {self.driver_name or '(no name)'}"

