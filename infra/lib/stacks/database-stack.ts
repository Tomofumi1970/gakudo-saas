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
  public readonly itemCatalogTable: dynamodb.Table;
  public readonly ledgerTable: dynamodb.Table;
  public readonly invoicesTable: dynamodb.Table;
  public readonly eventsTable: dynamodb.Table;
  public readonly eventParticipantsTable: dynamodb.Table;

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

    // ItemCatalog: 料金品目カタログ(spec.md §5.1)
    // PK: org_id, SK: item_id
    // GSI1: billing_unit_type + category (請求単位ごとの品目絞り込み)
    this.itemCatalogTable = new dynamodb.Table(this, 'ItemCatalogTable', {
      tableName: `${prefix}-item-catalog`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'item_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.itemCatalogTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-billing-category',
      partitionKey: {
        name: 'billing_unit_type',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: { name: 'category', type: dynamodb.AttributeType.STRING },
    });

    // Ledger: 課金/返金/訂正の追記台帳(spec.md §5.2)
    // PK: org_id#billing_unit (例: ORG_himawari#MONTH#2026-05)
    // SK: ledger_entry_id (created_at プレフィックスで時系列ソート可能に)
    // GSI1: household_id + billing_unit (世帯×請求単位の集計)
    // GSI2: org_id + created_at (テナント横断時系列、運営者向け)
    this.ledgerTable = new dynamodb.Table(this, 'LedgerTable', {
      tableName: `${prefix}-ledger`,
      partitionKey: {
        name: 'org_billing_unit',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: { name: 'ledger_entry_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.ledgerTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-household-billing',
      partitionKey: { name: 'household_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'billing_unit', type: dynamodb.AttributeType.STRING },
    });

    // Invoices: 請求書スナップショット(spec.md §5.2)
    // PK: org_id#household_id, SK: billing_unit (例: MONTH#2026-05)
    // GSI1: org_billing_unit + status (請求単位ごとのステータス別)
    this.invoicesTable = new dynamodb.Table(this, 'InvoicesTable', {
      tableName: `${prefix}-invoices`,
      partitionKey: {
        name: 'org_household',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: { name: 'billing_unit', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.invoicesTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-orgbilling-status',
      partitionKey: {
        name: 'org_billing_unit',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: { name: 'status', type: dynamodb.AttributeType.STRING },
    });

    // Events: イベント(キャンプ・夏まつり等)
    // PK: org_id, SK: event_id
    // GSI1: status + event_date (開催予定/未精算の一覧)
    this.eventsTable = new dynamodb.Table(this, 'EventsTable', {
      tableName: `${prefix}-events`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'event_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.eventsTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-status-date',
      partitionKey: { name: 'status', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'event_date', type: dynamodb.AttributeType.STRING },
    });

    // EventParticipants: 参加者と見込み/実費按分結果
    // PK: org_id#event_id, SK: member_id
    // GSI1: member_id + event_date (個人の参加履歴)
    this.eventParticipantsTable = new dynamodb.Table(this, 'EventParticipantsTable', {
      tableName: `${prefix}-event-participants`,
      partitionKey: { name: 'org_event', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'member_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.eventParticipantsTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-member-date',
      partitionKey: { name: 'member_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'event_date', type: dynamodb.AttributeType.STRING },
    });

    new cdk.CfnOutput(this, 'OrganizationsTableName', {
      value: this.organizationsTable.tableName,
    });
    new cdk.CfnOutput(this, 'UsersTableName', { value: this.usersTable.tableName });
  }
}
