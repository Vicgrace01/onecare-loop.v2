from fastapi import APIRouter

from app.api.v1 import audit, auth, communications, demo, fhir, followups, health, hospital, metrics, organisations, patients, referrals, screening

api_router = APIRouter()
for module in [health, auth, audit, organisations, screening, referrals, hospital, patients, followups, communications, fhir, metrics, demo]:
    api_router.include_router(module.router)
