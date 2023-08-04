import urllib.parse

BASE_URI = "http://127.0.0.1:5000"
REDIRECT_URI = f"{BASE_URI}/callback/google"

GOOGLE_CLIENT_ID = (
    "881365933465-8p88663jo662djd5kllfc0sudnq6lclj.apps.googleusercontent.com"
)
GOOGLE_CLIENT_SECRET = "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"


def get_google_oauth_url(redirect: str = "") -> str:
    root_url = "https://accounts.google.com/o/oauth2/v2/auth"

    options = {
        "redirect_uri": REDIRECT_URI
        if redirect == ""
        else f"{REDIRECT_URI}?redirect={redirect}",
        "client_id": GOOGLE_CLIENT_ID,
        "access_type": "offline",
        "response_type": "code",
        "prompt": "consent",
        "scope": "https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email",
    }

    qs = urllib.parse.urlencode(options)

    return f"{root_url}?{qs}"
