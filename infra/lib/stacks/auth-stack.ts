import * as cdk from 'aws-cdk-lib/core';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import { Construct } from 'constructs';

export interface AuthStackProps extends cdk.StackProps {
  envName: 'stg' | 'prod';
}

/**
 * Phase 1: Cognito User Pool(共通プール+org_id属性によるテナント分離)
 *
 * spec.md §3.2 準拠:
 * - Cognito 共通プール
 * - カスタム属性: org_id, user_type (staff/parent/operator)
 * - 1ユーザー複数施設所属はMVP対象外
 */
export class AuthStack extends cdk.Stack {
  public readonly userPool: cognito.UserPool;
  public readonly userPoolClient: cognito.UserPoolClient;

  constructor(scope: Construct, id: string, props: AuthStackProps) {
    super(scope, id, props);

    const { envName } = props;
    const prefix = `gakudo-saas-${envName}`;

    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: `${prefix}-user-pool`,
      selfSignUpEnabled: false, // 招待制(施設管理者が登録)
      signInAliases: { email: true },
      autoVerify: { email: true },
      standardAttributes: {
        email: { required: true, mutable: true },
        familyName: { required: true, mutable: true },
        givenName: { required: true, mutable: true },
      },
      customAttributes: {
        // テナント識別子(必須・不変)
        org_id: new cognito.StringAttribute({ minLen: 1, maxLen: 64, mutable: false }),
        // ユーザー種別: staff | parent | operator
        user_type: new cognito.StringAttribute({ minLen: 1, maxLen: 32, mutable: true }),
      },
      passwordPolicy: {
        minLength: 10,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: false,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy:
        envName === 'prod' ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
    });

    this.userPoolClient = this.userPool.addClient('WebClient', {
      userPoolClientName: `${prefix}-web-client`,
      authFlows: {
        userSrp: true,
        userPassword: false, // SRPのみ(セキュア)
      },
      preventUserExistenceErrors: true,
      idTokenValidity: cdk.Duration.hours(1),
      accessTokenValidity: cdk.Duration.hours(1),
      refreshTokenValidity: cdk.Duration.days(30),
    });

    new cdk.CfnOutput(this, 'UserPoolId', { value: this.userPool.userPoolId });
    new cdk.CfnOutput(this, 'UserPoolClientId', {
      value: this.userPoolClient.userPoolClientId,
    });
  }
}
