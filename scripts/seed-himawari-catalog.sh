#!/usr/bin/env bash
# 本山南学童保育所ひまわりクラブ 2026年度保育料表を ItemCatalog に投入する。
# 参考: 第37回総会議案書 P.36
#
# 環境変数:
#   ORG_ID (default: ORG_himawari)
#   AWS_REGION (default: ap-northeast-1)
#   STG/PROD: gakudo-saas-stg-CatalogCreateFn を直接 invoke する

set -euo pipefail

REGION="${AWS_REGION:-ap-northeast-1}"
ORG_ID="${ORG_ID:-ORG_himawari}"
FN="${FN_NAME:-gakudo-saas-stg-CatalogCreateFn}"

post_item() {
  local name="$1" billing="$2" cat="$3" price="$4" tier="${5:-}"
  python3 - <<PY > /tmp/seed_payload.json
import json
body = {"name": "$name", "billing_unit_type": "$billing", "category": "$cat", "unit_price": $price}
if "$tier":
    body["age_tier"] = "$tier"
print(json.dumps({
  "body": json.dumps(body, ensure_ascii=False),
  "requestContext": {"authorizer": {"claims": {
    "sub": "seed-bot",
    "email": "seed@gakudo-saas",
    "custom:org_id": "$ORG_ID",
    "custom:user_type": "operator"
  }}}
}, ensure_ascii=False))
PY
  aws lambda invoke --function-name "$FN" \
    --cli-binary-format raw-in-base64-out \
    --payload file:///tmp/seed_payload.json \
    --region "$REGION" /tmp/seed_out.json > /dev/null
  python3 -c "import json;b=json.loads(json.load(open('/tmp/seed_out.json'))['body']);print(f'  {b.get(\"name\",\"err\")}: id={b.get(\"item_id\",b.get(\"error\"))}')"
}

echo "Seeding ItemCatalog for $ORG_ID ..."

# 入所金・基本保育料
post_item "入所金"               "ONETIME" "tuition"   20000
post_item "基本保育料(低学年)"   "MONTH"   "tuition"   14000
post_item "基本保育料(4年)"      "MONTH"   "tuition"    5000
post_item "基本保育料(5年)"      "MONTH"   "tuition"    4000
post_item "基本保育料(6年)"      "MONTH"   "tuition"    3000

# 特別保育料(夏・冬)
post_item "夏特別保育料"         "ONETIME" "tuition"   10000
post_item "冬特別保育料"         "ONETIME" "tuition"   10000

# 延長保育(30分単位)
post_item "延長保育(30分)"      "ONETIME" "fee"         200

# 会費
post_item "市連会費"             "ANNUAL"  "membership" 2400
post_item "保護者会費"           "ANNUAL"  "membership" 2400

# 昼食代・外出時飲料
post_item "昼食代"               "VACATION" "lunch"      350
post_item "ジュース"             "OUTING"   "beverage"   150
post_item "お茶"                 "OUTING"   "beverage"   110

# イベント参加費(年齢区分別)
post_item "イベント参加費(大人)"          "EVENT" "event_fee" 5000 adult
post_item "イベント参加費(学童在籍)"      "EVENT" "event_fee" 3000 afterschool
post_item "イベント参加費(未就学)"        "EVENT" "event_fee" 1500 preschool
post_item "イベント参加費(卒所後中学生)"  "EVENT" "event_fee" 5000 junior_high

echo ""
echo "Done."
