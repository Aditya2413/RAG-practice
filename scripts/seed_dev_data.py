"""
Seed development data: 1 SUPER_ADMIN + 2 tenants with CLIENT_ADMIN + CLIENT_USER each.

Usage:
    python scripts/seed_dev_data.py
"""
import asyncio
import sys
from pathlib import Path

# Allow imports from src/ when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.security import hash_password
from src.infrastructure.database.postgres.connection import AsyncSessionLocal
from src.infrastructure.repositories.tenant_repository import TenantRepository
from src.infrastructure.repositories.user_repository import UserRepository

TENANTS = [
    {"name": "Acme Legal", "slug": "acme", "plan": "professional"},
    {"name": "TechCorp", "slug": "techcorp", "plan": "starter"},
]

SUPER_ADMIN = {
    "email": "super@admin.com",
    "password": "admin123",
    "role": "SUPER_ADMIN",
    "first_name": "Super",
    "last_name": "Admin",
}


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        tenant_repo = TenantRepository(session)
        user_repo = UserRepository(session)

        created_tenants = []
        for t_data in TENANTS:
            existing = await tenant_repo.find_by_slug(t_data["slug"])
            if existing:
                print(f"  [skip] Tenant '{t_data['slug']}' already exists.")
                created_tenants.append(existing)
                continue
            tenant = await tenant_repo.create(t_data)
            print(f"  [ok]   Created tenant: {tenant.name} (id={tenant.id})")
            created_tenants.append(tenant)

        # SUPER_ADMIN is associated with the first tenant for FK requirement
        first_tenant = created_tenants[0]
        existing_super = await user_repo.find_by_email_and_tenant(
            SUPER_ADMIN["email"], first_tenant.id
        )
        if existing_super:
            print(f"  [skip] SUPER_ADMIN '{SUPER_ADMIN['email']}' already exists.")
        else:
            await user_repo.create({
                "tenant_id": first_tenant.id,
                "email": SUPER_ADMIN["email"],
                "password_hash": hash_password(SUPER_ADMIN["password"]),
                "role": SUPER_ADMIN["role"],
                "first_name": SUPER_ADMIN["first_name"],
                "last_name": SUPER_ADMIN["last_name"],
            })
            print(f"  [ok]   Created SUPER_ADMIN: {SUPER_ADMIN['email']} / {SUPER_ADMIN['password']}")

        for tenant in created_tenants:
            slug = tenant.slug
            admin_email = f"admin@{slug}.com"
            user_email = f"user@{slug}.com"
            password = "test123"

            existing_admin = await user_repo.find_by_email_and_tenant(admin_email, tenant.id)
            if existing_admin:
                print(f"  [skip] CLIENT_ADMIN '{admin_email}' already exists.")
            else:
                await user_repo.create({
                    "tenant_id": tenant.id,
                    "email": admin_email,
                    "password_hash": hash_password(password),
                    "role": "CLIENT_ADMIN",
                    "first_name": "Admin",
                    "last_name": slug.capitalize(),
                })
                print(f"  [ok]   Created CLIENT_ADMIN: {admin_email} / {password}")

            existing_user = await user_repo.find_by_email_and_tenant(user_email, tenant.id)
            if existing_user:
                print(f"  [skip] CLIENT_USER '{user_email}' already exists.")
            else:
                await user_repo.create({
                    "tenant_id": tenant.id,
                    "email": user_email,
                    "password_hash": hash_password(password),
                    "role": "CLIENT_USER",
                    "first_name": "User",
                    "last_name": slug.capitalize(),
                })
                print(f"  [ok]   Created CLIENT_USER: {user_email} / {password}")

    print("\nSeed complete.")
    print("\nCredentials summary:")
    print(f"  SUPER_ADMIN  : {SUPER_ADMIN['email']} / {SUPER_ADMIN['password']}")
    for t_data in TENANTS:
        print(f"  CLIENT_ADMIN : admin@{t_data['slug']}.com / test123  (tenant: {t_data['slug']})")
        print(f"  CLIENT_USER  : user@{t_data['slug']}.com  / test123  (tenant: {t_data['slug']})")


if __name__ == "__main__":
    asyncio.run(seed())
