from django import forms
from django.db.models import Q

from . import crypto
from .models import Authorization, Client, Episode, FundingSource, Medication, Oca, WaitlistEntry

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class SSNMixin(forms.Form):
    ssn = forms.CharField(label="SSN", required=False, max_length=11,
                          help_text="9 digits. Leave blank to keep the current value.")

    def clean_ssn(self):
        raw = self.cleaned_data.get("ssn", "").strip()
        if raw and not crypto.normalize_ssn(raw):
            raise forms.ValidationError("Enter a valid 9-digit SSN.")
        return raw


class ClientForm(SSNMixin, forms.ModelForm):
    class Meta:
        model = Client
        fields = ["first_name", "last_name", "date_of_birth", "ssn", "medicaid_id", "gender", "race",
                  "ethnicity", "phone", "notes"]
        widgets = {"date_of_birth": DATE, "notes": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        cleaned = super().clean()
        ssn = crypto.normalize_ssn(cleaned.get("ssn"))
        if ssn:
            dupes = Client.objects.filter(ssn_hash=crypto.ssn_hash(ssn))
            if self.instance.pk:
                dupes = dupes.exclude(pk=self.instance.pk)
            if dupes.exists():
                raise forms.ValidationError(f"A client with this SSN already exists: {dupes.first()}.")
        return cleaned

    def save(self, commit=True):
        client = super().save(commit=False)
        if self.cleaned_data.get("ssn"):
            client.set_ssn(self.cleaned_data["ssn"])
        if commit:
            client.save()
        return client


class EpisodeForm(forms.ModelForm):
    class Meta:
        model = Episode
        fields = ["record_id", "funding_source", "level_of_care", "secondary_funding", "admit_date",
                  "bed", "diagnosis_code", "benefits_notes",
                  "discharge_date", "discharge_reason", "discharge_note", "notes"]
        widgets = {"admit_date": DATE, "discharge_date": DATE, "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["funding_source"].queryset = FundingSource.objects.filter(
            Q(is_active=True) | Q(pk=getattr(self.instance, "funding_source_id", None)))

    def clean(self):
        cleaned = super().clean()
        admit, discharge = cleaned.get("admit_date"), cleaned.get("discharge_date")
        if admit and discharge and discharge < admit:
            self.add_error("discharge_date", "Discharge date can't be before the admit date.")
        if discharge and not cleaned.get("discharge_reason"):
            self.add_error("discharge_reason", "Choose a discharge reason.")
        return cleaned


class DischargeForm(forms.ModelForm):
    class Meta:
        model = Episode
        fields = ["discharge_date", "discharge_reason", "discharge_note"]
        widgets = {"discharge_date": DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["discharge_date"].required = True
        self.fields["discharge_reason"].required = True

    def clean_discharge_date(self):
        value = self.cleaned_data["discharge_date"]
        if value < self.instance.admit_date:
            raise forms.ValidationError("Discharge date can't be before the admit date.")
        return value


class AuthorizationForm(forms.ModelForm):
    class Meta:
        model = Authorization
        fields = ["funding_source", "oca", "auth_number", "start_date", "end_date", "days_authorized", "notes"]
        widgets = {"start_date": DATE, "end_date": DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["oca"].queryset = Oca.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date can't be before the start date.")
        if start and end and not cleaned.get("days_authorized"):
            cleaned["days_authorized"] = (end - start).days
        return cleaned


class MedicationForm(forms.ModelForm):
    class Meta:
        model = Medication
        fields = ["drug", "dosage", "frequency", "quantity", "fill_date", "next_fill_date"]
        widgets = {"fill_date": DATE, "next_fill_date": DATE}


class WaitlistEntryForm(forms.ModelForm):
    class Meta:
        model = WaitlistEntry
        fields = ["funding_source", "status", "rank", "date_added", "referral_date", "referral_source",
                  "secondary_funding", "notes"]
        widgets = {"date_added": DATE, "referral_date": DATE, "notes": forms.Textarea(attrs={"rows": 3})}


class NewWaitlistClientForm(SSNMixin, forms.Form):
    """Client fields for adding someone to the waitlist who may not be in the system yet."""

    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100, required=False)
    date_of_birth = forms.DateField(required=False, widget=DATE)
    phone = forms.CharField(max_length=30, required=False)

    field_order = ["first_name", "last_name", "date_of_birth", "ssn", "phone"]

    def find_or_create_client(self):
        data = self.cleaned_data
        ssn = crypto.normalize_ssn(data.get("ssn"))
        client = None
        if ssn:
            client = Client.objects.filter(ssn_hash=crypto.ssn_hash(ssn)).first()
        if client is None and data.get("date_of_birth"):
            client = Client.objects.filter(first_name__iexact=data["first_name"], last_name__iexact=data["last_name"],
                                           date_of_birth=data["date_of_birth"]).first()
        if client is None:
            client = Client(first_name=data["first_name"], last_name=data["last_name"],
                            date_of_birth=data.get("date_of_birth"), phone=data.get("phone", ""))
            client.set_ssn(ssn)
            client.save()
        return client


class WaitlistAdmitForm(forms.ModelForm):
    class Meta:
        model = Episode
        fields = ["record_id", "funding_source", "level_of_care", "admit_date", "bed"]
        widgets = {"admit_date": DATE}


class WaitlistCloseForm(forms.Form):
    status = forms.ChoiceField(choices=[(WaitlistEntry.Status.DECLINED, "Declined / removed"),
                                        (WaitlistEntry.Status.ON_HOLD, "On hold")])
    reason = forms.CharField(max_length=255, required=False)
