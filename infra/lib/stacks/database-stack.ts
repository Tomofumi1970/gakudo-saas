import * as cdk from 'aws-cdk-lib/core';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { Construct } from 'constructs';

export interface DatabaseStackProps extends cdk.StackProps {
  envName: 'stg' | 'prod';
}

/**
 * Phase 1: 認証・ロール・世帯・メンバー・監査ログの最小テーブル群
 *
 * spec.md §3〜§4 に準拠:
 * - 全テーブルで org_id をパーティションキー先頭に含めてマルチテナント分離
 * - 時限ロール(validFrom/validTo)
 * - 世帯メンバーは単一テーブルでステータス切り分け
 * - 監査ログは全エンティティを時系列で追記
 */
export class DatabaseStack extends cdk.Stack {
  public readonly organizationsTable: dynamodb.Table;
  public readonly usersTable: dynamodb.Table;
  public readonly roleAssignmentsTable: dynamodb.Table;
  public readonly householdsTable: dynamodb.Table;
  public readonly membersTable: dynamodb.Table;
  public readonly auditLogTable: dynamodb.Table;

  constructor(scope: Construct, id: string, props: DatabaseStackProps) {
    super(scope, id, props);

    const { envName } = props;
    const prefix = `gakudo-saas-${envName}`;

    const common: Partial<dynamodb.TableProps> = {
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy:
        envName === 'prod' ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
    };

    // Organizations: テナント(学童保育所)
    // PK: org_id
    this.organizationsTable = new dynamodb.Table(this, 'OrganizationsTable', {
      tableName: `${prefix}-organizations`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });

    // Users: Cognito 拡張属性 + 静的ロール
    // PK: org_id, SK: user_id
    // GSI1: email (グローバル検索, 共通プール内一意性)
    this.usersTable = new dynamodb.Table(this, 'UsersTable', {
      tableName: `${prefix}-users`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'user_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.usersTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-email',
      partitionKey: { name: 'email', type: dynamodb.AttributeType.STRING },
    });

    // RoleAssignments: 時限ロール割当(任期付き)
    // PK: org_id, SK: assignment_id (ULID推奨)
    // GSI1: user_id + valid_to (個人のアクティブロール一覧)
    // GSI2: role + valid_to (当該ロールを現在持つ人)
    this.roleAssignmentsTable = new dynamodb.Table(this, 'RoleAssignmentsTable', {
      tableName: `${prefix}-role-assignments`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'assignment_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.roleAssignmentsTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-user-validto',
      partitionKey: { name: 'user_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'valid_to', type: dynamodb.AttributeType.STRING },
    });
    this.roleAssignmentsTable.addGlobalSecondaryIndex({
      indexName: 'gsi2-role-validto',
      partitionKey: { name: 'role', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'valid_to', type: dynamodb.AttributeType.STRING },
    });

    // Households: 世帯
    // PK: org_id, SK: household_id
    this.householdsTable = new dynamodb.Table(this, 'HouseholdsTable', {
      tableName: `${prefix}-households`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'household_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });

    // Members: 世帯メンバー(児童・保護者・兄弟・緊急連絡先を単一テーブルで保持)
    // PK: org_id, SK: member_id
    // GSI1: household_id + member_type (世帯のメンバー一覧)
    // GSI2: status + grade (ACTIVE児童の学年別一覧など)
    this.membersTable = new dynamodb.Table(this, 'MembersTable', {
      tableName: `${prefix}-members`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'member_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.membersTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-household-type',
      partitionKey: { name: 'household_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'member_type', type: dynamodb.AttributeType.STRING },
    });
    this.membersTable.addGlobalSecondaryIndex({
      indexName: 'gsi2-status-grade',
      partitionKey: { name: 'status', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'grade', type: dynamodb.AttributeType.STRING },
    });

    // AuditLog: 全エンティティの編集履歴(spec.md §3.4)
    // PK: org_id#entity_type#entity_id, SK: timestamp
    // GSI1: actor_user_id + timestamp (ユーザー別の操作履歴)
    this.auditLogTable = new dynamodb.Table(this, 'AuditLogTable', {
      tableName: `${prefix}-audit-log`,
      partitionKey: { name: 'entity_key', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.auditLogTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-actor-timestamp',
      partitionKey: { name: 'actor_user_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.STRING },
    });

    new cdk.CfnOutput(this, 'OrganizationsTableName', {
      value: this.organizationsTable.tableName,
    });
    new cdk.CfnOutput(this, 'UsersTableName', { value: this.usersTable.tableName });
  }
}
