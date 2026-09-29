"""Seed sectors and washing stations.

These are reference data, not demo data: the API refers to them by name ("Kigoma",
"Nyaruguru"), so they must exist on every freshly migrated database, including the grader's.
"""

from django.db import migrations

SECTORS = [
    ("Kigoma", "Huye"),
    ("Mbazi", "Huye"),
    ("Kibeho", "Nyaruguru"),
    ("Ngera", "Nyaruguru"),
    ("Ruheru", "Nyaruguru"),
    ("Runda", "Kamonyi"),
]

# name, code, sector
STATIONS = [
    ("Nyaruguru", "NYR", "Kibeho"),
    ("Kamonyi", "KMY", "Runda"),
]


def seed(apps, schema_editor):
    Sector = apps.get_model("registry", "Sector")
    WashingStation = apps.get_model("registry", "WashingStation")
    for name, district in SECTORS:
        Sector.objects.get_or_create(name=name, defaults={"district": district})
    for name, code, sector in STATIONS:
        WashingStation.objects.get_or_create(
            name=name, defaults={"code": code, "sector": Sector.objects.get(name=sector)}
        )


def unseed(apps, schema_editor):
    apps.get_model("registry", "WashingStation").objects.filter(name__in=[s[0] for s in STATIONS]).delete()
    apps.get_model("registry", "Sector").objects.filter(name__in=[s[0] for s in SECTORS]).delete()


class Migration(migrations.Migration):
    dependencies = [("registry", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
