"""Who is calling, and what can they do in the portal.

Identity comes from the Databricks Apps forwarded headers (x-forwarded-email / x-forwarded-access-token).
App role precedence: explicit scorecard.app_user_role row  >  UC persona (lochard_governance.principal_persona,
the same table the ABAC policies use)  >  OBSERVER.  Workspace admins can always use the persona switcher.

Admins can also preview the portal as another app role ("view as" lens, header x-lochard-view-as). The lens only ever
narrows what the portal lets them do; Unity Catalog still evaluates their real identity for data access.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

from fastapi import HTTPException, Request

from . import config, db, sql

PERSONA_ROLE = {"board": "BOARD", "leadership": "LLT", "platform_admin": "ADMIN", "finance": "KPI_OWNER",
                "hse": "KPI_OWNER", "hse_investigator": "KPI_OWNER", "maintenance": "KPI_OWNER",
                "operations": "KPI_OWNER", "budget_holder": "OBSERVER", "data_engineer": "OBSERVER"}
VIEW_AS = ("LLT", "KPI_OWNER", "BOARD", "OBSERVER", "ADMIN")
_cache: dict[str, tuple[float, "User"]] = {}
TTL = 300          # seconds; persona switches invalidate explicitly (auth.invalidate)


@dataclass
class User:
    email: str
    name: str
    token: str | None
    role: str = "OBSERVER"
    personas: list[str] = field(default_factory=list)
    persona_team: str | None = None
    workspace_admin: bool = False
    initials: str | None = None
    persona_source: str = "none"
    real_role: str | None = None      # set when an admin is viewing the portal as another role
    can_view_as: bool = False

    @property
    def can_switch_persona(self) -> bool:
        return self.workspace_admin or "platform_admin" in self.personas or (self.real_role or self.role) == "ADMIN"

    def as_dict(self):
        return {"email": self.email, "name": self.name, "role": self.role, "real_role": self.real_role or self.role,
                "view_as": self.role if self.real_role else None, "can_view_as": self.can_view_as,
                "personas": self.personas, "persona_team": self.persona_team, "workspace_admin": self.workspace_admin,
                "can_switch_persona": self.can_switch_persona, "initials": self.initials,
                "persona_source": self.persona_source, "obo": bool(self.token)}


def _identity(request: Request) -> tuple[str, str, str | None]:
    token = request.headers.get("x-forwarded-access-token")
    email = request.headers.get("x-forwarded-email") or request.headers.get("x-forwarded-preferred-username")
    if not email:
        email = config.user_client(token).current_user.me().user_name
    name = request.headers.get("x-forwarded-preferred-username") or email
    return email, name, token


def current_user(request: Request) -> User:
    u = _base_user(request)
    view = (request.headers.get("x-lochard-view-as") or "").upper()
    if view in VIEW_AS and u.can_view_as and view != u.role:
        return replace(u, role=view, real_role=u.role)
    return u


def _base_user(request: Request) -> User:
    email, name, token = _identity(request)
    hit = _cache.get(email)
    if hit and time.time() - hit[0] < TTL:
        u = hit[1]
        u.token = token
        return u
    u = User(email=email, name=name.split("@")[0].replace(".", " ").title(), token=token)
    try:
        me = config.user_client(token).current_user.me()
        u.workspace_admin = any((g.display or "") == "admins" for g in (me.groups or []))
        if me.display_name:
            u.name = me.display_name
    except Exception:  # noqa: BLE001 – default scopes include iam.current-user:read, but degrade gracefully
        pass
    res = sql.safe(token, f"SELECT persona, team FROM {config.CATALOG}.{config.GOVERNANCE}.principal_persona "
                          f"WHERE principal = current_user()")
    if "error" not in res:
        u.personas = [r["persona"] for r in res["rows"]]
        u.persona_team = next((r["team"] for r in res["rows"] if r.get("team")), None)
        u.persona_source = "unity_catalog"
    with db.tx(email) as cur:
        cur.execute("SELECT role, initials FROM scorecard.app_user_role WHERE email = %s", (email,))
        row = cur.fetchone()
    if row:
        u.role, u.initials = row["role"], row["initials"]
    elif u.personas:
        ranks = ["ADMIN", "BOARD", "LLT", "KPI_OWNER", "OBSERVER"]
        u.role = sorted((PERSONA_ROLE.get(p, "OBSERVER") for p in u.personas), key=ranks.index)[0]
    elif u.workspace_admin:
        u.role = "ADMIN"
    u.can_view_as = u.can_switch_persona
    _cache[email] = (time.time(), u)
    return u


def invalidate(email: str):
    _cache.pop(email, None)


def require(u: User, *roles: str):
    if u.role not in roles and u.role != "ADMIN":
        raise HTTPException(403, f"requires role {' or '.join(roles)} (you are {u.role})")
