from fastapi import APIRouter

from app.api.v1 import applications, auth, dev, inspections, land, misc, parcels, public, signals

api_router = APIRouter(prefix="/api/v1")
for module in (auth, parcels, signals, applications, inspections, land, misc, public, dev):
    api_router.include_router(module.router)
