"""FastAPI service. Start with python -m uvicorn src.api:app --workers 1."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .serving import MAX_BATCH_CHARS, MAX_BATCH_SIZE, MAX_TEXT_CHARS, Predictor

ROOT = Path(__file__).resolve().parents[1]
Text = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=MAX_TEXT_CHARS)]
logger = logging.getLogger('vitoxic.api')


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: Text


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    texts: list[Text] = Field(min_length=1, max_length=MAX_BATCH_SIZE)

    @model_validator(mode='after')
    def total_limit(self):
        if sum(map(len, self.texts)) > MAX_BATCH_CHARS:
            raise ValueError(f'Batch exceeds {MAX_BATCH_CHARS} characters')
        return self


class Prediction(BaseModel):
    label_id: int = Field(ge=0, le=2)
    label: Literal['CLEAN', 'OFFENSIVE', 'HATE']
    confidence: float = Field(ge=0, le=1)
    probabilities: dict[str, float]
    token_count: int
    truncated: bool


class BatchResponse(BaseModel):
    predictions: list[Prediction]
    count: int


class BodyLimit:
    """Bound bytes before JSON decoding, including chunked requests."""
    def __init__(self, app, limit=131072):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in {'POST', 'PUT', 'PATCH'}:
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > self.limit:
                response = JSONResponse({'detail': 'Request body exceeds 128 KiB'}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(message.get('body', b''))
            if not message.get('more_body', False):
                break
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)


def create_app(predictor_factory=None):
    if predictor_factory is None:
        def predictor_factory():
            return Predictor(os.environ.get('VITOXIC_BUNDLE', ROOT / 'outputs/stage4/bundle'),
                             device=os.environ.get('VITOXIC_DEVICE', 'cpu'),
                             threads=int(os.environ.get('VITOXIC_THREADS', '4')))

    @asynccontextmanager
    async def lifespan(app):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='vitoxic-inference')
        app.state.executor = executor
        app.state.ready, app.state.busy = False, False
        try:
            app.state.predictor = await asyncio.get_running_loop().run_in_executor(executor, predictor_factory)
            app.state.ready = True
            yield
        finally:
            app.state.ready = False
            executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title='ViToxic Analyzer', version='1.0.0', lifespan=lifespan,
                  description='Vietnamese CLEAN / OFFENSIVE / HATE classifier. '
                              'Confidence is uncalibrated softmax; model is a research demo.')
    app.add_middleware(BodyLimit)
    app.state.ready, app.state.busy = False, False

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not echo the user's potentially sensitive text in validation errors.
        return JSONResponse(status_code=422, content={'detail': [
            {'loc': list(err['loc']), 'type': err['type'], 'msg': err['msg']} for err in exc.errors()]})

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    @app.get('/ready')
    async def ready():
        if not app.state.ready:
            raise HTTPException(503, 'Model not ready')
        return {'status': 'ready', 'busy': app.state.busy}

    @app.get('/model')
    async def model():
        if not app.state.ready:
            raise HTTPException(503, 'Model not ready')
        return app.state.predictor.metadata()

    async def infer(texts):
        if not app.state.ready:
            raise HTTPException(503, 'Model not ready')
        if app.state.busy:
            raise HTTPException(503, 'Inference busy; retry later', headers={'Retry-After': '1'})
        app.state.busy = True
        # No await between admission check and setting busy: one request per process.
        future = asyncio.get_running_loop().run_in_executor(app.state.executor, app.state.predictor.predict, texts)
        def release(completed):
            app.state.busy = False
            # Retrieve failures even if the client disconnected/cancelled its request.
            if not completed.cancelled():
                completed.exception()
        future.add_done_callback(release)
        try:
            return await asyncio.shield(future)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            logger.error('Inference failed (%s)', type(exc).__name__)
            raise HTTPException(500, 'Inference failed') from exc

    @app.post('/predict', response_model=Prediction)
    async def predict(payload: PredictRequest):
        return (await infer([payload.text]))[0]

    @app.post('/predict/batch', response_model=BatchResponse)
    async def batch(payload: BatchRequest):
        predictions = await infer(payload.texts)
        return {'predictions': predictions, 'count': len(predictions)}

    return app


app = create_app()
