import * as cdk from 'aws-cdk-lib/core';
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Construct } from 'constructs';
import * as path from 'path';

export interface ApiStackTables {
  organizations: dynamodb.Table;
  users: dynamodb.Table;
  roleAssignments: dynamodb.Table;
  households: dynamodb.Table;
  members: dynamodb.Table;
  auditLog: dynamodb.Table;
}

export interface ApiStackProps extends cdk.StackProps {
  envName: 'stg' | 'prod';
  userPool: cognito.UserPool;
  tables: ApiStackTables;
}

interface AccessSpec {
  read?: (keyof ApiStackTables)[];
  write?: (keyof ApiStackTables)[];
}

/**
 * Phase 2: 会員・世帯管理 API
 *
 * Lambda は backend/ ルートを共通アセットとして使い、handler を
 * `handlers.<domain>.<action>.handler` 形式で指定する。これにより
 * backend/common/ の共通モジュールを各ハンドラから import できる。
 */
export class ApiStack extends cdk.Stack {
  public readonly api: apigw.RestApi;
  private readonly authorizer: apigw.CognitoUserPoolsAuthorizer;
  private readonly tables: ApiStackTables;
  private readonly envName: string;
  private readonly assetCode: lambda.AssetCode;

  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);

    this.envName = props.envName;
    this.tables = props.tables;
    const prefix = `gakudo-saas-${props.envName}`;

    this.api = new apigw.RestApi(this, 'RestApi', {
      restApiName: `${prefix}-api`,
      deployOptions: {
        stageName: props.envName,
        tracingEnabled: true,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigw.Cors.ALL_ORIGINS,
        allowMethods: apigw.Cors.ALL_METHODS,
      },
    });

    this.authorizer = new apigw.CognitoUserPoolsAuthorizer(this, 'CognitoAuthorizer', {
      cognitoUserPools: [props.userPool],
      authorizerName: `${prefix}-cognito-authorizer`,
    });

    this.assetCode = lambda.Code.fromAsset(
      path.join(__dirname, '..', '..', '..', 'backend'),
      {
        exclude: ['**/*.pyc', '**/__pycache__', '**/.pytest_cache', 'README.md'],
      },
    );

    // === エンドポイント定義 ===
    this.registerEndpoint({
      id: 'MeFn',
      handler: 'handlers.me.handler.handler',
      resourcePath: ['me'],
      method: 'GET',
      access: { read: ['users', 'organizations'] },
    });

    this.registerEndpoint({
      id: 'HouseholdsCreateFn',
      handler: 'handlers.households.create.handler',
      resourcePath: ['households'],
      method: 'POST',
      access: { write: ['households', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'HouseholdsListFn',
      handler: 'handlers.households.list.handler',
      resourcePath: ['households'],
      method: 'GET',
      access: { read: ['households'] },
    });

    this.registerEndpoint({
      id: 'MembersCreateFn',
      handler: 'handlers.members.create.handler',
      resourcePath: ['households', '{household_id}', 'members'],
      method: 'POST',
      access: {
        read: ['households'],
        write: ['members', 'auditLog'],
      },
    });

    this.registerEndpoint({
      id: 'MembersListFn',
      handler: 'handlers.members.list.handler',
      resourcePath: ['households', '{household_id}', 'members'],
      method: 'GET',
      access: { read: ['households', 'members'] },
    });

    new cdk.CfnOutput(this, 'ApiUrl', { value: this.api.url });
  }

  private registerEndpoint(opts: {
    id: string;
    handler: string;
    resourcePath: string[]; // ['households', '{id}', 'members'] のように分解
    method: string;
    access: AccessSpec;
  }) {
    const prefix = `gakudo-saas-${this.envName}`;

    const fn = new lambda.Function(this, opts.id, {
      functionName: `${prefix}-${opts.id}`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: opts.handler,
      code: this.assetCode,
      environment: {
        ENV_NAME: this.envName,
        ORGS_TABLE: this.tables.organizations.tableName,
        USERS_TABLE: this.tables.users.tableName,
        ROLE_ASSIGNMENTS_TABLE: this.tables.roleAssignments.tableName,
        HOUSEHOLDS_TABLE: this.tables.households.tableName,
        MEMBERS_TABLE: this.tables.members.tableName,
        AUDIT_LOG_TABLE: this.tables.auditLog.tableName,
      },
      timeout: cdk.Duration.seconds(10),
      memorySize: 256,
    });

    for (const t of opts.access.read ?? []) {
      this.tables[t].grantReadData(fn);
    }
    for (const t of opts.access.write ?? []) {
      this.tables[t].grantReadWriteData(fn);
    }

    // パスを辿って Resource をネスト構築
    let resource: apigw.IResource = this.api.root;
    for (const part of opts.resourcePath) {
      const existing = resource.getResource(part);
      resource = existing ?? resource.addResource(part);
    }
    resource.addMethod(opts.method, new apigw.LambdaIntegration(fn), {
      authorizer: this.authorizer,
      authorizationType: apigw.AuthorizationType.COGNITO,
    });
  }
}
