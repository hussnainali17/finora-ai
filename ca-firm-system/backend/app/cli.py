"""Operator commands. There is deliberately no public sign-up or "first user" HTTP endpoint.

    python -m app.cli bootstrap-firm --firm-name "Acme & Co" --slug acme \
        --admin-email admin@acme.example --admin-name "Ada Admin"

The admin password is read from the BOOTSTRAP_ADMIN_PASSWORD environment variable or, if unset,
prompted for without echo. It is never accepted as a command-line argument (shell history/ps).
"""

import argparse
import asyncio
import getpass
import os
import re
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import DomainValidationError
from app.core.permissions import FIRM_ADMIN
from app.core.security import hash_password, validate_password_strength
from app.db.session import get_engine, get_sessionmaker
from app.models import Firm, User
from app.services.audit import record_audit

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")


async def bootstrap_firm(
    *, firm_name: str, slug: str, admin_email: str, admin_name: str, password: str
) -> None:
    if not _SLUG.match(slug):
        raise SystemExit("slug must be 3-80 chars: lowercase letters, digits and hyphens")
    try:
        validate_password_strength(password)
    except DomainValidationError as exc:
        raise SystemExit(exc.detail) from exc
    async with get_sessionmaker()() as session:
        if await session.scalar(select(Firm).where(Firm.slug == slug)):
            raise SystemExit(f"A firm with slug '{slug}' already exists")
        firm = Firm(name=firm_name, slug=slug)
        session.add(firm)
        await session.flush()
        admin = User(
            firm_id=firm.id,
            email=admin_email.strip().lower(),
            full_name=admin_name,
            role_key=FIRM_ADMIN,
            password_hash=hash_password(password),
        )
        session.add(admin)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise SystemExit("A user with that email already exists") from None
        record_audit(
            session,
            action="firm.bootstrapped",
            actor_user_id=admin.id,
            actor_email=admin.email,
            firm_id=firm.id,
            target_type="firm",
            target_id=firm.id,
            metadata={"slug": slug, "via": "cli"},
        )
        await session.commit()
    await get_engine().dispose()
    print(f"Created firm '{firm_name}' with Firm Admin {admin_email}")  # noqa: T201


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("bootstrap-firm", help="Create a firm and its first Firm Admin")
    b.add_argument("--firm-name", required=True)
    b.add_argument("--slug", required=True)
    b.add_argument("--admin-email", required=True)
    b.add_argument("--admin-name", required=True)
    args = parser.parse_args(argv)

    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not password:
        if not sys.stdin.isatty():
            raise SystemExit("Set BOOTSTRAP_ADMIN_PASSWORD when running non-interactively")
        password = getpass.getpass("Admin password: ")
    asyncio.run(
        bootstrap_firm(
            firm_name=args.firm_name,
            slug=args.slug,
            admin_email=args.admin_email,
            admin_name=args.admin_name,
            password=password,
        )
    )


if __name__ == "__main__":
    main()
