import * as cdk from 'aws-cdk-lib/core';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import { Construct } from 'constructs';
import * as path from 'path';

export interface FrontendStackProps extends cdk.StackProps {
  envName: 'stg' | 'prod';
  /** Cognito 設定を HTML に埋め込んで配信する。 */
  userPoolId: string;
  userPoolClientId: string;
  apiUrl: string;
  region: string;
}

/**
 * Phase 確認用: 静的 SPA(単一HTML+JS)を S3 から CloudFront で配信。
 *
 * - S3 はパブリック非公開(OAC 経由のみ)
 * - HTML に Cognito User Pool ID / Client ID / API URL を埋め込む
 * - 配信は CDK の BucketDeployment で frontend/public/ を同期
 */
export class FrontendStack extends cdk.Stack {
  public readonly distributionUrl: string;

  constructor(scope: Construct, id: string, props: FrontendStackProps) {
    super(scope, id, props);

    const prefix = `gakudo-saas-${props.envName}`;

    const bucket = new s3.Bucket(this, 'SiteBucket', {
      bucketName: `${prefix}-frontend-${this.account}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy:
        props.envName === 'prod'
          ? cdk.RemovalPolicy.RETAIN
          : cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: props.envName !== 'prod',
      encryption: s3.BucketEncryption.S3_MANAGED,
    });

    const distribution = new cloudfront.Distribution(this, 'Distribution', {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(bucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED, // 開発中は常に最新
      },
      defaultRootObject: 'index.html',
      errorResponses: [
        { httpStatus: 403, responseHttpStatus: 200, responsePagePath: '/index.html' },
        { httpStatus: 404, responseHttpStatus: 200, responsePagePath: '/index.html' },
      ],
      comment: `${prefix}-frontend`,
    });

    // index.html を Cognito/API 情報入りで生成して同梱
    const configJs = [
      `window.GAKUDO_CONFIG = {`,
      `  region: ${JSON.stringify(props.region)},`,
      `  userPoolId: ${JSON.stringify(props.userPoolId)},`,
      `  userPoolClientId: ${JSON.stringify(props.userPoolClientId)},`,
      `  apiUrl: ${JSON.stringify(props.apiUrl)}`,
      `};`,
    ].join('\n');

    new s3deploy.BucketDeployment(this, 'DeployStatic', {
      sources: [
        s3deploy.Source.asset(
          path.join(__dirname, '..', '..', '..', 'frontend', 'public'),
        ),
        s3deploy.Source.data('config.js', configJs),
      ],
      destinationBucket: bucket,
      distribution,
      distributionPaths: ['/*'],
      prune: false,
    });

    this.distributionUrl = `https://${distribution.distributionDomainName}`;
    new cdk.CfnOutput(this, 'FrontendUrl', { value: this.distributionUrl });
    new cdk.CfnOutput(this, 'FrontendBucket', { value: bucket.bucketName });
  }
}
