"""Operator CLI for self-hosted installs (no email service needed).

    python -m app.cli create-user EMAIL NAME --workspace "Acme"     # prompts for a password
    python -m app.cli reset-password EMAIL                          # prompts; signs the user out everywhere
    python -m app.cli list-users
    python -m app.cli setup-free                                    # free providers + starter agents everywhere

In Docker:  docker compose exec api python -m app.cli reset-password someone@example.com
"""
import argparse
import asyncio
import getpass
import sys

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.client import close_client, get_db
from app.db.indexes import ensure_schema
from app.repositories.identity import SessionRepository, UserRepository, WorkspaceRepository
from app.schemas.auth import RegisterRequest
from app.services.auth import AuthService
from app.services.providers import ProviderService

MIN_PASSWORD = 12


def _password(arg: str | None) -> str:
    pw = arg or getpass.getpass("New password: ")
    if not arg and pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match")
    if len(pw) < MIN_PASSWORD:
        sys.exit(f"Password must be at least {MIN_PASSWORD} characters")
    return pw


async def create_user(email: str, name: str, workspace: str, password: str | None) -> None:
    db = get_db()
    get_settings().allow_registration = True  # operators may always create accounts
    req = RegisterRequest(email=email, name=name, workspace_name=workspace, password=_password(password))
    user, _ = await AuthService(db).register(req, ip="cli")
    for m in await WorkspaceRepository(db).memberships_for(user["_id"]):
        await ProviderService(db).ensure_demo(m["workspace_id"])
    print(f"Created {user['email']} ({user['_id']}) as owner of workspace '{workspace}'")


async def reset_password(email: str, password: str | None) -> None:
    db = get_db()
    users = UserRepository(db)
    user = await users.by_email(email)
    if not user:
        sys.exit(f"No user with email {email}")
    await users.set_password(user["_id"], hash_password(_password(password)))
    await SessionRepository(db).delete_for_user(user["_id"])
    print(f"Password reset for {user['email']}; all their sessions were signed out")


async def list_users() -> None:
    async for u in get_db()["users"].find({}, {"email": 1, "name": 1, "created_at": 1}).sort("created_at", 1):
        print(f"{u['_id']}\t{u['email']}\t{u['name']}\t{u['created_at']:%Y-%m-%d}")


async def setup_free() -> None:
    """Adds the free providers configured in .env and the starter agents to every workspace."""
    from app.services.starter_agents import StarterAgentService

    db = get_db()
    async for ws in db["workspaces"].find({}, {"name": 1, "owner_id": 1}):
        r = await StarterAgentService(db).install(ws["_id"], ws["owner_id"])
        print(f"{ws['name']}: created {len(r['created'])}, updated {len(r['updated'])}, "
              f"skipped {len(r['skipped'])}")


async def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user", help="create an account and its own workspace")
    c.add_argument("email")
    c.add_argument("name")
    c.add_argument("--workspace", default="Default")
    c.add_argument("--password", help="non-interactive (avoid: ends up in shell history)")
    r = sub.add_parser("reset-password", help="set a new password and sign the user out everywhere")
    r.add_argument("email")
    r.add_argument("--password", help="non-interactive (avoid: ends up in shell history)")
    sub.add_parser("list-users")
    sub.add_parser("setup-free", help="add free providers from .env and starter agents to every workspace")
    a = p.parse_args(argv)
    await ensure_schema(get_db())
    try:
        if a.cmd == "create-user":
            await create_user(a.email, a.name, a.workspace, a.password)
        elif a.cmd == "reset-password":
            await reset_password(a.email, a.password)
        elif a.cmd == "setup-free":
            await setup_free()
        else:
            await list_users()
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
