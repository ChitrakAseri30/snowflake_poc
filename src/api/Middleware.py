import os
import sys
import time
import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import src.utils.Constants as CONSTANT
from src.utils.LogSetup import get_logger

logger = get_logger()

security = HTTPBearer()


# ==========================================
# AUTH0 KEY CACHING
# ==========================================
# Caching the keys prevents network latency and rate-limiting on every single API call
_jwks_cache = None
_jwks_cache_time = 0


def _get_jwks() -> dict:
    """
    Purpose: Fetches and caches the JSON Web Key Set from Auth0 securely.
    Args: None
    Returns: dict containing the Auth0 public keys.
    Raises: HTTPException if the Auth0 server is unreachable.
    """
    global _jwks_cache, _jwks_cache_time
    
    # Return cached keys if they are still fresh
    if _jwks_cache and (time.time() - _jwks_cache_time < CONSTANT.JWKS_CACHE_TTL):
        return _jwks_cache
        
    jwks_url = f'https://{CONSTANT.AUTH0_DOMAIN}/.well-known/jwks.json'
    
    try:
        logger.debug(f"Fetching fresh JWKS from {jwks_url}")
        response = httpx.get(jwks_url, timeout=10.0)
        response.raise_for_status()
        
        _jwks_cache = response.json()
        _jwks_cache_time = time.time()
        return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS from Auth0: {e}", exc_info=True)
        # We raise a 500 here because if Auth0 is down, it's a server issue, not a user issue
        raise HTTPException(status_code=500, detail="Internal authentication service unavailable.")


# ==========================================
# MIDDLEWARE VALIDATION
# ==========================================
def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Purpose: Validates an incoming JWT against the Auth0 public keys.
    Args:
        credentials (HTTPAuthorizationCredentials): The bearer token extracted from the Authorization header.
    Returns: dict containing the decoded token payload if valid.
    Raises: HTTPException (401) if the token is invalid, expired, or missing.
    """

    token = credentials.credentials

    try:
        jwks = _get_jwks()
        unverified_header = jwt.get_unverified_header(token)
        
        # Match the Key ID (kid) from the token with the keys from Auth0
        rsa_key = {}
        for key in jwks.get("keys", []):
            if key["kid"] == unverified_header.get("kid"):
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
                break

        if rsa_key:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience=CONSTANT.API_AUDIENCE,
                issuer=f'https://{CONSTANT.AUTH0_DOMAIN}/'
            )
            return payload
        
        # If we loop through and find no matching key
        logger.warning("JWT Verification Failed: Unable to find appropriate RSA key.")
        raise HTTPException(status_code=401, detail="Unable to verify credentials")
    
    except ExpiredSignatureError:
        # Specific catch for expired tokens (forces the user to log in again cleanly)
        logger.warning("JWT Verification Failed: Token has expired.")
        raise HTTPException(status_code=401, detail="Token has expired. Please log in again.")
        
    except JWTError as e:
        # General catch for malformed or tampered tokens
        logger.warning(f"JWT Verification Failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token.")
        
    except HTTPException:
        # Re-raise HTTPExceptions (like the 500 from _get_jwks) so they aren't swallowed
        raise
        
    except Exception as e:
        # Absolute safety net: Log the raw error, but return a generic 401 to the frontend
        logger.error(f"Unexpected error during JWT verification: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication failed due to an unexpected error.")