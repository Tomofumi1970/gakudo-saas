import * as cdk from 'aws-cdk-lib/core';
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Construct } from 'constructs';
import * as path from 'path';

export interface ApiStackProps extends cdk.StackProps {
  envName: 'stg' | 'prod';
  userPool: cognito.UserPool;
  tables: {
    organizations: dynamodb.Table;
    users: dynamodb.Table;
  };
}

/**
 * Phase 1: API Gateway + Lambda 雛形
 *
 * - Cognito User Pool Authorizer で認証
 * - /me エンドポイントで認証動作確認
 * - Lambda は Python(spec.md §2 デフォルト)
 */
export class ApiStack extends cdk.Stack {
  public readonly api: apigw.RestApi;

  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);

    const { envName, userPool, tables } = props;
    const prefix = `gakudo-saas-${envName}`;

    this.api = new apigw.RestApi(this, 'RestApi', {
      restApiName: `${prefix}-api`,
      deployOptions: {
        stageName: envName,
        tracingEnabled: true,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigw.Cors.ALL_ORIGINS,
        allowMethods: apigw.Cors.ALL_METHODS,
      },
    });

    const authorizer = new apigw.CognitoUserPoolsAuthorizer(this, 'CognitoAuthorizer', {
      cognitoUserPools: [userPool],
      authorizerName: `${prefix}-cognito-authorizer`,
    });

    // GET /me — 認証ユーザー自身の情報を返す動作確認用エンドポイント
    const meFn = new lambda.Function(this, 'MeFn', {
      functionName: `${prefix}-me`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(
        path.join(__dirname, '..', '..', '..', 'backend', 'handlers', 'me'),
      ),
      environment: {
        ENV_NAME: envName,
        USERS_TABLE: tables.users.tableName,
        ORGS_TABLE: tables.organizations.tableName,
      },
      timeout: cdk.Duration.seconds(10),
      memorySize: 256,
    });
    tables.users.grantReadData(meFn);
    tables.organizations.grantReadData(meFn);

    const me = this.api.root.addResource('me');
    me.addMethod('GET', new apigw.LambdaIntegration(meFn), {
      authorizer,
      authorizationType: apigw.AuthorizationType.COGNITO,
    });

    new cdk.CfnOutput(this, 'ApiUrl', { value: this.api.url });
  }
}
