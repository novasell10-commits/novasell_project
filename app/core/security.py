from fastapi import Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()


def get_current_merchant(
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    # ⚠️ On ne vérifie PAS ici (ton middleware le fait déjà)
    return credentials.credentials