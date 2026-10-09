from datetime import timedelta

from django.db import migrations
from django.db.models import F

# The deadline in force when these rows were written (the frontend's 150 s); fixed here so
# the migration means the same thing whatever QUERY_DEADLINE_SECONDS later becomes.
LEGACY_DEADLINE = timedelta(seconds=150)


def backfill(apps, schema_editor):
    QueryRequest = apps.get_model("queries", "QueryRequest")
    QueryRequest.objects.filter(expires_at__isnull=True).update(expires_at=F("created_at") + LEGACY_DEADLINE)
    # Until now a finished row's updated_at was its finish time (nothing saved it afterwards).
    QueryRequest.objects.filter(status__in=["done", "error"], finished_at__isnull=True).update(
        finished_at=F("updated_at")
    )


class Migration(migrations.Migration):
    dependencies = [("queries", "0002_query_request_deadline_and_finish")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
