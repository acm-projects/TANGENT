#!/usr/bin/env bash
# Create the send-only IAM user the backend uses to enqueue debates, and print the .env lines for it.
#
#   export AWS_PROFILE=tangent
#   aws sso login --profile tangent
#   bash scripts/setup_aws_runtime.sh            # after `sam deploy` has created the stack
#
# Run it AFTER the stack exists: the queue's ARN is what the policy is scoped to.
# Safe to run again - it reuses the user and only mints a key if there is room for one.
set -euo pipefail

STACK="${STACK:-tangent-debate}"
USER_NAME="${USER_NAME:-tangent-backend-enqueue}"
POLICY_NAME="EnqueueDebatesOnly"

command -v aws >/dev/null || { echo "aws CLI not found"; exit 1; }
command -v jq  >/dev/null || { echo "jq not found: brew install jq"; exit 1; }

echo "account : $(aws sts get-caller-identity --query Account --output text)"
echo "region  : $(aws configure get region || echo '(none set)')"
echo "stack   : $STACK"
echo
read -r -p "Is that the NEW account? [y/N] " ok
[[ "$ok" == "y" || "$ok" == "Y" ]] || { echo "Stopping. Set AWS_PROFILE to the new account's profile."; exit 1; }

# The queue the backend is allowed to write to, and nothing else.
QUEUE_ARN=$(aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='DebateQueueArn'].OutputValue" --output text)
QUEUE_URL=$(aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='DebateQueueUrl'].OutputValue" --output text)
[[ "$QUEUE_ARN" == arn:aws:sqs:* ]] || { echo "Could not read DebateQueueArn from stack '$STACK'. Deploy it first."; exit 1; }
echo "queue   : $QUEUE_ARN"

aws iam get-user --user-name "$USER_NAME" >/dev/null 2>&1 \
    && echo "user    : $USER_NAME (exists)" \
    || { aws iam create-user --user-name "$USER_NAME" >/dev/null; echo "user    : $USER_NAME (created)"; }

# sqs:SendMessage on one queue. No read, no delete, no other service. A leaked key can only enqueue a debate.
aws iam put-user-policy --user-name "$USER_NAME" --policy-name "$POLICY_NAME" --policy-document "$(cat <<JSON
{"Version": "2012-10-17",
 "Statement": [{"Effect": "Allow",
                "Action": ["sqs:SendMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"],
                "Resource": "$QUEUE_ARN"}]}
JSON
)"
echo "policy  : $POLICY_NAME attached (SendMessage only, this queue only)"

# IAM allows two keys per user; refuse to create a third rather than failing halfway.
EXISTING=$(aws iam list-access-keys --user-name "$USER_NAME" --query 'length(AccessKeyMetadata)' --output text)
if [[ "$EXISTING" -ge 2 ]]; then
    echo
    echo "This user already has 2 access keys, which is the IAM limit. Delete an unused one first:"
    aws iam list-access-keys --user-name "$USER_NAME" \
        --query 'AccessKeyMetadata[].{Key:AccessKeyId,Status:Status,Created:CreateDate}' --output table
    echo "  aws iam delete-access-key --user-name $USER_NAME --access-key-id <KEY>"
    exit 1
fi

KEY_JSON=$(aws iam create-access-key --user-name "$USER_NAME")
AKID=$(jq -r '.AccessKey.AccessKeyId' <<<"$KEY_JSON")
SECRET=$(jq -r '.AccessKey.SecretAccessKey' <<<"$KEY_JSON")
REGION=$(cut -d: -f4 <<<"$QUEUE_ARN")

cat <<ENV

================= put these in backend/.env =================
DEBATE_QUEUE_URL=$QUEUE_URL
AWS_ACCESS_KEY_ID=$AKID
AWS_SECRET_ACCESS_KEY=$SECRET
AWS_DEFAULT_REGION=$REGION
=============================================================

The secret is shown once and AWS will not show it again. Copy it now.
Replace the old account's values; do not keep both.
Check .env is ignored before you commit anything:   git check-ignore -v backend/.env
ENV
