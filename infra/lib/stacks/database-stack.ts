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
  public readonly staffTable: dynamodb.Table;
  public readonly contractsTable: dynamodb.Table;
  public readonly timeEntriesTable: dynamodb.Table;
  public readonly payrollRunsTable: dynamodb.Table;
  public readonly attendanceTable: dynamodb.Table;
  public readonly announcementsTable: dynamodb.Table;
  public readonly meetingMinutesTable: dynamodb.Table;
  public readonly documentsTable: dynamodb.Table;
  public readonly resolutionsTable: dynamodb.Table;
  public readonly ballotsTable: dynamodb.Table;
  public readonly applicationsTable: dynamodb.Table;
  public readonly withdrawalsTable: dynamodb.Table;
  public readonly shiftsTable: dynamodb.Table;
  public readonly bonusRunsTable: dynamodb.Table;

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

    // === Phase 5: 指導員・労務・給与 ===

    // Staff: 指導員マスタ
    // PK: org_id, SK: staff_id
    // GSI1: status + hired_at (在籍指導員一覧)
    this.staffTable = new dynamodb.Table(this, 'StaffTable', {
      tableName: `${prefix}-staff`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'staff_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.staffTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-status-hired',
      partitionKey: { name: 'status', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'hired_at', type: dynamodb.AttributeType.STRING },
    });

    // EmploymentContract: 雇用契約(時系列、有効期間付き)
    // PK: org_id#staff_id, SK: valid_from (時系列ソート)
    // 契約タイプ: REGULAR(月給) | PART_TIME(時給)、各種手当を JSON で保持
    this.contractsTable = new dynamodb.Table(this, 'ContractsTable', {
      tableName: `${prefix}-contracts`,
      partitionKey: { name: 'org_staff', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'valid_from', type: dynamodb.AttributeType.STRING },
      ...common,
    });

    // TimeEntries: 勤怠記録(1日1人複数行可能)
    // PK: org_id#staff_id, SK: entry_id (work_date プレフィックス)
    // GSI1: org_date + staff_id (日別の出勤者一覧)
    this.timeEntriesTable = new dynamodb.Table(this, 'TimeEntriesTable', {
      tableName: `${prefix}-time-entries`,
      partitionKey: { name: 'org_staff', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'entry_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.timeEntriesTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-orgdate-staff',
      partitionKey: { name: 'org_date', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'staff_id', type: dynamodb.AttributeType.STRING },
    });

    // PayrollRun: 月次給与計算結果(スナップショット)
    // PK: org_id#staff_id, SK: period (YYYY-MM)
    // GSI1: org_period + status (期別の給与一覧、振込済管理)
    this.payrollRunsTable = new dynamodb.Table(this, 'PayrollRunsTable', {
      tableName: `${prefix}-payroll-runs`,
      partitionKey: { name: 'org_staff', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'period', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.payrollRunsTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-orgperiod-status',
      partitionKey: { name: 'org_period', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'status', type: dynamodb.AttributeType.STRING },
    });

    // === Phase 6.1: 出席管理 / お知らせ配信 ===

    // Attendance: 出席記録(児童・指導員)
    // PK: org_id#date, SK: member_id
    // GSI1: org_member + work_date (個人の出席履歴)
    this.attendanceTable = new dynamodb.Table(this, 'AttendanceTable', {
      tableName: `${prefix}-attendance`,
      partitionKey: { name: 'org_date', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'member_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.attendanceTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-orgmember-date',
      partitionKey: { name: 'org_member', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'work_date', type: dynamodb.AttributeType.STRING },
    });

    // Announcements: お知らせ
    // PK: org_id, SK: announcement_id
    // GSI1: target_audience + sent_at (受信者別の時系列、参照用)
    this.announcementsTable = new dynamodb.Table(this, 'AnnouncementsTable', {
      tableName: `${prefix}-announcements`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'announcement_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });

    // === Phase 6.2: 議事録 / 規程文書 ===

    // MeetingMinutes: 議事録
    // PK: org_id, SK: minute_id
    // GSI1: meeting_type + meeting_date(種別ごとの時系列)
    this.meetingMinutesTable = new dynamodb.Table(this, 'MeetingMinutesTable', {
      tableName: `${prefix}-meeting-minutes`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'minute_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.meetingMinutesTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-type-date',
      partitionKey: {
        name: 'meeting_type',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: { name: 'meeting_date', type: dynamodb.AttributeType.STRING },
    });

    // Documents: 規程文書のメタデータ(本体は S3)
    // PK: org_id#doc_key, SK: version(YYYY-MM-DD#seq)
    // GSI1: org_doctype + status(種別×ステータスで最新版を引く)
    this.documentsTable = new dynamodb.Table(this, 'DocumentsTable', {
      tableName: `${prefix}-documents`,
      partitionKey: {
        name: 'org_doc_key',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: { name: 'version', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.documentsTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-doctype-status',
      partitionKey: {
        name: 'org_doc_type',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: { name: 'status', type: dynamodb.AttributeType.STRING },
    });

    // === Phase 7.2: 総会議決(Resolution + Ballot) ===

    // Resolutions: 議案(=投票対象)
    // PK: org_id, SK: resolution_id
    // GSI1: assembly_id + order_no(総会単位の議案順序)
    this.resolutionsTable = new dynamodb.Table(this, 'ResolutionsTable', {
      tableName: `${prefix}-resolutions`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'resolution_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.resolutionsTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-assembly-order',
      partitionKey: { name: 'assembly_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'order_no', type: dynamodb.AttributeType.STRING },
    });

    // Ballots: 議決権行使(同 resolution × 同 household は1票で上書き)
    // PK: org_id#resolution_id, SK: household_id
    // GSI1: household_id + resolution_id(個人の投票履歴)
    this.ballotsTable = new dynamodb.Table(this, 'BallotsTable', {
      tableName: `${prefix}-ballots`,
      partitionKey: { name: 'org_resolution', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'household_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.ballotsTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-household-resolution',
      partitionKey: { name: 'household_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'resolution_id', type: dynamodb.AttributeType.STRING },
    });

    // === Phase 8: 入所申込 / 退所届 ===

    this.applicationsTable = new dynamodb.Table(this, 'ApplicationsTable', {
      tableName: `${prefix}-applications`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'application_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.applicationsTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-status-submitted',
      partitionKey: { name: 'status', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'submitted_at', type: dynamodb.AttributeType.STRING },
    });

    this.withdrawalsTable = new dynamodb.Table(this, 'WithdrawalsTable', {
      tableName: `${prefix}-withdrawals`,
      partitionKey: { name: 'org_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'withdrawal_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.withdrawalsTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-household-date',
      partitionKey: { name: 'household_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'submitted_at', type: dynamodb.AttributeType.STRING },
    });

    // === Phase 9: シフト管理 / 賞与 ===

    this.shiftsTable = new dynamodb.Table(this, 'ShiftsTable', {
      tableName: `${prefix}-shifts`,
      partitionKey: { name: 'org_date', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'staff_id', type: dynamodb.AttributeType.STRING },
      ...common,
    });
    this.shiftsTable.addGlobalSecondaryIndex({
      indexName: 'gsi1-staff-date',
      partitionKey: { name: 'org_staff', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'work_date', type: dynamodb.AttributeType.STRING },
    });

    this.bonusRunsTable = new dynamodb.Table(this, 'BonusRunsTable', {
      tableName: `${prefix}-bonus-runs`,
      partitionKey: { name: 'org_staff', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'bonus_key', type: dynamodb.AttributeType.STRING },
      ...common,
    });

    new cdk.CfnOutput(this, 'OrganizationsTableName', {
      value: this.organizationsTable.tableName,
    });
    new cdk.CfnOutput(this, 'UsersTableName', { value: this.usersTable.tableName });
  }
}
