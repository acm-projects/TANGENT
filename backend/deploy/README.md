# Deploying the debate worker to AWS

Prereqs: AWS CLI + SAM CLI + Docker, an AWS account/region, and the database already set up
(`python scripts/setup_db.py --ddl --saver`).

1. From the repo root (the folder that contains `debate/`, `deploy/`, `requirements-lambda.txt`):
       sam build -t deploy/template.yaml
       sam deploy --guided --template-file .aws-sam/build/template.yaml
   `--guided` asks for the parameters (database URL, keys, cost cap) and creates an ECR repo for the image.
   Parameters marked NoEcho are still visible in the Lambda configuration to anyone with console access. For
   production move the secrets to Secrets Manager and read them at start-up.
2. Copy the `DebateQueueUrl` output into the backend's environment as `DEBATE_QUEUE_URL`, and give the backend's
   IAM identity `sqs:SendMessage` on the queue.
3. Smoke test the worker without the backend: start a debate through the API, or insert a row and send
       aws sqs send-message --queue-url <url> --message-group-id <debate_id> \
         --message-deduplication-id $(uuidgen) --message-body '{"debate_id":"<debate_id>"}'
4. Watch CloudWatch Logs for the two functions. Failed messages land in the DLQ after 5 receives.

What the settings mean:
- Worker timeout 900 s (the Lambda maximum). The runner stops at a safe boundary before time runs out, saves its
  checkpoint, and re-queues itself. A debate is therefore a chain of invocations, not one long call.
- `WorkerMaxConcurrency` caps simultaneous debates (and so your OpenRouter spend rate).
- `MaxCostUsd` stops a debate and judges with what it has once the cap is passed.
- The sweeper runs every 2 minutes: re-queues stuck debates, fails overdue ones, purges old events and checkpoints.

Local development without AWS: use `InlineEnqueuer` (debate/pg/local.py), see integration/README.md.
