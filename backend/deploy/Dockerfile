# One image for both Lambdas. The function's ImageConfig.Command picks the entry point:
#   debate.pg.handler.handler   (SQS worker)
#   debate.pg.handler.sweeper   (EventBridge sweeper)
FROM public.ecr.aws/lambda/python:3.12

COPY requirements-lambda.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements-lambda.txt

COPY debate/ ${LAMBDA_TASK_ROOT}/debate/

CMD ["debate.pg.handler.handler"]
