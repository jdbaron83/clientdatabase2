from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from .management.commands.seed_from_masterlog import discharge_reason, split_name, to_date
from .models import AuditLog, Authorization, Client, DischargeReason, Episode, FundingSource, Oca, WaitlistEntry

KEY = "1lsgq3mCnA5MZsdY5o6aBdWdTXL1E5mFXRmNP0q0bkM="


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
class AppTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "a@example.com", "a-long-test-password")
        self.client.force_login(self.user)
        self.sfbhn = FundingSource.objects.create(name="SFBHN")
        self.va = FundingSource.objects.create(name="VA GPD")
        self.oca = Oca.objects.create(code="MS003")
        self.oca.funding_sources.add(self.sfbhn)
        self.person = Client(first_name="Test", last_name="Person", date_of_birth=date(1980, 1, 2))
        self.person.set_ssn("123-45-6789")
        self.person.save()
        self.episode = Episode.objects.create(client=self.person, funding_source=self.sfbhn,
                                              admit_date=date.today() - timedelta(days=10), record_id="R26-001")

    def test_ssn_is_encrypted_and_masked(self):
        self.person.refresh_from_db()
        self.assertNotIn("6789", self.person.ssn_encrypted)
        self.assertEqual(self.person.ssn, "123456789")
        self.assertEqual(self.person.ssn_masked, "***-**-6789")

    def test_pages_load(self):
        for url in [reverse("dashboard"), reverse("client_list") + "?q=person", reverse("client_list") + "?q=123456789",
                    self.person.get_absolute_url(), self.episode.get_absolute_url(), reverse("census"),
                    reverse("authorization_list") + "?view=all", reverse("waitlist"), reverse("waitlist_create"),
                    reverse("audit_log"), reverse("authorization_create", args=[self.episode.pk])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_search_by_ssn(self):
        response = self.client.get(reverse("client_list") + "?q=123-45-6789")
        self.assertContains(response, "Person, Test")

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("client_list")).status_code, 302)

    def test_oca_only_for_its_funding_sources(self):
        auth = Authorization(episode=self.episode, funding_source=self.va, oca=self.oca)
        with self.assertRaises(ValidationError):
            auth.full_clean()
        Authorization(episode=self.episode, funding_source=self.sfbhn, oca=self.oca).full_clean()

    def test_waitlist_add_and_admit(self):
        response = self.client.post(reverse("waitlist_create"), {
            "client-first_name": "New", "client-last_name": "Referral", "client-date_of_birth": "1990-05-05",
            "entry-funding_source": self.sfbhn.pk, "entry-status": "waiting", "entry-date_added": date.today(),
        })
        self.assertEqual(response.status_code, 302)
        entry = WaitlistEntry.objects.get(client__last_name="Referral")
        response = self.client.post(reverse("waitlist_admit", args=[entry.pk]), {
            "funding_source": self.sfbhn.pk, "level_of_care": "residential", "admit_date": date.today(),
        })
        entry.refresh_from_db()
        self.assertEqual(entry.status, WaitlistEntry.Status.ADMITTED)
        self.assertTrue(entry.admitted_episode.is_active)

    def test_discharge_and_audit(self):
        self.client.post(reverse("episode_discharge", args=[self.episode.pk]), {
            "discharge_date": date.today(), "discharge_reason": "successful"})
        self.episode.refresh_from_db()
        self.assertEqual(self.episode.discharge_reason, "successful")
        self.assertTrue(AuditLog.objects.filter(action="update", model="episode", user=self.user).exists())


class SeedParsingTests(TestCase):
    def test_dates(self):
        self.assertEqual(to_date("12/21/1950"), date(1950, 12, 21))
        self.assertEqual(to_date(43795), date(2019, 11, 26))
        self.assertIsNone(to_date("TBD"))
        self.assertIsNone(to_date("1900-02-28"))

    def test_names(self):
        self.assertEqual(split_name("Pierre Massey.3"), ("Pierre", "Massey"))
        self.assertEqual(split_name(" Cosby, Herschel"), ("Herschel", "Cosby"))

    def test_discharge_reasons(self):
        self.assertEqual(discharge_reason("Successfull"), DischargeReason.SUCCESSFUL)
        self.assertEqual(discharge_reason("", "Admin D/C - drug use"), DischargeReason.ADMIN)
        self.assertEqual(discharge_reason("D/C to HLC"), DischargeReason.HOSPITAL)
