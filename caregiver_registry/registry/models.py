from django.db import models
from organizations.models import Organization
import uuid
from django.utils import timezone
from datetime import timedelta

def default_invite_expiration():
    return timezone.now() + timedelta(days=7)

# ==============================================
# Invites
# ==============================================
ROLE_CHOICES = [
    ("caregiver", "Caregiver"),
    ("client", "Client"),
]


class Invite(models.Model):
    email = models.EmailField()
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES
    )
    token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        default=default_invite_expiration
    )
    accepted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.email} - {self.role}"


# ==============================================
# Caregivers and Clients
# ==============================================
STATUS_CHOICES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]


CONTACT_PREFERENCES = [
    ("phone", "Phone"),
    ("email", "Email"),
    ("text", "Text Message"),
    ("any", "Any"),
]


PRONOUN_CHOICES = [
    ("she_her", "She/Her"),
    ("he_him", "He/Him"),
    ("they_them", "They/Them"),
    ("she_they", "She/They"),
    ("he_they", "He/They"),
    ("ze_zir", "Ze/Zir"),
    ("ask_me", "Ask Me"),
    ("self_describe", "Self Describe"),
]


TRANSPORTATION_CHOICES = [
    ("licensed_driver", "Licensed Driver"),
    ("vehicle_access", "Reliable access to a vehicle"),
    ("wheelchair_vehicle", "Comfortable driving or learning wheelchair accessible vehicles"),
    ("insured", "Insured"),
    ("comfortable_driving_others", "Comfortable driving others"),
    ("no_driving", "Looking for work that doesn't involve driving"),
]


HOURS_LOOKING_FOR_CHOICES = [
    ("all_welcome", "All are welcome"),
    ("few_hours", "Just a few hours"),
    ("part_time", "Part-Time"),
    ("full_time", "Full Time"),
    ("live_in", "Live-In"),
    ("flexible", "Flexible"),
]


EXPERIENCE_CHOICES = [
    ("domestic_tasks", "Domestic tasks"),
    ("errands", "Willing to run errands"),
    ("bathing", "Bathing assistance"),
    ("cooking", "Cooking / meal preparation"),
    ("dressing", "Dressing assistance"),

    ("assistive_technology", "Assistive Technology Maintenance"),
    ("bowel_programs", "Bowel Programs"),
    ("couple_family", "Caring for a couple/small family"),
    ("catheters", "Catheters"),
    ("chair_users", "Chair Users"),
    ("chronic_illness", "Chronic Illness Disabilities"),
    ("cna", "CNA"),
    ("cognitive_disabilities", "Cognitive Disabilities"),
    ("complex_illnesses", "Complex Illnesses"),
    ("cpr", "CPR Training"),
    ("deaf_community", "d/Deaf community"),
    ("dementia", "Dementia/Alzheimers"),
    ("developmental_disabilities", "Developmental disabilities"),
    ("elders", "Elders/Older Adults"),
    ("emergency_preparedness", "Emergency Preparedness Plans"),
    ("emt", "EMT Training"),
    ("cil_courses", "Enrolled in CIL Caregiver Courses"),
    ("feeding_tubes", "Feeding Tubes"),
    ("fragrance_free", "Fragrance-Free"),
    ("anti_bias", "Has taken anti-bias trainings"),
    ("soft_skills", "Has taken soft skills trainings"),
    ("hoyer_lifts", "Hoyer Lifts"),
    ("ihss", "IHSS"),
    ("lgbtq", "LGBTQ+"),
    ("lifting_transfers", "Lifting/Transfers"),
    ("limited_english", "Multi-Lingual Limited English Speakers"),
    ("person_centered", "Person-centered care"),
    ("spinal_cord", "Spinal Cord Disabilities"),
    ("ventilators", "Ventilators"),
    ("visual_impairments", "Visual impairments"),
]

LANGUAGE_CHOICES = [
    ("english", "English"),
    ("spanish", "Spanish"),
    ("asl", "ASL"),
    ("cantonese", "Cantonese"),
    ("mandarin", "Mandarin"),
    ("portuguese_brazilian", "Portuguese (Brazilian)"),
    ("portuguese_portugal", "Portuguese (Portugal)"),
    ("other_languages", "Other Languages"),
]

PATHOGEN_PROTOCOL_CHOICES = [
    ("n95_at_work", "Willing to mask with N95's at work"),
    ("masking_indoors", "Consistently masking indoors"),
    ("masking_crowded_outdoors", "Consistently masking in crowded spaces outdoors"),
    ("masking_around_others", "Consistently masking around anyone not taking protocols"),
    ("adjust_protocols", "Open to adjusting daily life protocols"),
    ("learn_more", "Interested in learning more about pathogen safety"),
]


RATE_CHOICES = [
    ("17_20", "$17-$20/hr"),
    ("20_25", "$20-$25/hr"),
    ("25_30", "$25-$30/hr"),
    ("30_50", "$30-$50/hr"),
    ("50_plus", "$50+/hr"),
]


ATTENDANT_PROGRAM_CHOICES = [
    ("ihss", "IHSS - In Home Supportive Services"),
    ("wpcs", "WPCS - Waiver Personal Care Services"),
    ("sls", "SLS - Supportive Living Services"),
    ("sdp", "SDP - Self Determination Program"),
    ("out_of_pocket", "Pay out of pocket"),
]


CARE_NEEDS_CHOICES = [
    ("domestic_tasks", "Domestic tasks"),
    ("errands", "Errands"),
    ("bathing", "Bathing"),
    ("cooking", "Cooking"),
    ("dressing", "Dressing"),

    ("assistive_technology", "Assistive technology maintenance"),
    ("bowel_programs", "Bowel programs"),
    ("couple_family", "Care for a couple/small family"),
    ("catheters", "Catheter support"),
    ("chair_users", "Wheelchair / chair user support"),
    ("chronic_illness", "Chronic illness support"),
    ("cognitive_disabilities", "Cognitive disability support"),
    ("complex_illnesses", "Complex illness support"),
    ("deaf_community", "d/Deaf community support"),
    ("dementia", "Dementia/Alzheimer’s support"),
    ("developmental_disabilities", "Developmental disability support"),
    ("elders", "Elder / older adult support"),
    ("emergency_preparedness", "Emergency preparedness planning"),
    ("feeding_tubes", "Feeding tube support"),
    ("fragrance_free", "Fragrance-free support needed"),
    ("hoyer_lifts", "Hoyer lift support"),
    ("ihss", "IHSS experience preferred"),
    ("lgbtq", "LGBTQ+ affirming care"),
    ("lifting_transfers", "Lifting / transfers"),
    ("limited_english", "Support for limited English speakers"),
    ("person_centered", "Person-centered care"),
    ("spinal_cord", "Spinal cord disability support"),
    ("ventilators", "Ventilator support"),
    ("visual_impairments", "Visual impairment support"),

    ("cna_preferred", "CNA preferred"),
    ("cpr_preferred", "CPR training preferred"),
    ("emt_preferred", "EMT training preferred"),
    ("anti_bias_preferred", "Anti-bias training preferred"),
    ("soft_skills_preferred", "Soft skills training preferred"),
    ("cil_training_preferred", "CIL caregiver course training preferred"),
]


class Caregiver(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=25)
    email = models.EmailField()

    contact_preferences = models.JSONField(default=list, blank=True)
    pronouns = models.CharField(max_length=50, choices=PRONOUN_CHOICES, blank=True)

    base_zip_code = models.CharField(max_length=10)
    willing_to_work_cities = models.JSONField(default=list, blank=True)

    transportation = models.JSONField(default=list, blank=True)
    availability = models.JSONField(default=dict, blank=True)

    hours_looking_for = models.CharField(
        max_length=50,
        choices=HOURS_LOOKING_FOR_CHOICES
    )

    certified_ihss_worker = models.BooleanField(default=False)
    additional_certifications = models.TextField(blank=True)

    experience_with = models.JSONField(default=list, blank=True)
    languages_spoken = models.JSONField(default=list, blank=True)
    pathogen_protocols = models.JSONField(default=list, blank=True)

    rate = models.CharField(max_length=50, choices=RATE_CHOICES)

    bio = models.TextField(blank=True)

    availability_confirmation_agreement = models.BooleanField(default=False)
    wants_training_updates = models.BooleanField(default=False)

    other_ways_find_work = models.TextField(blank=True)
    helpful_for_finding_work = models.TextField(blank=True)

    release_of_liability = models.BooleanField(default=False)
    signed_date = models.DateField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    profile_completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Client(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=25)
    email = models.EmailField()

    contact_preferences = models.JSONField(default=list, blank=True)
    pronouns = models.CharField(max_length=50, choices=PRONOUN_CHOICES, blank=True)

    address = models.TextField()
    base_zip_code = models.CharField(max_length=10)

    attendant_care_programs = models.JSONField(default=list, blank=True)

    languages_preferred = models.JSONField(default=list, blank=True)

    availability = models.JSONField(default=dict, blank=True)
    schedule_flexibility = models.BooleanField(default=False)
    hours_per_week = models.PositiveIntegerField(null=True, blank=True)

    care_needs = models.JSONField(default=list, blank=True)
    additional_care_needs = models.TextField(blank=True)

    preferences = models.TextField(blank=True)

    pathogen_protocol_preferences = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    profile_completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name