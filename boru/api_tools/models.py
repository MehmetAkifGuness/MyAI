from dataclasses import dataclass
from enum import Enum


class ApiMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


@dataclass(frozen=True, slots=True)
class ApiRequest:
    method: ApiMethod
    url: str
    body: str = ""


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status_code: int
    content_type: str
    body: str
    truncated: bool = False
