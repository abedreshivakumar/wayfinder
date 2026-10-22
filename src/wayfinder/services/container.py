"""Building the services once, and shutting them down cleanly."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from wayfinder.agents.llm import LLM
from wayfinder.agents.orchestrator import AgentRunner
from wayfinder.core.config import Settings
from wayfinder.languages import python as _python  # noqa: F401 - importing registers it
from wayfinder.services.analysis import AnalysisService
from wayfinder.services.context import ServiceContext
from wayfinder.services.drift import DriftService
from wayfinder.services.driver_pool import DriverPool
from wayfinder.services.explanation import ExplanationService
from wayfinder.services.model_access import ModelAccess
from wayfinder.services.orchestration import OrchestrationService
from wayfinder.services.overview import OverviewService
from wayfinder.services.purposes import PurposeService
from wayfinder.services.tracing import TraceService
from wayfinder.storage.repository import GraphRepository


@dataclass
class Services:
    """Everything the API and MCP layers call - and the only thing they need to hold."""

    analysis: AnalysisService
    explanation: ExplanationService
    drift: DriftService
    orchestration: OrchestrationService
    tracing: TraceService
    overview: OverviewService
    purposes: PurposeService
    pool: DriverPool
    _ctx: ServiceContext

    def close(self) -> None:
        with self._ctx.lock:
            self.pool.close()  # stops the pyright processes
            self._ctx.store.close()


def build_services(
    settings: Settings | None = None, llm: LLM | None = None, runner: AgentRunner | None = None
) -> Services:
    """`settings` defaults to the environment; `llm` and `runner` let a caller (or a test)
    supply the model client and the Orchestrator's runner instead of the defaults."""
    settings = settings or Settings.from_env()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    ctx = ServiceContext(
        settings=settings,
        store=GraphRepository(settings.db_path),
        pool=DriverPool(),
        lock=threading.Lock(),
    )
    access = ModelAccess(settings, llm)  # shared: one rate limiter across every model-using service
    analysis = AnalysisService(ctx)
    overview = OverviewService(ctx, analysis)
    explanation = ExplanationService(ctx, analysis, access, overview)
    drift = DriftService(ctx, analysis, access)
    return Services(
        analysis=analysis,
        explanation=explanation,
        drift=drift,
        orchestration=OrchestrationService(ctx, analysis, explanation, drift, access, runner),
        tracing=TraceService(ctx, analysis),
        overview=overview,
        purposes=PurposeService(ctx, overview, access),
        pool=ctx.pool,
        _ctx=ctx,
    )
