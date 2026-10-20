"""Audit trail: records who created, changed, deleted or viewed client data."""

import contextvars
from contextlib import contextmanager

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

_current_user = contextvars.ContextVar("current_user", default=None)
_suspended = contextvars.ContextVar("audit_suspended", default=False)

SENSITIVE_FIELDS = {"ssn_encrypted", "ssn_hash", "ssn_last4"}
IGNORED_FIELDS = {"created_at", "updated_at"}


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        token = _current_user.set(user)
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token)


@contextmanager
def suspended():
    """Turn off audit logging, e.g. for the bulk seed import."""
    token = _suspended.set(True)
    try:
        yield
    finally:
        _suspended.reset(token)


def log(action, instance, changes=None, user=None):
    from .models import AuditLog

    if _suspended.get():
        return
    AuditLog.objects.create(
        user=user or _current_user.get(),
        action=action,
        model=instance._meta.model_name,
        object_id=str(instance.pk),
        object_repr=str(instance)[:200],
        changes=changes or {},
    )


def _audited(sender):
    from . import models

    return sender in (models.Client, models.Episode, models.Authorization, models.WaitlistEntry,
                      models.Medication, models.FundingSource, models.Oca)


def _field_values(instance):
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in IGNORED_FIELDS:
            continue
        values[field.name] = field.value_from_object(instance)
    return values


@receiver(pre_save)
def _remember_old(sender, instance, **kwargs):
    if _suspended.get() or not _audited(sender) or not instance.pk:
        return
    old = sender.objects.filter(pk=instance.pk).first()
    instance._audit_old = _field_values(old) if old else None


@receiver(post_save)
def _log_save(sender, instance, created, **kwargs):
    if _suspended.get() or not _audited(sender):
        return
    new = _field_values(instance)
    if created:
        log("create", instance)
        return
    old = getattr(instance, "_audit_old", None) or {}
    changes = {}
    for name, value in new.items():
        if old.get(name) != value:
            if name in SENSITIVE_FIELDS:
                changes["ssn"] = "changed"
            else:
                changes[name] = [_jsonable(old.get(name)), _jsonable(value)]
    if changes:
        log("update", instance, changes)


@receiver(post_delete)
def _log_delete(sender, instance, **kwargs):
    if _suspended.get() or not _audited(sender):
        return
    log("delete", instance)


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
