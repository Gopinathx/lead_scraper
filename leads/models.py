from django.db import models
import uuid

class Lead(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, default="N/A")
    website = models.CharField(max_length=500, default="N/A")
    emails = models.CharField(max_length=500, default="N/A")
    address = models.TextField(default="N/A")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ScraperJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, default="RUNNING") # RUNNING, COMPLETED, FAILED
    created_at = models.DateTimeField(auto_now_add=True)

class ScraperLog(models.Model):
    job = models.ForeignKey(ScraperJob, on_delete=models.CASCADE, related_name="logs")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)