import re

from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Lead


def user_payload(user):
    """The single shape every auth endpoint returns, so the frontend can't end
    up with an `isAdmin` on one and not the other.

    `isAdmin` combines is_superuser and is_staff on purpose — it mirrors
    exactly what `is_admin()` in views.py uses to decide row-level access, so
    what the UI shows and what the API allows can never drift apart.
    """
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "fullName": (user.get_full_name() or "").strip(),
        "isStaff": user.is_staff,
        "isSuperuser": user.is_superuser,
        "isAdmin": user.is_superuser or user.is_staff,
    }


def derive_username(email):
    """Users log in with email, so the username is an internal detail — but
    Django still requires one and requires it unique. Derived from the email's
    local part, stripped to legal characters, and suffixed if taken.
    """
    User = get_user_model()
    base = re.sub(r"[^\w.@+-]", "", email.split("@")[0]) or "user"
    base = base[:140]
    candidate = base
    n = 1
    while User.objects.filter(username__iexact=candidate).exists():
        n += 1
        candidate = f"{base}{n}"
    return candidate


class LoginView(APIView):
    """
    POST /api/auth/login/
    Body: {"email": "...", "password": "..."}

    Login is by EMAIL, not username — email is already the identity that ties a
    person to their leads (the CSV's Owner Email column), so making them
    remember a separate username was a pointless second identifier.

    Django's `authenticate()` still works on username under the hood, so the
    email is resolved to an account first. `username` is also accepted in the
    body for backwards compatibility with any older client still posting it.

    No self-signup — accounts are created by an admin via CreateUserView below.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        password = request.data.get("password") or ""
        legacy_username = (request.data.get("username") or "").strip()

        identifier = email or legacy_username

        if not identifier or not password:
            return Response(
                {"detail": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = None

        if email:
            User = get_user_model()
            # iexact, because nobody types their email with consistent casing.
            # Django doesn't enforce email uniqueness, so try each match rather
            # than picking one arbitrarily and rejecting a valid password.
            for candidate in User.objects.filter(email__iexact=email):
                user = authenticate(
                    request, username=candidate.username, password=password
                )
                if user:
                    break
        else:
            user = authenticate(request, username=legacy_username, password=password)

        if user is None:
            # Deliberately the same message whether the account doesn't exist
            # or the password is wrong — anything more specific tells an
            # attacker which emails are registered.
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return Response(
                {"detail": "This account is inactive."},
                status=status.HTTP_403_FORBIDDEN,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, **user_payload(user)})


class LogoutView(APIView):
    """POST /api/auth/logout/ — deletes the token server-side, so it can't
    be reused even if it leaked (e.g. left in browser history/devtools)."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.auth_token.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/auth/me/ — lets the frontend validate a stored token on app
    load, and tells it whether this user is an admin so the UI can hide what
    they can't use."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_payload(request.user))


class UserListCreateView(APIView):
    """
    GET  /api/auth/users/  — list all accounts (admin only)
    POST /api/auth/users/  — create a SPOC account (admin only)
         Body: {"fullName": "...", "email": "...", "password": "...",
                "isAdmin": false}

    IsAdminUser checks is_staff — the same flag `is_admin()` in views.py uses,
    so a user who can reach this endpoint is exactly a user who can already see
    every lead. There's no privilege gap between the two.

    Creating a user fires the post_save signal in signals.py, which claims any
    orphaned leads whose owner_email matches. The count comes back in the
    response so the admin sees it happened — that's the whole point of the
    email being the join key.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        User = get_user_model()
        users = User.objects.all().order_by("-is_superuser", "-is_staff", "username")
        return Response(
            [
                {
                    **user_payload(u),
                    "leadCount": Lead.objects.filter(owner_user=u).count(),
                }
                for u in users
            ]
        )

    def post(self, request):
        User = get_user_model()

        full_name = (request.data.get("fullName") or "").strip()
        email = (request.data.get("email") or "").strip()
        password = request.data.get("password") or ""
        make_admin = bool(request.data.get("isAdmin"))

        if not email or not password:
            return Response(
                {"detail": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"detail": "That doesn't look like a valid email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Email is the login identity AND the lead-ownership key, so a duplicate
        # would be genuinely ambiguous — reject it even though Django's User
        # model doesn't enforce uniqueness itself.
        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {"detail": "An account with that email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Length only. Django's full validator set (common-password lists,
        # numeric-only checks, similarity to the username) is deliberately NOT
        # run here — internal tool, admin-created accounts. The tradeoff is
        # that "password123" is now acceptable.
        #
        # This applies to THIS endpoint only. createsuperuser and the Django
        # admin still run AUTH_PASSWORD_VALIDATORS from settings.py, which is
        # where you want strictness kept: that's the account that sees every
        # lead.
        if len(password) < 8:
            return Response(
                {"detail": "Password must be at least 8 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        first_name, _, last_name = full_name.partition(" ")

        user = User.objects.create_user(
            username=derive_username(email),
            email=email,
            password=password,
            first_name=first_name[:150],
            last_name=last_name[:150],
        )

        # is_staff is what both IsAdminUser and views.is_admin() check, so
        # these two must be set together or an "admin" would see every lead but
        # be unable to import, or vice versa.
        if make_admin:
            user.is_staff = True
            user.is_superuser = True
            user.save()

        # The signal has already run by now (on create_user's save), so this is
        # just reading back what it did.
        claimed = Lead.objects.filter(owner_user=user).count()

        return Response(
            {**user_payload(user), "claimedLeads": claimed},
            status=status.HTTP_201_CREATED,
        )