import * as cdk from 'aws-cdk-lib/core';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export interface StorageStackProps extends cdk.StackProps {
  envName: 'stg' | 'prod';
}

/**
 * Phase 6.2: 規程文書・添付ファイル等の S3 ストレージ。
 *
 * - documentsBucket: 規程文書(就業規則・賃金規程・運営規程など)の本体保存
 *   キー設計: {org_id}/{doc_key}/{version}/{filename}
 *   versioning は有効化(削除/上書きの取り戻し容易化)
 *
 * Lambda は presigned URL を発行することで保護者・スタッフがファイルを直接アップロード/ダウンロード可。
 */
export class StorageStack extends cdk.Stack {
  public readonly documentsBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props: StorageStackProps) {
    super(scope, id, props);

    const prefix = `gakudo-saas-${props.envName}`;

    this.documentsBucket = new s3.Bucket(this, 'DocumentsBucket', {
      bucketName: `${prefix}-documents-${this.account}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy:
        props.envName === 'prod'
          ? cdk.RemovalPolicy.RETAIN
          : cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: props.envName !== 'prod',
      cors: [
        {
          // presigned URL でブラウザから直接アップロード/ダウンロードできるよう CORS 許可
          allowedHeaders: ['*'],
          allowedMethods: [
            s3.HttpMethods.PUT,
            s3.HttpMethods.GET,
            s3.HttpMethods.HEAD,
          ],
          allowedOrigins: ['*'],
          exposedHeaders: ['ETag'],
          maxAge: 3000,
        },
      ],
    });

    new cdk.CfnOutput(this, 'DocumentsBucketName', {
      value: this.documentsBucket.bucketName,
    });
  }
}
