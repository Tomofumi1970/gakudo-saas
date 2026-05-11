# 学童保育 請求・会員管理 SaaS

学童保育向けのマルチテナント請求・会員管理 SaaS。
AWS サーバーレス + DynamoDB を中心とした構成で構築予定。

## ステータス

🟡 **計画段階** — 実装着手前

## ドキュメント

- [計画書・仕様メモ・実装着手用プロンプト](docs/saas-plan.md)

## 関連プロジェクト

- [himawari](../himawari) — 本山南学童保育所ひまわりクラブ 公式HP(本SaaSの想定利用施設の1つ)

## 想定する技術スタック

- AWS (Cognito, API Gateway, Lambda, DynamoDB, S3, EventBridge, SES)
- IaC: AWS CDK (TypeScript)
- Lambda: Python (一部 TypeScript)
- 開発環境: VSCode + GitHub + Claude
