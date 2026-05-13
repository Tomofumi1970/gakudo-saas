#!/usr/bin/env bash
set -euo pipefail

# STG Cognito User Pool にテストユーザーを2人作成する。
# - スタッフ: torii+staff@thinkfactory.co.jp / Gakudo2026!Staff
# - 保護者:   torii+parent@thinkfactory.co.jp / Gakudo2026!Parent (鳥井家世帯所属)
#
# メールアドレスはエイリアス(+suffix)で実体は torii@thinkfactory.co.jp 同一受信箱。
# Cognito ではこれを別ユーザーとして扱う。

USER_POOL_ID="${USER_POOL_ID:-ap-northeast-1_ZYtZsfMJn}"
REGION="${AWS_REGION:-ap-northeast-1}"
HID="${HOUSEHOLD_ID:-46e3600bae364b60b8b75952cdbcf66b}"
ORG_ID="${ORG_ID:-ORG_himawari}"

STAFF_EMAIL="torii+staff@thinkfactory.co.jp"
STAFF_PASS="Gakudo2026!Staff"
PARENT_EMAIL="torii+parent@thinkfactory.co.jp"
PARENT_PASS="Gakudo2026!Parent"

create_user() {
  local email="$1"; shift
  local password="$1"; shift
  # 残りの引数はカスタム属性 ("Name=custom:user_type,Value=staff" の形式)
  local existing
  existing=$(aws cognito-idp admin-get-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$email" \
    --region "$REGION" 2>/dev/null || true)
  if [[ -n "$existing" ]]; then
    echo "User already exists: $email — skipping create"
  else
    aws cognito-idp admin-create-user \
      --user-pool-id "$USER_POOL_ID" \
      --username "$email" \
      --user-attributes \
        "Name=email,Value=$email" \
        "Name=email_verified,Value=true" \
        "$@" \
      --message-action SUPPRESS \
      --region "$REGION" > /dev/null
    echo "Created user: $email"
  fi

  aws cognito-idp admin-set-user-password \
    --user-pool-id "$USER_POOL_ID" \
    --username "$email" \
    --password "$password" \
    --permanent \
    --region "$REGION"
  echo "Password set (permanent): $email"
}

create_user "$STAFF_EMAIL" "$STAFF_PASS" \
  "Name=custom:org_id,Value=$ORG_ID" \
  "Name=custom:user_type,Value=staff"

create_user "$PARENT_EMAIL" "$PARENT_PASS" \
  "Name=custom:org_id,Value=$ORG_ID" \
  "Name=custom:user_type,Value=parent" \
  "Name=custom:household_id,Value=$HID"

cat <<EOF

------------------------------------------------------------
テストユーザー作成完了

スタッフ:
  email:    $STAFF_EMAIL
  password: $STAFF_PASS

保護者:
  email:    $PARENT_EMAIL
  password: $PARENT_PASS
  世帯:     $HID
------------------------------------------------------------
EOF
