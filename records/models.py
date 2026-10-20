from datetime import date

from django.conf import settings
from django.db import models
from django.urls import reverse

from . import crypto


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class LevelOfCare(models.TextChoices):
    RESIDENTIAL = "residential", "Residential"
    OUTPATIENT = "outpatient", "Outpatient"
    MAT = "mat", "MAT"
    OTHER = "other", "Other"


class FundingSource(TimeStamped):
    name = models.CharField(max_length=100, unique=True)
    level_of_care = models.CharField(max_length=20, choices=LevelOfCare.choices, default=LevelOfCare.RESIDENTIAL)
    bed_capacity = models.PositiveIntegerField(null=True, blank=True, help_text="Contracted beds or slots, if any.")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Client(TimeStamped):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    ssn_encrypted = models.TextField(blank=True, editable=False)
    ssn_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    ssn_last4 = models.CharField(max_length=4, blank=True, editable=False)
    medicaid_id = models.CharField(max_length=30, blank=True)
    gender = models.CharField(max_length=30, blank=True)
    race = models.CharField(max_length=50, blank=True)
    ethnicity = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["last_name", "first_name"])]
        permissions = [("view_full_ssn", "Can view full SSN")]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def ssn(self):
        return crypto.decrypt(self.ssn_encrypted)

    def set_ssn(self, raw):
        ssn = crypto.normalize_ssn(raw)
        self.ssn_encrypted = crypto.encrypt(ssn)
        self.ssn_hash = crypto.ssn_hash(ssn)
        self.ssn_last4 = ssn[-4:] if ssn else ""

    @property
    def ssn_masked(self):
        return f"***-**-{self.ssn_last4}" if self.ssn_last4 else ""

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    def get_absolute_url(self):
        return reverse("client_detail", args=[self.pk])


class DischargeReason(models.TextChoices):
    SUCCESSFUL = "successful", "Successful"
    SUCCESSFUL_TO_OP = "successful_to_op", "Successful, stepped down to outpatient"
    ASA = "asa", "ASA (against staff advice)"
    ELOPEMENT = "elopement", "Elopement"
    ADMIN = "admin", "Administrative discharge"
    APPREHENDED = "apprehended", "Apprehended"
    INCARCERATED = "incarcerated", "Incarcerated"
    TRANSFER = "transfer", "Transfer"
    HOSPITAL = "hospital", "Discharged to hospital"
    READMIT = "readmit", "Readmitted to residential"
    NO_INTAKE = "no_intake", "Did not complete intake"
    STOPPED_REPORTING = "stopped_reporting", "Stopped reporting"
    OTHER = "other", "Other"


class EpisodeQuerySet(models.QuerySet):
    def active(self):
        return self.filter(discharge_date__isnull=True)


class Episode(TimeStamped):
    """One admission of a client to a program (an episode of care)."""

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="episodes")
    record_id = models.CharField("Client ID / MR#", max_length=30, blank=True, db_index=True,
                                 help_text="Program record number, e.g. R07-121 or O21-143-2.")
    level_of_care = models.CharField(max_length=20, choices=LevelOfCare.choices, default=LevelOfCare.RESIDENTIAL)
    funding_source = models.ForeignKey(FundingSource, on_delete=models.PROTECT, related_name="episodes")
    initial_funding_source = models.ForeignKey(FundingSource, on_delete=models.SET_NULL, null=True, blank=True,
                                               related_name="initial_episodes")
    secondary_funding = models.CharField("Secondary funding / notes", max_length=255, blank=True)
    admit_date = models.DateField()
    discharge_date = models.DateField(null=True, blank=True)
    discharge_reason = models.CharField(max_length=30, choices=DischargeReason.choices, blank=True)
    discharge_note = models.CharField(max_length=255, blank=True)
    bed = models.CharField(max_length=20, blank=True)
    diagnosis_code = models.CharField(max_length=20, blank=True)
    benefits_notes = models.CharField("Disability / SSI / unemployment", max_length=255, blank=True)
    notes = models.TextField(blank=True)

    objects = EpisodeQuerySet.as_manager()

    class Meta:
        ordering = ["-admit_date"]
        indexes = [models.Index(fields=["discharge_date"]), models.Index(fields=["admit_date"])]

    def __str__(self):
        return f"{self.client} · {self.funding_source} · {self.admit_date:%m/%d/%Y}"

    @property
    def is_active(self):
        return self.discharge_date is None

    @property
    def length_of_stay(self):
        end = self.discharge_date or date.today()
        return (end - self.admit_date).days

    def get_absolute_url(self):
        return reverse("episode_detail", args=[self.pk])


class Oca(TimeStamped):
    """OCA: a sub-funding source (contract code) under SFBHN or SFBHNMH, e.g. MS003 or MH001."""

    code = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=255, blank=True)
    funding_sources = models.ManyToManyField(FundingSource, related_name="ocas",
                                             help_text="Funding sources this OCA can be billed under.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "OCA"
        verbose_name_plural = "OCAs"

    def __str__(self):
        return self.code


class Authorization(TimeStamped):
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name="authorizations")
    funding_source = models.ForeignKey(FundingSource, on_delete=models.PROTECT, related_name="authorizations")
    oca = models.ForeignKey(Oca, on_delete=models.PROTECT, null=True, blank=True, related_name="authorizations",
                            verbose_name="OCA", help_text="Sub-funding source. Only for SFBHN and SFBHNMH.")
    auth_number = models.CharField(max_length=60, blank=True, help_text="Leave blank if the authorization is still needed.")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    days_authorized = models.PositiveIntegerField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-end_date"]

    def __str__(self):
        return self.auth_number or "Authorization needed"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.oca_id and self.funding_source_id and not self.oca.funding_sources.filter(pk=self.funding_source_id).exists():
            raise ValidationError({"oca": f"OCA {self.oca} doesn't apply to {self.funding_source}."})

    @property
    def days_remaining(self):
        if not self.end_date:
            return None
        return (self.end_date - date.today()).days

    @property
    def status(self):
        if not self.auth_number:
            return "needed"
        remaining = self.days_remaining
        if remaining is None:
            return "open"
        if remaining < 0:
            return "expired"
        if remaining <= 14:
            return "expiring"
        return "current"


class WaitlistEntry(TimeStamped):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        ON_HOLD = "on_hold", "On hold"
        ADMITTED = "admitted", "Admitted"
        DECLINED = "declined", "Declined / removed"

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="waitlist_entries")
    funding_source = models.ForeignKey(FundingSource, on_delete=models.PROTECT, null=True, blank=True,
                                       related_name="waitlist_entries")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING, db_index=True)
    rank = models.PositiveIntegerField(null=True, blank=True, help_text="Lower ranks are offered a bed first.")
    date_added = models.DateField(default=date.today, null=True, blank=True)
    referral_date = models.DateField(null=True, blank=True)
    referral_source = models.CharField(max_length=255, blank=True)
    secondary_funding = models.CharField("Secondary funding / notes", max_length=255, blank=True)
    notes = models.TextField(blank=True)
    closed_date = models.DateField(null=True, blank=True)
    closed_reason = models.CharField(max_length=255, blank=True)
    admitted_episode = models.OneToOneField(Episode, on_delete=models.SET_NULL, null=True, blank=True,
                                            related_name="waitlist_entry")

    class Meta:
        ordering = ["status", "rank", "date_added"]
        verbose_name_plural = "waitlist entries"

    def __str__(self):
        return f"{self.client} ({self.get_status_display()})"

    @property
    def days_waiting(self):
        end = self.closed_date or date.today()
        return (end - self.date_added).days if self.date_added else None


class Medication(TimeStamped):
    """MAT prescriptions and fills."""

    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name="medications")
    drug = models.CharField(max_length=100)
    dosage = models.CharField(max_length=50, blank=True)
    frequency = models.CharField(max_length=50, blank=True)
    quantity = models.PositiveIntegerField(null=True, blank=True)
    fill_date = models.DateField(null=True, blank=True)
    next_fill_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-fill_date"]

    def __str__(self):
        return " ".join(p for p in [self.drug, self.dosage, self.frequency] if p)


class AuditLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=10)  # create, update, delete, view
    model = models.CharField(max_length=50)
    object_id = models.CharField(max_length=40)
    object_repr = models.CharField(max_length=200, blank=True)
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.user} {self.action} {self.model} {self.object_id}"
