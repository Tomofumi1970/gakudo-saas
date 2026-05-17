import * as cdk from 'aws-cdk-lib/core';
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';
import * as path from 'path';

export interface ApiStackTables {
  organizations: dynamodb.Table;
  users: dynamodb.Table;
  roleAssignments: dynamodb.Table;
  households: dynamodb.Table;
  members: dynamodb.Table;
  auditLog: dynamodb.Table;
  itemCatalog: dynamodb.Table;
  ledger: dynamodb.Table;
  invoices: dynamodb.Table;
  events: dynamodb.Table;
  eventParticipants: dynamodb.Table;
  staff: dynamodb.Table;
  contracts: dynamodb.Table;
  timeEntries: dynamodb.Table;
  payrollRuns: dynamodb.Table;
  attendance: dynamodb.Table;
  announcements: dynamodb.Table;
  meetingMinutes: dynamodb.Table;
  documents: dynamodb.Table;
  resolutions: dynamodb.Table;
  ballots: dynamodb.Table;
}

export interface ApiStackProps extends cdk.StackProps {
  envName: 'stg' | 'prod';
  userPool: cognito.UserPool;
  tables: ApiStackTables;
  /** SES 送信元(NotificationStack で verify 済の前提)。 */
  fromEmail: string;
  /** 規程文書ストレージ。 */
  documentsBucket: s3.IBucket;
}

interface AccessSpec {
  read?: (keyof ApiStackTables)[];
  write?: (keyof ApiStackTables)[];
  /** SES:SendEmail / SendRawEmail 権限を Lambda に付与する。 */
  sendEmail?: boolean;
  /** documentsBucket への read/write を Lambda に付与する。 */
  docsBucket?: 'read' | 'write';
  /** bedrock:InvokeModel 権限を Lambda に付与する。 */
  bedrock?: boolean;
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
  private readonly fromEmail: string;
  private readonly documentsBucket: s3.IBucket;

  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);

    this.envName = props.envName;
    this.tables = props.tables;
    this.fromEmail = props.fromEmail;
    this.documentsBucket = props.documentsBucket;
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

    // === Phase 2: 料金カタログ / 課金 / 請求書 ===

    this.registerEndpoint({
      id: 'CatalogCreateFn',
      handler: 'handlers.catalog.create.handler',
      resourcePath: ['catalog', 'items'],
      method: 'POST',
      access: { write: ['itemCatalog', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'CatalogListFn',
      handler: 'handlers.catalog.list.handler',
      resourcePath: ['catalog', 'items'],
      method: 'GET',
      access: { read: ['itemCatalog'] },
    });

    this.registerEndpoint({
      id: 'ChargesCreateFn',
      handler: 'handlers.charges.create.handler',
      resourcePath: ['charges'],
      method: 'POST',
      access: {
        read: ['households', 'itemCatalog'],
        write: ['ledger', 'auditLog'],
      },
    });

    this.registerEndpoint({
      id: 'BillingGenerateFn',
      handler: 'handlers.billing.generate.handler',
      resourcePath: ['billing', 'generate'],
      method: 'POST',
      access: {
        read: ['ledger'],
        write: ['invoices', 'auditLog'],
      },
    });

    this.registerEndpoint({
      id: 'InvoicesByHouseholdFn',
      handler: 'handlers.invoices.list_by_household.handler',
      resourcePath: ['households', '{household_id}', 'invoices'],
      method: 'GET',
      access: { read: ['households', 'invoices'] },
    });

    // === Phase 3: イベントと実費按分 ===

    this.registerEndpoint({
      id: 'EventsCreateFn',
      handler: 'handlers.events.create.handler',
      resourcePath: ['events'],
      method: 'POST',
      access: { write: ['events', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'EventsListFn',
      handler: 'handlers.events.list.handler',
      resourcePath: ['events'],
      method: 'GET',
      access: { read: ['events'] },
    });

    this.registerEndpoint({
      id: 'EventsRegisterParticipantsFn',
      handler: 'handlers.events.register_participants.handler',
      resourcePath: ['events', '{event_id}', 'participants'],
      method: 'POST',
      access: {
        read: ['events'],
        write: ['events', 'eventParticipants', 'auditLog'],
      },
    });

    this.registerEndpoint({
      id: 'EventsSettleFn',
      handler: 'handlers.events.settle.handler',
      resourcePath: ['events', '{event_id}', 'settle'],
      method: 'POST',
      access: {
        read: ['eventParticipants'],
        write: ['events', 'eventParticipants', 'ledger', 'auditLog'],
      },
    });

    // === Phase 4: 保護者向け自分用 + 請求書発行/消込 ===

    this.registerEndpoint({
      id: 'MeHouseholdFn',
      handler: 'handlers.me.household.handler',
      resourcePath: ['me', 'household'],
      method: 'GET',
      access: { read: ['households', 'members'] },
    });

    this.registerEndpoint({
      id: 'MeInvoicesFn',
      handler: 'handlers.me.invoices.handler',
      resourcePath: ['me', 'invoices'],
      method: 'GET',
      access: { read: ['invoices'] },
    });

    this.registerEndpoint({
      id: 'InvoicesIssueFn',
      handler: 'handlers.invoices.issue.handler',
      resourcePath: [
        'invoices',
        '{household_id}',
        '{billing_unit}',
        'issue',
      ],
      method: 'POST',
      access: {
        read: ['members'],
        write: ['invoices', 'auditLog'],
        sendEmail: true,
      },
    });

    this.registerEndpoint({
      id: 'InvoicesMarkPaidFn',
      handler: 'handlers.invoices.mark_paid.handler',
      resourcePath: [
        'invoices',
        '{household_id}',
        '{billing_unit}',
        'mark-paid',
      ],
      method: 'POST',
      access: { write: ['invoices', 'auditLog'] },
    });

    // === Phase 5: 指導員・労務・給与計算 ===

    this.registerEndpoint({
      id: 'StaffCreateFn',
      handler: 'handlers.staff.create.handler',
      resourcePath: ['staff'],
      method: 'POST',
      access: { write: ['staff', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'StaffListFn',
      handler: 'handlers.staff.list.handler',
      resourcePath: ['staff'],
      method: 'GET',
      access: { read: ['staff'] },
    });

    this.registerEndpoint({
      id: 'ContractsCreateFn',
      handler: 'handlers.contracts.create.handler',
      resourcePath: ['staff', '{staff_id}', 'contracts'],
      method: 'POST',
      access: {
        read: ['staff'],
        write: ['contracts', 'auditLog'],
      },
    });

    this.registerEndpoint({
      id: 'TimeEntriesCreateFn',
      handler: 'handlers.timeentries.create.handler',
      resourcePath: ['staff', '{staff_id}', 'timeentries'],
      method: 'POST',
      access: {
        read: ['staff'],
        write: ['timeEntries', 'auditLog'],
      },
    });

    this.registerEndpoint({
      id: 'PayrollCalculateFn',
      handler: 'handlers.payroll.calculate.handler',
      resourcePath: ['payroll', 'calculate'],
      method: 'POST',
      access: {
        read: ['staff', 'contracts', 'timeEntries'],
        write: ['payrollRuns', 'auditLog'],
      },
    });

    // === Phase 6.1: 出席 / お知らせ ===

    this.registerEndpoint({
      id: 'AttendanceUpsertFn',
      handler: 'handlers.attendance.upsert.handler',
      resourcePath: ['attendance'],
      method: 'POST',
      access: { write: ['attendance', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'AttendanceListByDateFn',
      handler: 'handlers.attendance.list_by_date.handler',
      resourcePath: ['attendance'],
      method: 'GET',
      access: { read: ['attendance'] },
    });

    this.registerEndpoint({
      id: 'AttendanceListByMemberFn',
      handler: 'handlers.attendance.list_by_member.handler',
      resourcePath: ['members', '{member_id}', 'attendance'],
      method: 'GET',
      access: { read: ['attendance'] },
    });

    this.registerEndpoint({
      id: 'AnnouncementsCreateFn',
      handler: 'handlers.announcements.create.handler',
      resourcePath: ['announcements'],
      method: 'POST',
      access: { write: ['announcements', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'AnnouncementsSendFn',
      handler: 'handlers.announcements.send.handler',
      resourcePath: ['announcements', '{announcement_id}', 'send'],
      method: 'POST',
      access: {
        read: ['announcements', 'members'],
        write: ['announcements', 'auditLog'],
        sendEmail: true,
      },
    });

    this.registerEndpoint({
      id: 'MeAnnouncementsFn',
      handler: 'handlers.me.announcements.handler',
      resourcePath: ['me', 'announcements'],
      method: 'GET',
      access: { read: ['announcements'] },
    });

    // === Phase 6.2: 議事録 / 規程文書 ===

    this.registerEndpoint({
      id: 'MeetingsCreateFn',
      handler: 'handlers.meetings.create.handler',
      resourcePath: ['meetings'],
      method: 'POST',
      access: { write: ['meetingMinutes', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'MeetingsListFn',
      handler: 'handlers.meetings.list.handler',
      resourcePath: ['meetings'],
      method: 'GET',
      access: { read: ['meetingMinutes'] },
    });

    this.registerEndpoint({
      id: 'MeetingsPublishFn',
      handler: 'handlers.meetings.publish.handler',
      resourcePath: ['meetings', '{minute_id}', 'publish'],
      method: 'POST',
      access: { write: ['meetingMinutes', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'MeMeetingsFn',
      handler: 'handlers.me.meetings.handler',
      resourcePath: ['me', 'meetings'],
      method: 'GET',
      access: { read: ['meetingMinutes'] },
    });

    this.registerEndpoint({
      id: 'DocumentsUploadUrlFn',
      handler: 'handlers.documents.upload_url.handler',
      resourcePath: ['documents', 'upload-url'],
      method: 'POST',
      access: { docsBucket: 'write' },
    });

    this.registerEndpoint({
      id: 'DocumentsRegisterFn',
      handler: 'handlers.documents.register.handler',
      resourcePath: ['documents'],
      method: 'POST',
      access: { write: ['documents', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'DocumentsListFn',
      handler: 'handlers.documents.list.handler',
      resourcePath: ['documents'],
      method: 'GET',
      access: { read: ['documents'] },
    });

    this.registerEndpoint({
      id: 'DocumentsDownloadUrlFn',
      handler: 'handlers.documents.download_url.handler',
      resourcePath: ['documents', '{doc_key}', 'download-url'],
      method: 'GET',
      access: { read: ['documents'], docsBucket: 'read' },
    });

    // === Phase 6.3: レポート ===

    this.registerEndpoint({
      id: 'ReportsMonthlyRevenueFn',
      handler: 'handlers.reports.monthly_revenue.handler',
      resourcePath: ['reports', 'monthly-revenue'],
      method: 'GET',
      access: { read: ['invoices'] },
    });

    this.registerEndpoint({
      id: 'ReportsUnpaidFn',
      handler: 'handlers.reports.unpaid.handler',
      resourcePath: ['reports', 'unpaid'],
      method: 'GET',
      access: { read: ['invoices'] },
    });

    this.registerEndpoint({
      id: 'ReportsEnrollmentFn',
      handler: 'handlers.reports.enrollment.handler',
      resourcePath: ['reports', 'enrollment'],
      method: 'GET',
      access: { read: ['members'] },
    });

    // === Phase 7.1: AI支援(Bedrock Claude) ===

    this.registerEndpoint({
      id: 'MeetingsSummarizeFn',
      handler: 'handlers.meetings.summarize.handler',
      resourcePath: ['meetings', '{minute_id}', 'summarize'],
      method: 'POST',
      access: { write: ['meetingMinutes', 'auditLog'], bedrock: true },
      timeoutSeconds: 60,
      memorySize: 512,
    });

    this.registerEndpoint({
      id: 'EventsHandoverFn',
      handler: 'handlers.events.handover.handler',
      resourcePath: ['events', '{event_id}', 'handover'],
      method: 'POST',
      access: {
        read: ['eventParticipants'],
        write: ['events', 'auditLog'],
        bedrock: true,
      },
      timeoutSeconds: 90,
      memorySize: 512,
    });

    // === Phase 7.2: 総会議決 ===

    this.registerEndpoint({
      id: 'ResolutionsCreateFn',
      handler: 'handlers.resolutions.create.handler',
      resourcePath: ['resolutions'],
      method: 'POST',
      access: { write: ['resolutions', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'ResolutionsListFn',
      handler: 'handlers.resolutions.list.handler',
      resourcePath: ['resolutions'],
      method: 'GET',
      access: { read: ['resolutions'] },
    });

    this.registerEndpoint({
      id: 'ResolutionsCastVoteFn',
      handler: 'handlers.resolutions.cast_vote.handler',
      resourcePath: ['resolutions', '{resolution_id}', 'votes'],
      method: 'POST',
      access: { read: ['resolutions'], write: ['ballots', 'auditLog'] },
    });

    this.registerEndpoint({
      id: 'ResolutionsTallyFn',
      handler: 'handlers.resolutions.tally.handler',
      resourcePath: ['resolutions', '{resolution_id}', 'tally'],
      method: 'GET',
      access: { read: ['resolutions', 'ballots'] },
    });

    new cdk.CfnOutput(this, 'ApiUrl', { value: this.api.url });
  }

  private registerEndpoint(opts: {
    id: string;
    handler: string;
    resourcePath: string[]; // ['households', '{id}', 'members'] のように分解
    method: string;
    access: AccessSpec;
    timeoutSeconds?: number; // 既定10秒、AI系は60〜120秒
    memorySize?: number; // 既定256MB、AI系は512〜1024MB
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
        ITEM_CATALOG_TABLE: this.tables.itemCatalog.tableName,
        LEDGER_TABLE: this.tables.ledger.tableName,
        INVOICES_TABLE: this.tables.invoices.tableName,
        EVENTS_TABLE: this.tables.events.tableName,
        EVENT_PARTICIPANTS_TABLE: this.tables.eventParticipants.tableName,
        STAFF_TABLE: this.tables.staff.tableName,
        CONTRACTS_TABLE: this.tables.contracts.tableName,
        TIME_ENTRIES_TABLE: this.tables.timeEntries.tableName,
        PAYROLL_RUNS_TABLE: this.tables.payrollRuns.tableName,
        ATTENDANCE_TABLE: this.tables.attendance.tableName,
        ANNOUNCEMENTS_TABLE: this.tables.announcements.tableName,
        MEETING_MINUTES_TABLE: this.tables.meetingMinutes.tableName,
        DOCUMENTS_TABLE: this.tables.documents.tableName,
        RESOLUTIONS_TABLE: this.tables.resolutions.tableName,
        BALLOTS_TABLE: this.tables.ballots.tableName,
        DOCUMENTS_BUCKET: this.documentsBucket.bucketName,
        FROM_EMAIL: this.fromEmail,
      },
      timeout: cdk.Duration.seconds(opts.timeoutSeconds ?? 10),
      memorySize: opts.memorySize ?? 256,
    });

    for (const t of opts.access.read ?? []) {
      this.tables[t].grantReadData(fn);
    }
    for (const t of opts.access.write ?? []) {
      this.tables[t].grantReadWriteData(fn);
    }
    if (opts.access.sendEmail) {
      fn.addToRolePolicy(
        new iam.PolicyStatement({
          actions: ['ses:SendEmail', 'ses:SendRawEmail'],
          resources: ['*'],
        }),
      );
    }
    if (opts.access.docsBucket === 'read') {
      this.documentsBucket.grantRead(fn);
    } else if (opts.access.docsBucket === 'write') {
      this.documentsBucket.grantReadWrite(fn);
    }
    if (opts.access.bedrock) {
      fn.addToRolePolicy(
        new iam.PolicyStatement({
          actions: ['bedrock:InvokeModel'],
          resources: [
            // inference profile 経由(jp.anthropic.*, global.anthropic.*)
            `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/*anthropic.*`,
            // inference profile が指す実モデル(クロスリージョン)
            `arn:aws:bedrock:*::foundation-model/anthropic.*`,
          ],
        }),
      );
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
