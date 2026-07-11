from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Lead


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def claim_leads_for_user(sender, instance, **kwargs):
    """Links any unassigned leads whose owner_email matches this account.

    This is what makes import order not matter. A CSV can be imported naming
    surrender@prepnxt.com as the owner before that account exists — the lead
    lands unassigned, but its owner_email is preserved. The moment the account
    is created (or has its email corrected), this fires and hands the leads
    over.

    Fires on every User save, not just creation, so fixing a typo in an email
    address also re-links correctly.

    Deliberately only touches leads with owner_user IS NULL — an already-owned
    lead is never silently reassigned, even if two accounts somehow share an
    email.
    """
    email = (instance.email or "").strip()
    if not email:
        return

    claimed = Lead.objects.filter(
        owner_user__isnull=True,
        owner_email__iexact=email,
    ).update(owner_user=instance)

    if claimed:
        # Visible in runserver output / the PythonAnywhere server log, so an
        # admin creating an account can see it took effect.
        print(f"[leads] Claimed {claimed} lead(s) for {instance.username} <{email}>")