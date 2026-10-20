import re
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from . import audit, crypto
from .forms import (AuthorizationForm, ClientForm, DischargeForm, EpisodeForm, MedicationForm,
                    NewWaitlistClientForm, WaitlistAdmitForm, WaitlistCloseForm, WaitlistEntryForm)
from .models import Authorization, AuditLog, Client, Episode, FundingSource, WaitlistEntry

EXPIRING_DAYS = 14


@login_required
def dashboard(request):
    today = date.today()
    active = Episode.objects.active()
    census = (active.values("funding_source__name", "funding_source__level_of_care", "funding_source__bed_capacity")
              .annotate(n=Count("id")).order_by("funding_source__level_of_care", "funding_source__name"))
    expiring = (Authorization.objects.filter(episode__discharge_date__isnull=True, end_date__gte=today,
                                             end_date__lte=today + timedelta(days=EXPIRING_DAYS))
                .select_related("episode__client", "funding_source").order_by("end_date"))
    needs_auth = (Authorization.objects.filter(episode__discharge_date__isnull=True, auth_number="")
                  .select_related("episode__client", "funding_source"))
    return render(request, "records/dashboard.html", {
        "census": census,
        "active_total": active.count(),
        "residential_total": active.filter(level_of_care="residential").count(),
        "waiting_total": WaitlistEntry.objects.filter(status=WaitlistEntry.Status.WAITING).count(),
        "expiring": expiring,
        "needs_auth": needs_auth,
        "recent_admits": Episode.objects.filter(admit_date__gte=today - timedelta(days=14))
                                        .select_related("client", "funding_source")[:15],
        "recent_discharges": Episode.objects.filter(discharge_date__gte=today - timedelta(days=14))
                                            .select_related("client", "funding_source")
                                            .order_by("-discharge_date")[:15],
    })


def _client_search(q):
    qs = Client.objects.all()
    if not q:
        return qs
    digits = re.sub(r"\D", "", q)
    if len(digits) == 9:
        return qs.filter(ssn_hash=crypto.ssn_hash(crypto.normalize_ssn(digits)))
    if len(digits) == 4 and digits == q.strip():
        return qs.filter(ssn_last4=digits)
    # Every word must match part of the name, or the whole query starts a record ID.
    name_cond = Q()
    for term in q.split():
        name_cond &= Q(first_name__icontains=term) | Q(last_name__icontains=term)
    return qs.filter(name_cond | Q(episodes__record_id__istartswith=q.strip())).distinct()


@login_required
def client_list(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    qs = _client_search(q)
    if status == "active":
        qs = qs.filter(episodes__discharge_date__isnull=True).distinct()
    qs = qs.annotate(episode_count=Count("episodes", distinct=True))
    page = Paginator(qs.order_by("last_name", "first_name"), 50).get_page(request.GET.get("page"))
    return render(request, "records/client_list.html", {"page": page, "q": q, "status": status})


@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    audit.log("view", client)
    episodes = client.episodes.select_related("funding_source").prefetch_related(
        "authorizations__funding_source", "authorizations__oca", "medications")
    show_ssn = request.GET.get("ssn") == "1" and request.user.has_perm("records.view_full_ssn")
    if show_ssn:
        audit.log("view", client, {"ssn": "full SSN shown"})
    return render(request, "records/client_detail.html", {
        "client": client,
        "episodes": episodes,
        "waitlist": client.waitlist_entries.select_related("funding_source"),
        "show_ssn": show_ssn,
        "can_view_ssn": request.user.has_perm("records.view_full_ssn"),
    })


@login_required
@permission_required("records.add_client", raise_exception=True)
def client_create(request):
    form = ClientForm(request.POST or None)
    if form.is_valid():
        client = form.save()
        messages.success(request, f"Added {client}.")
        return redirect(client)
    return render(request, "records/form.html", {"form": form, "title": "New client"})


@login_required
@permission_required("records.change_client", raise_exception=True)
def client_update(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if form.is_valid():
        form.save()
        messages.success(request, "Client updated.")
        return redirect(client)
    return render(request, "records/form.html", {"form": form, "title": f"Edit {client}", "back": client.get_absolute_url()})


@login_required
@permission_required("records.add_episode", raise_exception=True)
def episode_create(request, client_pk):
    client = get_object_or_404(Client, pk=client_pk)
    form = EpisodeForm(request.POST or None, initial={"admit_date": date.today()})
    if form.is_valid():
        episode = form.save(commit=False)
        episode.client = client
        episode.save()
        messages.success(request, "Admission added.")
        return redirect(episode)
    return render(request, "records/form.html", {"form": form, "title": f"New admission for {client}",
                                                 "back": client.get_absolute_url()})


@login_required
def episode_detail(request, pk):
    episode = get_object_or_404(Episode.objects.select_related("client", "funding_source"), pk=pk)
    audit.log("view", episode)
    return render(request, "records/episode_detail.html", {
        "episode": episode,
        "authorizations": episode.authorizations.select_related("funding_source", "oca"),
        "medications": episode.medications.all(),
    })


@login_required
@permission_required("records.change_episode", raise_exception=True)
def episode_update(request, pk):
    episode = get_object_or_404(Episode, pk=pk)
    form = EpisodeForm(request.POST or None, instance=episode)
    if form.is_valid():
        form.save()
        messages.success(request, "Admission updated.")
        return redirect(episode)
    return render(request, "records/form.html", {"form": form, "title": f"Edit admission: {episode}",
                                                 "back": episode.get_absolute_url()})


@login_required
@permission_required("records.change_episode", raise_exception=True)
def episode_discharge(request, pk):
    episode = get_object_or_404(Episode, pk=pk)
    form = DischargeForm(request.POST or None, instance=episode, initial={"discharge_date": date.today()})
    if form.is_valid():
        form.save()
        messages.success(request, f"{episode.client} discharged.")
        return redirect(episode)
    return render(request, "records/form.html", {"form": form, "title": f"Discharge {episode.client}",
                                                 "back": episode.get_absolute_url()})


@login_required
@permission_required("records.add_authorization", raise_exception=True)
def authorization_create(request, episode_pk):
    episode = get_object_or_404(Episode, pk=episode_pk)
    form = AuthorizationForm(request.POST or None,
                             initial={"funding_source": episode.funding_source, "start_date": date.today()})
    if form.is_valid():
        auth = form.save(commit=False)
        auth.episode = episode
        auth.save()
        messages.success(request, "Authorization added.")
        return redirect(episode)
    return render(request, "records/form.html", {"form": form, "title": f"New authorization for {episode.client}",
                                                 "back": episode.get_absolute_url()})


@login_required
@permission_required("records.change_authorization", raise_exception=True)
def authorization_update(request, pk):
    auth = get_object_or_404(Authorization, pk=pk)
    form = AuthorizationForm(request.POST or None, instance=auth)
    if form.is_valid():
        form.save()
        messages.success(request, "Authorization updated.")
        return redirect(auth.episode)
    return render(request, "records/form.html", {"form": form, "title": "Edit authorization",
                                                 "back": auth.episode.get_absolute_url()})


@login_required
def authorization_list(request):
    today = date.today()
    view = request.GET.get("view", "expiring")
    qs = Authorization.objects.filter(episode__discharge_date__isnull=True).select_related(
        "episode__client", "funding_source", "oca")
    if view == "expiring":
        qs = qs.filter(end_date__lte=today + timedelta(days=EXPIRING_DAYS)).exclude(auth_number="")
    elif view == "needed":
        qs = qs.filter(auth_number="")
    return render(request, "records/authorization_list.html", {"auths": qs.order_by("end_date"), "view": view})


@login_required
@permission_required("records.add_medication", raise_exception=True)
def medication_create(request, episode_pk):
    episode = get_object_or_404(Episode, pk=episode_pk)
    form = MedicationForm(request.POST or None)
    if form.is_valid():
        med = form.save(commit=False)
        med.episode = episode
        med.save()
        messages.success(request, "Medication added.")
        return redirect(episode)
    return render(request, "records/form.html", {"form": form, "title": f"New MAT medication for {episode.client}",
                                                 "back": episode.get_absolute_url()})


@login_required
def census(request):
    funding = request.GET.get("funding", "")
    qs = Episode.objects.active().select_related("client", "funding_source")
    if funding:
        qs = qs.filter(funding_source_id=funding)
    return render(request, "records/census.html", {
        "episodes": qs.order_by("funding_source__name", "bed", "client__last_name"),
        "funding_sources": FundingSource.objects.filter(episodes__discharge_date__isnull=True).distinct(),
        "funding": funding,
    })


@login_required
def waitlist(request):
    status = request.GET.get("status", WaitlistEntry.Status.WAITING)
    funding = request.GET.get("funding", "")
    qs = WaitlistEntry.objects.select_related("client", "funding_source")
    if status != "all":
        qs = qs.filter(status=status)
    if funding:
        qs = qs.filter(funding_source_id=funding)
    page = Paginator(qs.order_by("rank", "date_added"), 50).get_page(request.GET.get("page"))
    return render(request, "records/waitlist.html", {
        "page": page, "status": status, "funding": funding,
        "statuses": WaitlistEntry.Status.choices,
        "funding_sources": FundingSource.objects.filter(waitlist_entries__isnull=False).distinct(),
    })


@login_required
@permission_required("records.add_waitlistentry", raise_exception=True)
def waitlist_create(request):
    client = None
    if request.GET.get("client"):
        client = get_object_or_404(Client, pk=request.GET["client"])
    entry_form = WaitlistEntryForm(request.POST or None, prefix="entry", initial={"date_added": date.today()})
    client_form = None if client else NewWaitlistClientForm(request.POST or None, prefix="client")
    if request.method == "POST" and entry_form.is_valid() and (client or client_form.is_valid()):
        with transaction.atomic():
            entry = entry_form.save(commit=False)
            entry.client = client or client_form.find_or_create_client()
            entry.save()
        messages.success(request, f"{entry.client} added to the waitlist.")
        return redirect("waitlist")
    return render(request, "records/waitlist_form.html", {"entry_form": entry_form, "client_form": client_form,
                                                          "client": client})


@login_required
@permission_required("records.change_waitlistentry", raise_exception=True)
def waitlist_update(request, pk):
    entry = get_object_or_404(WaitlistEntry, pk=pk)
    form = WaitlistEntryForm(request.POST or None, instance=entry)
    if form.is_valid():
        form.save()
        messages.success(request, "Waitlist entry updated.")
        return redirect("waitlist")
    return render(request, "records/form.html", {"form": form, "title": f"Edit waitlist entry: {entry.client}"})


@login_required
@permission_required("records.add_episode", raise_exception=True)
def waitlist_admit(request, pk):
    entry = get_object_or_404(WaitlistEntry, pk=pk, admitted_episode__isnull=True)
    form = WaitlistAdmitForm(request.POST or None, initial={
        "funding_source": entry.funding_source,
        "level_of_care": entry.funding_source.level_of_care if entry.funding_source else "residential",
        "admit_date": date.today(),
    })
    if form.is_valid():
        with transaction.atomic():
            episode = form.save(commit=False)
            episode.client = entry.client
            episode.secondary_funding = entry.secondary_funding
            episode.save()
            entry.status = WaitlistEntry.Status.ADMITTED
            entry.admitted_episode = episode
            entry.closed_date = episode.admit_date
            entry.save()
        messages.success(request, f"{entry.client} admitted from the waitlist.")
        return redirect(episode)
    return render(request, "records/form.html", {"form": form, "title": f"Admit {entry.client} from the waitlist",
                                                 "back": "/waitlist/"})


@login_required
@permission_required("records.change_waitlistentry", raise_exception=True)
def waitlist_close(request, pk):
    entry = get_object_or_404(WaitlistEntry, pk=pk)
    form = WaitlistCloseForm(request.POST or None)
    if form.is_valid():
        entry.status = form.cleaned_data["status"]
        entry.closed_reason = form.cleaned_data["reason"]
        entry.closed_date = date.today() if entry.status == WaitlistEntry.Status.DECLINED else None
        entry.save()
        messages.success(request, "Waitlist entry updated.")
        return redirect("waitlist")
    return render(request, "records/form.html", {"form": form, "title": f"Remove or hold {entry.client}",
                                                 "back": "/waitlist/"})


@login_required
@permission_required("records.view_auditlog", raise_exception=True)
def audit_log(request):
    page = Paginator(AuditLog.objects.select_related("user"), 100).get_page(request.GET.get("page"))
    return render(request, "records/audit_log.html", {"page": page})
