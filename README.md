# 学童保育 請求・会員管理 SaaS

学童保育向けのマルチテナント請求・会員管理 SaaS。
AWS サーバーレス + DynamoDB を中心とした構成で構築予定。

## ステータス

🟢 **Phase 1 着手** — CDK雛形・認証基盤・DynamoDB設計完了、未デプロイ

## ドキュメント

- [確定仕様書](docs/spec.md) — メインの仕様書
- [計画書・仕様メモ・実装着手用プロンプト](docs/saas-plan.md)
- [仕様確定の対話記録 (2026-05-11)](docs/talks/2026-05-11_学童SaaS仕様.md)
- [Infra README](infra/README.md) — CDK スタック構成と開発手順
- [Backend README](backend/README.md) — Lambda ハンドラ規約

## ディレクトリ構成

```
gakudo-saas/
  docs/         # 仕様書・対話記録
  infra/        # AWS CDK (TypeScript)
  backend/      # Lambda ハンドラ (Python)
  frontend/     # Web UI (将来 Phase で追加)
```

## 関連プロジェクト

- [himawari](../himawari) — 本山南学童保育所ひまわりクラブ 公式HP(本SaaSの想定利用施設の1つ)

## 技術スタック

- AWS (Cognito, API Gateway, Lambda, DynamoDB, S3, EventBridge, SES, Bedrock)
- IaC: AWS CDK (TypeScript)
- Lambda: Python (一部 TypeScript)
- 開発環境: VSCode + GitHub + Claude
