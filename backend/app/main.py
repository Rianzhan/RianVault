from fastapi import FastAPI

from app.api.routes import conversations, health, imports, memories, messages

app = FastAPI(title="RianVault", version="0.1.0")

app.include_router(health.router)
app.include_router(imports.router)
app.include_router(conversations.router)
app.include_router(messages.router)
app.include_router(memories.router)
