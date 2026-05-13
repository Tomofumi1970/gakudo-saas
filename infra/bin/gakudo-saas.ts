#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { DatabaseStack } from '../lib/stacks/database-stack';
import { AuthStack } from '../lib/stacks/auth-stack';
import { ApiStack } from '../lib/stacks/api-stack';
import { NotificationStack } from '../lib/stacks/notification-stack';

const app = new cdk.App();

const envName = (app.node.tryGetContext('env') as 'stg' | 'prod') ?? 'stg';

const env: cdk.Environment = {
  account: process.env.CDK_DEFAULT_ACCOUNT ?? '956794148658',
  region: process.env.CDK_DEFAULT_REGION ?? 'ap-northeast-1',
};

const tagAll = (scope: cdk.Stack) => {
  cdk.Tags.of(scope).add('project', 'gakudo-saas');
  cdk.Tags.of(scope).add('env', envName);
};

const db = new DatabaseStack(app, `GakudoSaas-Database-${envName}`, {
  envName,
  env,
});
tagAll(db);

const auth = new AuthStack(app, `GakudoSaas-Auth-${envName}`, {
  envName,
  env,
});
tagAll(auth);

const notification = new NotificationStack(app, `GakudoSaas-Notification-${envName}`, {
  envName,
  env,
  fromEmail: (app.node.tryGetContext('fromEmail') as string) ?? 'torii@thinkfactory.co.jp',
});
tagAll(notification);

const api = new ApiStack(app, `GakudoSaas-Api-${envName}`, {
  envName,
  env,
  userPool: auth.userPool,
  fromEmail: notification.fromEmail,
  tables: {
    organizations: db.organizationsTable,
    users: db.usersTable,
    roleAssignments: db.roleAssignmentsTable,
    households: db.householdsTable,
    members: db.membersTable,
    auditLog: db.auditLogTable,
    itemCatalog: db.itemCatalogTable,
    ledger: db.ledgerTable,
    invoices: db.invoicesTable,
    events: db.eventsTable,
    eventParticipants: db.eventParticipantsTable,
    staff: db.staffTable,
    contracts: db.contractsTable,
    timeEntries: db.timeEntriesTable,
    payrollRuns: db.payrollRunsTable,
    attendance: db.attendanceTable,
    announcements: db.announcementsTable,
  },
});
tagAll(api);
api.addDependency(auth);
api.addDependency(db);
api.addDependency(notification);
