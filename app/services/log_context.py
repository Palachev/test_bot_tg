from __future__ import annotations

from contextvars import ContextVar, Token

RequestContext = dict[str, str]

_request_context: ContextVar[RequestContext] = ContextVar("request_context", default={})


def set_request_context(context: RequestContext) -> Token:
    return _request_context.set(context)


def reset_request_context(token: Token) -> None:
    _request_context.reset(token)


def get_request_context() -> RequestContext:
    return _request_context.get()
