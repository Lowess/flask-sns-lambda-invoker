# flask-sns-lambda-invoker

Tiny Flask app to plug behind [Ngrok](https://ngrok.com/) in order to automatically subscribes to a given SNS topic and trigger a local python lambda function

## :star2: App configuration from environment variable

| Env var          | Required | Defaults                           | Description                                                                                                       |
| ---------------- | -------- | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `SNS_TOPIC_ARN`  | `True`   |                                    | The SNS Topic ARN the webapp will subscribe to                                                                    |
| `LAMBDA_SRC`     | `False`  | folder where the app is run from   | The absolute path to the lambda folder that contains the handler                                                  |
| `LAMBDA_HANDLER` | `False`  | `app.default_lambda_handler`       | The `<module>.<function>` to load as the lambda handler which will be passed the `payload` and an empty `context` |
| `NGROK_ENDPOINT` | `False`  | `http://host.docker.internal:4040` | The endpoint where your `Ngrok` server is running                                                                 |



## :whale: Docker usage

```bash
docker run \
  -p 5000:5000 \
  -e LAMBDA_REQUIREMENTS=/requirements.txt \
  -e SNS_TOPIC_ARN=arn:aws:sns:us-east-1:012345678910:sns-lambda-dev \
  -e NGROK_ENDPOINT=http://host.docker.internal:4041 \
  -v <path/to/lambda/requirements>:/requirements.txt \
  -v <path/to/lambda/src>:/lambda \
  -v ~/.aws:/root/.aws \
  -v ~/.pip:/root/.pip \
  -v lambda-env:/lambda-env \
  lowess/flask-sns-lambda-invoker --host=0.0.0.0
```