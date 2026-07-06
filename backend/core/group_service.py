"""Режим школи (M14): кілька викладачів + групи. Ізоляція всередині школи —
викладач бачить лише свої групи/учнів/колоди; owner бачить усе.

Solo-тенанти (is_school=false) не зачіпаються: там один викладач і всі учні його.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import SessionLocal
from .models import Group, GroupMember, User


# ─── Викладачі (owner керує) ─────────────────────────────────────────────────

async def list_teachers(tenant_id: int) -> list[dict]:
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                User.role.in_(("teacher", "owner")),
            ).order_by(User.role.desc(), User.id)
        )).scalars().all()
        return [
            {"id": u.id, "telegram_id": u.telegram_id,
             "name": u.first_name or (f"@{u.username}" if u.username else f"id{u.telegram_id}"),
             "role": u.role, "is_active": u.is_active_teacher}
            for u in rows
        ]


async def add_teacher(tenant_id: int, telegram_id: int) -> dict:
    """Робить наявного користувача (який стартував бота) викладачем. Повертає
    {ok, error?}."""
    async with SessionLocal() as s:
        user = (await s.execute(
            select(User).where(User.telegram_id == telegram_id, User.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if user is None:
            return {"ok": False, "error": "user_not_found"}  # хай спершу натисне Start
        if user.role == "owner":
            return {"ok": True, "already": True}
        user.role = "teacher"
        user.is_active_teacher = True
        await s.commit()
        return {"ok": True, "user_id": user.id}


async def set_teacher_active(tenant_id: int, teacher_user_id: int, active: bool) -> bool:
    async with SessionLocal() as s:
        u = (await s.execute(
            select(User).where(
                User.id == teacher_user_id, User.tenant_id == tenant_id,
                User.role == "teacher",  # owner не деактивуємо
            )
        )).scalar_one_or_none()
        if u is None:
            return False
        u.is_active_teacher = active
        await s.commit()
        return True


# ─── Групи ───────────────────────────────────────────────────────────────────

async def create_group(tenant_id: int, name: str, teacher_user_id: int) -> Group:
    async with SessionLocal() as s:
        g = Group(tenant_id=tenant_id, name=name.strip()[:120] or "Група",
                  teacher_user_id=teacher_user_id)
        s.add(g)
        await s.commit()
        await s.refresh(g)
        return g


async def list_groups(tenant_id: int, teacher_user_id: int | None = None) -> list[dict]:
    """teacher_user_id заданий → лише групи цього викладача (ізоляція); None
    (owner) → усі групи тенанта."""
    async with SessionLocal() as s:
        q = select(Group).where(Group.tenant_id == tenant_id)
        if teacher_user_id is not None:
            q = q.where(Group.teacher_user_id == teacher_user_id)
        groups = (await s.execute(q.order_by(Group.created_at.desc()))).scalars().all()
        out = []
        for g in groups:
            n = (await s.execute(
                select(func.count(GroupMember.id)).where(GroupMember.group_id == g.id)
            )).scalar() or 0
            out.append({"id": g.id, "name": g.name, "teacher_user_id": g.teacher_user_id,
                        "members": int(n)})
        return out


async def _teacher_owns_group(s, tenant_id, group_id, teacher_user_id) -> bool:
    if teacher_user_id is None:
        # owner — перевіряємо лише тенант
        g = (await s.execute(
            select(Group.id).where(Group.id == group_id, Group.tenant_id == tenant_id)
        )).scalar_one_or_none()
        return g is not None
    g = (await s.execute(
        select(Group.id).where(
            Group.id == group_id, Group.tenant_id == tenant_id,
            Group.teacher_user_id == teacher_user_id,
        )
    )).scalar_one_or_none()
    return g is not None


async def set_group_members(
    tenant_id: int, group_id: int, user_ids: list[int], teacher_user_id: int | None,
) -> int:
    """Замінює склад групи. teacher_user_id (не-owner) мусить володіти групою.
    user_ids валідуються по тенанту."""
    async with SessionLocal() as s:
        if not await _teacher_owns_group(s, tenant_id, group_id, teacher_user_id):
            return -1
        valid = list((await s.execute(
            select(User.id).where(
                User.id.in_(user_ids or []), User.tenant_id == tenant_id,
                User.role == "student",
            )
        )).scalars().all())
        await s.execute(delete(GroupMember).where(GroupMember.group_id == group_id))
        for uid in valid:
            await s.execute(pg_insert(GroupMember).values(
                group_id=group_id, user_id=uid
            ).on_conflict_do_nothing(index_elements=["group_id", "user_id"]))
        await s.commit()
        return len(valid)


async def group_member_ids(group_id: int) -> list[int]:
    async with SessionLocal() as s:
        return list((await s.execute(
            select(GroupMember.user_id).where(GroupMember.group_id == group_id)
        )).scalars().all())


async def student_ids_for_teacher(tenant_id: int, teacher_user_id: int) -> list[int]:
    """Учні викладача = члени всіх його груп. Для ізоляції дашборду в школі."""
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(GroupMember.user_id)
            .join(Group, Group.id == GroupMember.group_id)
            .where(Group.tenant_id == tenant_id, Group.teacher_user_id == teacher_user_id)
            .distinct()
        )).scalars().all()
        return list(rows)


async def is_school(tenant_id: int) -> bool:
    from .models import Tenant
    async with SessionLocal() as s:
        return bool((await s.execute(
            select(Tenant.is_school).where(Tenant.id == tenant_id)
        )).scalar_one_or_none())
