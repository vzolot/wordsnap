"""Режим школи (M14): кілька викладачів + групи. Ізоляція всередині школи —
викладач бачить лише свої групи/учнів/колоди; owner бачить усе.

Solo-тенанти (is_school=false) не зачіпаються: там один викладач і всі учні його.
"""
from __future__ import annotations

import secrets

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import SessionLocal
from .models import Group, GroupMember, Tenant, User


def _new_token() -> str:
    return secrets.token_urlsafe(12)[:24]


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
        uid, name = user.id, (user.first_name or "")
    await ensure_default_group(tenant_id, uid, name)
    return {"ok": True, "user_id": uid}


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
    async with SessionLocal() as s:
        return bool((await s.execute(
            select(Tenant.is_school).where(Tenant.id == tenant_id)
        )).scalar_one_or_none())


# ─── Інвайт-посилання (викладачі + учні до викладача) ────────────────────────

async def ensure_default_group(tenant_id: int, teacher_user_id: int, teacher_name: str = "") -> Group:
    """Дефолтна група викладача (для інвайту учнів). Створює з invite_token якщо нема."""
    async with SessionLocal() as s:
        g = (await s.execute(
            select(Group).where(
                Group.tenant_id == tenant_id,
                Group.teacher_user_id == teacher_user_id,
                Group.is_default.is_(True),
            )
        )).scalar_one_or_none()
        if g is None:
            g = Group(
                tenant_id=tenant_id, teacher_user_id=teacher_user_id,
                name=(f"Учні {teacher_name}".strip()[:120] or "Мої учні"),
                is_default=True, invite_token=_new_token(),
            )
            s.add(g)
            await s.commit()
            await s.refresh(g)
        elif not g.invite_token:
            g.invite_token = _new_token()
            await s.commit()
            await s.refresh(g)
        return g


async def get_teacher_invite_token(tenant_id: int, regenerate: bool = False) -> str | None:
    """Токен інвайту викладачів школи (генерує при першому запиті). None якщо не школа."""
    async with SessionLocal() as s:
        t = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        if t is None or not t.is_school:
            return None
        if regenerate or not t.teacher_invite_token:
            t.teacher_invite_token = _new_token()
            await s.commit()
        return t.teacher_invite_token


async def redeem_teacher_invite(tenant_id: int, token: str, user_id: int) -> bool:
    """t_<token>: якщо збігається з teacher_invite_token школи → робимо викладачем."""
    if not token:
        return False
    name = ""
    async with SessionLocal() as s:
        t = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        if t is None or not t.is_school or not t.teacher_invite_token or t.teacher_invite_token != token:
            return False
        u = (await s.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if u is None:
            return False
        name = u.first_name or ""
        if u.role != "owner":
            u.role = "teacher"
            u.is_active_teacher = True
            await s.commit()
    await ensure_default_group(tenant_id, user_id, name)
    return True


async def redeem_student_invite(tenant_id: int, token: str, user_id: int) -> int | None:
    """s_<token>: кріпить учня до групи з цим invite_token. Повертає teacher_user_id."""
    if not token:
        return None
    async with SessionLocal() as s:
        g = (await s.execute(
            select(Group).where(Group.tenant_id == tenant_id, Group.invite_token == token)
        )).scalar_one_or_none()
        if g is None:
            return None
        await s.execute(pg_insert(GroupMember).values(
            group_id=g.id, user_id=user_id,
        ).on_conflict_do_nothing(index_elements=["group_id", "user_id"]))
        await s.commit()
        return g.teacher_user_id


async def assign_student_to_teacher(tenant_id: int, student_user_id: int, teacher_user_id: int) -> bool:
    """Призначає учня викладачу: додає в дефолтну групу викладача і прибирає з
    дефолтних груп інших викладачів (один основний викладач на учня)."""
    g = await ensure_default_group(tenant_id, teacher_user_id)
    async with SessionLocal() as s:
        st = (await s.execute(select(User.id).where(
            User.id == student_user_id, User.tenant_id == tenant_id, User.role == "student",
        ))).scalar_one_or_none()
        if st is None:
            return False
        others = (await s.execute(select(Group.id).where(
            Group.tenant_id == tenant_id, Group.is_default.is_(True), Group.id != g.id,
        ))).scalars().all()
        if others:
            await s.execute(delete(GroupMember).where(
                GroupMember.user_id == student_user_id, GroupMember.group_id.in_(others),
            ))
        await s.execute(pg_insert(GroupMember).values(
            group_id=g.id, user_id=student_user_id,
        ).on_conflict_do_nothing(index_elements=["group_id", "user_id"]))
        await s.commit()
    return True


async def students_with_teacher(tenant_id: int) -> list[dict]:
    """Усі учні школи + їхній поточний викладач (за дефолтною групою)."""
    async with SessionLocal() as s:
        students = (await s.execute(select(User).where(
            User.tenant_id == tenant_id, User.role == "student",
        ).order_by(User.id))).scalars().all()
        rows = (await s.execute(
            select(GroupMember.user_id, Group.teacher_user_id)
            .join(Group, Group.id == GroupMember.group_id)
            .where(Group.tenant_id == tenant_id, Group.is_default.is_(True))
        )).all()
        tmap = {uid: tid for uid, tid in rows}
        return [
            {"id": u.id, "name": u.first_name or (f"@{u.username}" if u.username else f"id{u.telegram_id}"),
             "target_lang": u.target_lang,  # мова, яку вивчає
             "teacher_id": tmap.get(u.id)}
            for u in students
        ]


async def remove_student(tenant_id: int, student_user_id: int, requester_id: int,
                         requester_role: str, is_school_tenant: bool) -> bool:
    """Видаляє учня. Owner або соло-репетитор — повністю з тенанта (каскад слів/
    повторень). Викладач у школі — лише відкріплює зі СВОЇХ груп."""
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(
            User.id == student_user_id, User.tenant_id == tenant_id, User.role == "student",
        ))).scalar_one_or_none()
        if u is None:
            return False
        if requester_role == "owner" or not is_school_tenant:
            await s.execute(delete(User).where(User.id == student_user_id))
        else:
            await s.execute(delete(GroupMember).where(
                GroupMember.user_id == student_user_id,
                GroupMember.group_id.in_(
                    select(Group.id).where(
                        Group.tenant_id == tenant_id, Group.teacher_user_id == requester_id,
                    )
                ),
            ))
        await s.commit()
        return True


async def remove_teacher(tenant_id: int, teacher_user_id: int) -> bool:
    """Видаляє викладача школи (owner видалити не можна). Прибирає його групи
    (каскадом — членства учнів у них), його колоди, його уроки та саму особу
    (каскадом — його слова/повторення/доступність). УЧНІВ не видаляє — вони
    лишаються в тенанті без викладача, адмін може перепризначити."""
    from .models import Deck, Lesson
    async with SessionLocal() as s:
        u = (await s.execute(select(User).where(
            User.id == teacher_user_id, User.tenant_id == tenant_id, User.role == "teacher",
        ))).scalar_one_or_none()
        if u is None:
            return False
        await s.execute(delete(Group).where(
            Group.tenant_id == tenant_id, Group.teacher_user_id == teacher_user_id))
        await s.execute(delete(Deck).where(
            Deck.tenant_id == tenant_id, Deck.owner_user_id == teacher_user_id))
        await s.execute(delete(Lesson).where(
            Lesson.tenant_id == tenant_id, Lesson.teacher_user_id == teacher_user_id))
        await s.execute(delete(User).where(User.id == teacher_user_id))
        await s.commit()
        return True


async def school_teacher_stats(tenant_id: int) -> list[dict]:
    """Per-teacher: учнів, занять проведено (всього + цього місяця), заплановано,
    + invite_token дефолтної групи."""
    from datetime import datetime, timezone
    from .models import Lesson
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with SessionLocal() as s:
        teachers = (await s.execute(select(User).where(
            User.tenant_id == tenant_id, User.role.in_(("teacher", "owner")),
        ).order_by(User.role.desc(), User.id))).scalars().all()
        out = []
        for t in teachers:
            students = (await s.execute(
                select(func.count(func.distinct(GroupMember.user_id)))
                .select_from(GroupMember).join(Group, Group.id == GroupMember.group_id)
                .where(Group.tenant_id == tenant_id, Group.teacher_user_id == t.id)
            )).scalar() or 0

            def _lc(*conds):
                return select(func.count(Lesson.id)).where(
                    Lesson.tenant_id == tenant_id, Lesson.teacher_user_id == t.id,
                    Lesson.status.in_(("booked", "completed")), *conds,
                )
            done_total = (await s.execute(_lc(Lesson.starts_at_utc < now))).scalar() or 0
            done_month = (await s.execute(_lc(Lesson.starts_at_utc < now, Lesson.starts_at_utc >= month_start))).scalar() or 0
            scheduled = (await s.execute(_lc(Lesson.starts_at_utc >= now))).scalar() or 0
            g = (await s.execute(select(Group).where(
                Group.tenant_id == tenant_id, Group.teacher_user_id == t.id, Group.is_default.is_(True),
            ))).scalar_one_or_none()
            out.append({
                "id": t.id, "name": t.first_name or f"id{t.telegram_id}", "role": t.role,
                "target_lang": t.target_lang,  # мова, яку викладає
                "students": int(students), "lessons_done_total": int(done_total),
                "lessons_done_month": int(done_month), "lessons_scheduled": int(scheduled),
                "invite_token": (g.invite_token if g else None),
            })
        return out
