#!/usr/bin/env python3
"""
fix_panel_labels.py — یک‌بار اجرا کن تا button_label های خالی در DB پر بشن
"""
import asyncio, os, sys
sys.path.insert(0, "/app")

from sqlalchemy import select, update
from db.database import AsyncSessionLocal
from db.models import Panel

async def fix():
    async with AsyncSessionLocal() as session:
        res  = await session.execute(select(Panel))
        panels = res.scalars().all()
        fixed = 0
        for p in panels:
            label = (p.button_label or "").strip()
            if not label:
                new_label = (p.name or "").strip() or f"Panel {p.id}"
                await session.execute(
                    update(Panel)
                    .where(Panel.id == p.id)
                    .values(button_label=new_label)
                )
                print(f"  ✅ Panel #{p.id}: button_label = '{new_label}'")
                fixed += 1
            else:
                print(f"  ✔  Panel #{p.id}: '{label}' — OK")
        await session.commit()
        print(f"\n🎉 Done — {fixed} panel(s) fixed.")

asyncio.run(fix())
