"""AWS Lambda entrypoint. Set the function handler to `lambda_handler.handler`."""

from mangum import Mangum

from app.main import app

handler = Mangum(app, lifespan="off")
