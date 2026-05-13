import * as cdk from 'aws-cdk-lib/core';
import * as ses from 'aws-cdk-lib/aws-ses';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';

export interface NotificationStackProps extends cdk.StackProps {
  envName: 'stg' | 'prod';
  /**
   * SES 送信元として登録するメールアドレス。
   * 初回は CDK が EmailIdentity を作成、Verification は受信メールから手動承認が必要。
   * STG では送信先も verified である必要がある(SES sandbox)。
   */
  fromEmail: string;
}

/**
 * Phase 4: 通知基盤
 *
 * - SES EmailIdentity を CDK で作成(verification は受信側で手動承認)
 * - Lambda が送信元として参照するための SSM パラメータを公開
 *
 * spec.md §6 通知はメールのみ(LINE/Push は将来検討)
 */
export class NotificationStack extends cdk.Stack {
  public readonly fromEmail: string;

  constructor(scope: Construct, id: string, props: NotificationStackProps) {
    super(scope, id, props);

    this.fromEmail = props.fromEmail;
    const prefix = `gakudo-saas-${props.envName}`;

    new ses.EmailIdentity(this, 'FromEmailIdentity', {
      identity: ses.Identity.email(props.fromEmail),
    });

    // 他スタックの Lambda が読みやすいよう SSM に公開
    new ssm.StringParameter(this, 'FromEmailParam', {
      parameterName: `/${prefix}/notification/from-email`,
      stringValue: props.fromEmail,
    });

    new cdk.CfnOutput(this, 'FromEmail', { value: props.fromEmail });
  }
}
