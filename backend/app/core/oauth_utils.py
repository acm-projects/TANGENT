"""
Tangent — oauth_utils.py
"""

import os
import secrets
import base64
import hashlib
from typing import Dict, Any
import httpx
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidSignatureError, InvalidTokenError

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

BACKEND_URL = (
    os.getenv("BACKEND_URL")
    if os.getenv("IS_PRODUCTION") == "1"
    else "http://localhost:8000"
)

GOOGLE_REDIRECT_URI = f"{BACKEND_URL}/auth/callback/google"
GOOGLE_REAUTH_REDIRECT_URI = f"{BACKEND_URL}/auth/callback/reauth/google"


def generate_state_token() -> str:
    """Generates a cryptographically secure pseudo-random string to mitigate CSRF attacks."""
    return secrets.token_urlsafe(32)


def generate_pkce_pair() -> tuple[str, str]:
    """Generates a secure PKCE code_verifier and code_challenge."""
    verifier_bytes = os.urandom(32)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).decode("utf-8").rstrip("=")

    challenge_bytes = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")

    return code_verifier, code_challenge


# ==========================================
# GOOGLE OIDC METADATA & CRYPTO PROCESSING
# ==========================================

def get_google_auth_url(state: str, code_challenge: str, redirect_uri: str = GOOGLE_REDIRECT_URI) -> str:
    """Constructs the raw initiation URL for the Google OIDC consent screen with PKCE."""
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{base_url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"


async def verify_google_id_token(id_token: str) -> Dict[str, Any]:
    """
    Manually verifies Google's OIDC ID token JWT by fetching Google's live
    JWKS and checking the RSA signature — same approach as the old app.
    """
    try:
        async with httpx.AsyncClient() as client:
            jwks_response = await client.get("https://www.googleapis.com/oauth2/v3/certs")
            jwks_response.raise_for_status()
            jwks = jwks_response.json()

        unverified_header = jwt.get_unverified_header(id_token)
        kid = unverified_header.get("kid")

        if not kid:
            raise InvalidTokenError("Missing 'kid' claim in token header.")

        public_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                break

        if not public_key:
            raise InvalidTokenError("Public key matching 'kid' not found in Google's JWKS.")

        decoded_token = jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=GOOGLE_CLIENT_ID,
            issuer="https://accounts.google.com",
        )
        return decoded_token

    except ExpiredSignatureError:
        raise ValueError("The Google identity token has expired.")
    except (InvalidSignatureError, InvalidTokenError) as e:
        raise ValueError(f"Cryptographic signature check failed: {str(e)}")


async def exchange_google_code_for_tokens(code: str, code_verifier: str, redirect_uri: str = GOOGLE_REDIRECT_URI) -> Dict[str, Any]:
    """Back-channel POST to exchange the auth code for tokens using PKCE."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        response.raise_for_status()
        return response.json()