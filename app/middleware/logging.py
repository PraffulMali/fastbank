import time
import logging
from fastapi import Request

from app.utils.jwt import decode_access_token

logger = logging.getLogger(__name__)

async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    tenant_id = "N/A"
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        payload = decode_access_token(token)
        if payload:
            tenant_id = payload.get("tenant_id", "N/A")
    
    if tenant_id == "N/A":
        tenant_id = request.headers.get("X-Tenant-ID", "N/A")

    logger.info(f"Incoming Request - TenantID={tenant_id} | Method={request.method} | Path={request.url.path}")

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(f"Unhandled exception occurred - TenantID={tenant_id}")
        raise

    process_time = time.time() - start_time

    logger.info(
        f"Completed Response - TenantID={tenant_id} | "
        f"Status={response.status_code} | "
        f"Time={process_time:.4f}s"
    )

    return response
