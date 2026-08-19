from django.db import models

class Lead(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, default="N/A")
    website = models.CharField(max_length=500, default="N/A")
    emails = models.CharField(max_length=500, default="N/A")
    address = models.TextField(default="N/A")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name