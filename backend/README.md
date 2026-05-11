# gakudo-saas Backend

Lambda ハンドラ群。デフォルト言語は Python(spec.md §2)。一部 TypeScript 可。

## ディレクトリ構成

```
backend/
  handlers/
    me/handler.py           # GET /me 認証検証用
    ...                     # 追加ハンドラはここに
```

各ハンドラは独立ディレクトリで、CDK の `lambda.Code.fromAsset()` から参照される。

## 開発

依存関係を持つハンドラは `requirements.txt` を同階層に置く。CDK が Docker でビルドして
Lambda レイヤーとしてパッケージする(Phase 2以降で必要に応じ追加)。
