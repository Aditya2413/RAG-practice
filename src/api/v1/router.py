from fastapi import APIRouter

from src.api.v1.routers import auth, collections, health, tenants

v1_router = APIRouter()

v1_router.include_router(health.router)
v1_router.include_router(auth.router)
v1_router.include_router(tenants.router)
v1_router.include_router(collections.router)
