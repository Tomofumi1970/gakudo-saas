# gakudo-saas Infrastructure (AWS CDK)

学童保育SaaSのAWSインフラ定義。CDK TypeScript。

## スタック構成 (Phase 1)

- **`GakudoSaas-Database-<env>`** — DynamoDB(Organizations / Users / RoleAssignments / Households / Members / AuditLog)
- **`GakudoSaas-Auth-<env>`** — Cognito User Pool(共通プール+org_id属性)
- **`GakudoSaas-Api-<env>`** — API Gateway + Lambda(認証検証用 GET /me)

`<env>` は `stg` / `prod` のいずれか。`cdk` コマンドに `--context env=<env>` で切替。

## 前提

- Node.js 20+
- AWS CLI 認証済み(`aws sts get-caller-identity` で確認)
- 初回のみ: `npx cdk bootstrap aws://<account>/ap-northeast-1 --context env=stg`

## 開発・デプロイ手順

```sh
cd infra
npm install

# 型チェック
npx tsc --noEmit

# CloudFormation 生成(デプロイなし)
npm run synth:stg

# 既存リソースとの差分確認
npm run diff:stg

# デプロイ(ユーザー許可が必要)
npm run deploy:stg
```

本番環境は `:prod` サフィックスのスクリプトを使用。

## ディレクトリ構成

```
infra/
  bin/gakudo-saas.ts        # CDK エントリーポイント
  lib/stacks/
    database-stack.ts       # DynamoDB
    auth-stack.ts           # Cognito
    api-stack.ts            # API Gateway + Lambda
  cdk.json
  package.json
```

Lambda コードは `../backend/handlers/<name>/` 配下。
