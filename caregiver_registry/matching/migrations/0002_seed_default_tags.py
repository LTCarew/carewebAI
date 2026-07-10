"""
Seed migration: populate the Tag table with default hashtag options.
These mirror the care-need and experience keys already used in registry models.
"""
from django.db import migrations

DEFAULT_TAGS = [
    # Care skills / experience
    ("transfers", "Transfers / Lifting"),
    ("wheelchair", "Wheelchair / Chair User"),
    ("dementia", "Dementia / Alzheimer's"),
    ("alzheimers", "Alzheimer's"),
    ("cooking", "Cooking / Meal Preparation"),
    ("errands", "Errands"),
    ("companionship", "Companionship"),
    ("transportation", "Transportation / Driving"),
    ("visual-impairment", "Visual Impairment"),
    ("deaf", "d/Deaf Community"),
    ("fragrance-free", "Fragrance-Free"),
    ("lgbtq", "LGBTQ+ Affirming"),
    ("catheters", "Catheter Support"),
    ("feeding-tube", "Feeding Tube"),
    ("hoyer-lifts", "Hoyer Lifts"),
    ("ventilators", "Ventilators"),
    ("bowel-programs", "Bowel Programs"),
    ("assistive-technology", "Assistive Technology"),
    ("bathing", "Bathing Assistance"),
    ("dressing", "Dressing Assistance"),
    ("domestic-tasks", "Domestic Tasks"),
    ("chronic-illness", "Chronic Illness"),
    ("cognitive-disabilities", "Cognitive Disabilities"),
    ("spinal-cord", "Spinal Cord Disabilities"),
    ("developmental-disabilities", "Developmental Disabilities"),
    ("complex-illnesses", "Complex Illnesses"),
    ("emergency-preparedness", "Emergency Preparedness"),
    ("elders", "Elders / Older Adults"),
    ("ihss", "IHSS"),
    ("person-centered", "Person-Centered Care"),
    # Certifications / training
    ("cna", "CNA"),
    ("cpr", "CPR Training"),
    ("emt", "EMT Training"),
    ("anti-bias", "Anti-Bias Training"),
    ("soft-skills", "Soft Skills Training"),
    ("cil-courses", "CIL Caregiver Courses"),
    # Language / access
    ("limited-english", "Limited English Support"),
    ("asl", "ASL / Sign Language"),
    # Schedule
    ("live-in", "Live-In"),
    ("full-time", "Full-Time"),
    ("part-time", "Part-Time"),
    ("flexible-hours", "Flexible Hours"),
]


def seed_tags(apps, schema_editor):
    Tag = apps.get_model("matching", "Tag")
    for name, label in DEFAULT_TAGS:
        Tag.objects.get_or_create(name=name, defaults={"label": label})


def unseed_tags(apps, schema_editor):
    Tag = apps.get_model("matching", "Tag")
    names = [name for name, _ in DEFAULT_TAGS]
    Tag.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("matching", "0001_initial_matching_models"),
    ]

    operations = [
        migrations.RunPython(seed_tags, reverse_code=unseed_tags),
    ]
