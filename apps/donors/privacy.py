import re


def public_username(user):
    """Preserve account handles without disclosing email/phone login names."""
    username = user.username
    if user.role == "DONOR" and (
        "@" in username or re.fullmatch(r"[+\d\s().-]+", username)
    ):
        return f"Donor #{user.pk}"
    return username
