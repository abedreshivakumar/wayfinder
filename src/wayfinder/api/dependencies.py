"""What routes ask FastAPI to hand them."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from wayfinder.services import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]
