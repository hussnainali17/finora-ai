"""One-shot script: enable gpt-6-luna model for the firm and set it as default for all agents.

Run from the backend directory:
    python scripts/seed_gpt6luna.py
"""

import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:ha4374177%40@localhost:5432/ca_firm_system"

FIRM_ID = "7c5f3de5-4fa3-4b78-8278-8a036bc13f5c"
ALIAS = "gpt-6-luna"
AGENTS = ["intake", "accounting_review", "adjustments", "reporting", "ca_review"]


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    sm: async_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sm() as session, session.begin():
        # ── 1. Enable gpt-6-luna model for the firm ─────────────────────────
        existing = await session.execute(
            text("SELECT id FROM llm_model_settings WHERE firm_id = :fid AND alias = :alias"),
            {"fid": FIRM_ID, "alias": ALIAS},
        )
        row = existing.fetchone()
        if row:
            await session.execute(
                text("UPDATE llm_model_settings SET enabled = true, updated_at = now() WHERE id = :id"),
                {"id": str(row[0])},
            )
            print(f"[✔] Updated existing llm_model_settings row for {ALIAS} → enabled=true")
        else:
            new_id = str(uuid.uuid4())
            await session.execute(
                text(
                    "INSERT INTO llm_model_settings (id, firm_id, alias, enabled, updated_at) "
                    "VALUES (:id, :fid, :alias, true, now())"
                ),
                {"id": new_id, "fid": FIRM_ID, "alias": ALIAS},
            )
            print(f"[✔] Inserted llm_model_settings row for {ALIAS} (id={new_id})")

        # ── 2. Set gpt-6-luna as default for every agent ────────────────────
        for agent in AGENTS:
            existing_cfg = await session.execute(
                text(
                    "SELECT id FROM llm_agent_configs WHERE firm_id = :fid AND agent = :agent"
                ),
                {"fid": FIRM_ID, "agent": agent},
            )
            cfg_row = existing_cfg.fetchone()
            if cfg_row:
                await session.execute(
                    text(
                        "UPDATE llm_agent_configs SET default_alias = :alias, updated_at = now() "
                        "WHERE id = :id"
                    ),
                    {"alias": ALIAS, "id": str(cfg_row[0])},
                )
                print(f"[✔] Updated llm_agent_configs for agent '{agent}' → default={ALIAS}")
            else:
                new_cfg_id = str(uuid.uuid4())
                await session.execute(
                    text(
                        "INSERT INTO llm_agent_configs "
                        "(id, firm_id, agent, default_alias, fallback_alias, updated_at) "
                        "VALUES (:id, :fid, :agent, :alias, NULL, now())"
                    ),
                    {"id": new_cfg_id, "fid": FIRM_ID, "agent": agent, "alias": ALIAS},
                )
                print(f"[✔] Inserted llm_agent_configs for agent '{agent}' → default={ALIAS}")

    await engine.dispose()
    print("\n✅ Done — gpt-6-luna is now the active model for all agents.")


if __name__ == "__main__":
    asyncio.run(main())
