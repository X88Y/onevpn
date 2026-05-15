from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreateServerRequest(BaseModel):
    host: str = Field(..., min_length=1)
    login: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    sshPort: Optional[int] = Field(default=22, ge=1, le=65535)
    label: Optional[str] = None
    countryCode: Optional[str] = None


class CreateServerResponse(BaseModel):
    serverId: str
    jobId: str


class InstallJobResponse(BaseModel):
    jobId: str
    serverId: str
    status: str
    progress: Optional[str] = None
    error: Optional[str] = None
    panelUrl: Optional[str] = None
    panelUser: Optional[str] = None
    panelPassword: Optional[str] = None
    log: Optional[str] = None


class ServerSummary(BaseModel):
    id: str
    host: str
    label: Optional[str] = None
    countryCode: Optional[str] = None
    status: str
    panelUrl: Optional[str] = None
    clientCount: int = 0
    addedAt: Optional[str] = None
    lastHealthAt: Optional[str] = None


class ProvisionRequest(BaseModel):
    userUid: str = Field(..., min_length=1)


class ProvisionResponse(BaseModel):
    subId: str
    subscriptionUrl: str
    perServer: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class RegenerateResponse(ProvisionResponse):
    regeneratedAt: Optional[str] = None
    regenerationCount: int = 0


class TrafficPerServer(BaseModel):
    up: int = 0
    down: int = 0
    total: int = 0


class TrafficResponse(BaseModel):
    userUid: str
    up: int = 0
    down: int = 0
    total: int = 0
    syncedAt: Optional[str] = None
    perServer: Dict[str, TrafficPerServer] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    retryAfter: Optional[int] = None


class ServerListResponse(BaseModel):
    total: int
    servers: List[ServerSummary]
