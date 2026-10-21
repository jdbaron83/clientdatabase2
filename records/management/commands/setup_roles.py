"""Create the standard staff groups and their permissions. Safe to run more than once."""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

VIEW_ALL = ["view_client", "view_episode", "view_authorization", "view_waitlistentry", "view_medication",
            "view_fundingsource", "view_oca"]

ROLES = {
    "Intake": VIEW_ALL + ["add_client", "change_client", "add_episode", "change_episode",
                          "add_waitlistentry", "change_waitlistentry", "add_medication", "change_medication"],
    "Billing": VIEW_ALL + ["add_authorization", "change_authorization"],
    "Supervisor": VIEW_ALL + [
        "add_client", "change_client", "add_episode", "change_episode", "add_waitlistentry",
        "change_waitlistentry", "add_medication", "change_medication", "add_authorization",
        "change_authorization", "add_fundingsource", "change_fundingsource", "add_oca", "change_oca",
        "view_full_ssn", "view_auditlog",
    ],
}


class Command(BaseCommand):
    help = "Create the Intake, Billing and Supervisor groups."

    def handle(self, **options):
        for name, codenames in ROLES.items():
            group, _ = Group.objects.get_or_create(name=name)
            perms = Permission.objects.filter(content_type__app_label="records", codename__in=codenames)
            missing = set(codenames) - set(perms.values_list("codename", flat=True))
            if missing:
                self.stderr.write(f"{name}: unknown permissions {sorted(missing)}")
            group.permissions.set(perms)
            self.stdout.write(f"{name}: {perms.count()} permissions")
        self.stdout.write(self.style.SUCCESS("Roles are set up. Add people to a group in Admin > Users."))
