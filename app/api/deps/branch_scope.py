"""app/api/deps/branch_scope.py — Multi-branch query scoping helpers."""
from typing import Optional, Dict, Any
from app.models.user import User

def get_branch_scope_filter(
    user: User,
    branch_id_param: Optional[int] = None,
) -> Dict[str, Any]:
    """Return kwargs for SQLAlchemy `filter_by()` based on user role.

    Rules
    -----
    • Admin / super_admin + branch_id_param  →  scoped to that branch
    • Admin / super_admin + no param         →  no filter (all branches)
    • Staff                                  →  locked to staff.branch_id
    • Customer / other                       →  no filter
    """
    if user.role.value in ("admin", "super_admin"):
        if branch_id_param is not None:
            return {"branch_id": branch_id_param}
        return {}

    if user.role.value == "staff" and user.branch_id is not None:
        return {"branch_id": user.branch_id}

    return {}


def can_access_branch(user: User, branch_id: int) -> bool:
    """Explicit permission check for a single branch."""
    if user.role.value in ("admin", "super_admin"):
        return True
    return user.branch_id == branch_id
