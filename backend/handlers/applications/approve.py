"""POST /applications/{application_id}/approve — 入所申込を承認。

承認時に Household を自動作成し、児童を ACTIVE/child で Member 追加、
親を PRIMARY_GUARDIAN として Member 追加する。
"""
from __future__ import annotations

from typing import Any

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    new_id,
    path_param,
    response,
    table,
    write_audit_log,
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can approve applications")

    application_id = path_param(event, "application_id")
    res = table("APPLICATIONS_TABLE").get_item(
        Key={"org_id": caller.org_id, "application_id": application_id}
    )
    if "Item" not in res:
        raise HttpError(404, "application not found")
    a = res["Item"]
    if a.get("status") != "SUBMITTED":
        raise HttpError(409, f"already {a.get('status')}")

    now = iso_now()
    household_id = new_id()
    household = {
        "org_id": caller.org_id,
        "household_id": household_id,
        "address": a["address"],
        "phone": a["parent_phone"],
        "note": "入所申込より自動作成",
        "created_at": now,
        "created_by": caller.user_id,
        "updated_at": now,
        "updated_by": caller.user_id,
    }
    table("HOUSEHOLDS_TABLE").put_item(Item=household)

    child_id = new_id()
    child: dict[str, Any] = {
        "org_id": caller.org_id,
        "member_id": child_id,
        "household_id": household_id,
        "member_type": "child",
        "status": "ACTIVE",
        "family_name": a["child_family_name"],
        "given_name": a["child_given_name"],
        "date_of_birth": a["child_dob"],
        "photo_consent": False,
        "created_at": now,
        "created_by": caller.user_id,
        "updated_at": now,
        "updated_by": caller.user_id,
    }
    grade = a.get("child_grade")
    if grade:
        child["grade"] = grade
    table("MEMBERS_TABLE").put_item(Item=child)

    parent_id = new_id()
    parent_full = a["parent_name"].strip()
    # 姓名分割の簡易版(スペース区切り)、なければ姓=parent_full、名=""
    if " " in parent_full or " " in parent_full:
        parts = parent_full.replace(" ", " ").split(" ", 1)
        p_family, p_given = parts[0], parts[1]
    else:
        p_family, p_given = parent_full, ""
    parent: dict[str, Any] = {
        "org_id": caller.org_id,
        "member_id": parent_id,
        "household_id": household_id,
        "member_type": "guardian",
        "status": "PRIMARY_GUARDIAN",
        "family_name": p_family or "保護者",
        "given_name": p_given or "代表",
        "email": a["parent_email"],
        "phone": a["parent_phone"],
        "photo_consent": False,
        "created_at": now,
        "created_by": caller.user_id,
        "updated_at": now,
        "updated_by": caller.user_id,
    }
    table("MEMBERS_TABLE").put_item(Item=parent)

    table("APPLICATIONS_TABLE").update_item(
        Key={"org_id": caller.org_id, "application_id": application_id},
        UpdateExpression=(
            "SET #s = :s, approved_at = :t, approved_by = :u, "
            "household_id = :h, child_member_id = :c, parent_member_id = :p"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "APPROVED",
            ":t": now,
            ":u": caller.user_id,
            ":h": household_id,
            ":c": child_id,
            ":p": parent_id,
        },
    )
    write_audit_log(
        "application",
        application_id,
        "approve",
        caller,
        after={
            "household_id": household_id,
            "child_member_id": child_id,
            "parent_member_id": parent_id,
        },
    )
    return response(
        200,
        {
            "application_id": application_id,
            "status": "APPROVED",
            "household_id": household_id,
            "child_member_id": child_id,
            "parent_member_id": parent_id,
        },
    )


handler = handler_wrapper(_impl)
