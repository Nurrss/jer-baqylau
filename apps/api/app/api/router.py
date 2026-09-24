from fastapi import APIRouter

from app.api.v1 import applications, auth, dev, misc, parcels, signals

api_router = APIRouter(prefix="/api/v1")
for module in (auth, parcels, signals, applications, misc, dev):
    api_router.include_router(module.router)
