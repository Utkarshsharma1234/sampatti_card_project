import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from . import models
from .database import engine
from .routers import user, cashfree, webhook
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.getcwd(), 'static')

app.mount("/static", StaticFiles(directory=static_dir), name="static")

models.Base.metadata.create_all(engine)

app.include_router(user.router)
app.include_router(cashfree.router)
app.include_router(webhook.router)