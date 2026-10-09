"""批量联系的本机审批接口与扩展执行接口，二者权限严格分开。"""

from uuid import UUID
from fastapi import Depends, HTTPException
from pydantic import Field
from app.models.base import DomainModel
from app.services.boss_contact import BossContactService


class SelectedJobs(DomainModel):
    job_ids: list[str] = Field(min_length=1,max_length=20)


class ActionRef(DomainModel):
    id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class BatchDecision(DomainModel):
    actions: list[ActionRef] = Field(min_length=1,max_length=20)
    approve: bool = Field(strict=True)
    platform_details_confirmed: bool = Field(default=False,strict=True)


class ObservedContact(DomainModel):
    job_id: str = Field(max_length=200)
    title: str = Field(max_length=500)
    company: str = Field(max_length=1000)
    button: str = Field(max_length=30)


class ContactPermit(DomainModel):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed: ObservedContact


class ContactPause(DomainModel):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    message: str = Field(min_length=1,max_length=300)


class ContactReceipt(DomainModel):
    token: str = Field(min_length=40,max_length=60)
    confirmed: bool = Field(strict=True)


def install_contact_routes(app,data_dir,runs,actions,tracker,auth,bridge_auth,database_url=None):
    service = BossContactService(actions,runs,tracker,data_dir,database_url)
    app.state.boss_contacts = service

    @app.post("/api/runs/{run_id}/boss-actions",dependencies=auth)
    def prepare(run_id: UUID,body: SelectedJobs):
        return service.prepare(str(run_id),body.job_ids)

    @app.get("/api/boss-actions",dependencies=auth)
    def list_actions(run_id: UUID | None=None):
        return service.list(str(run_id) if run_id else None)

    @app.post("/api/boss-actions/decision",dependencies=auth)
    def decide(body: BatchDecision):
        return service.decide(body.actions,body.approve,body.platform_details_confirmed)

    @app.get("/api/boss-actions/{action_id}/workflow",dependencies=auth)
    def workflow(action_id: UUID):
        return service.workflow(str(action_id))

    @app.post("/api/boss-actions/{action_id}/resume",dependencies=auth)
    def resume(action_id: UUID,body: ActionRef):
        if str(action_id) != body.id:
            raise HTTPException(422,"操作编号不一致")
        return service.resume(str(action_id),body.digest)

    @app.get("/api/boss/contacts/next")
    def next_action(owner: str=Depends(bridge_auth)):
        return {"action":service.next()}

    @app.post("/api/boss/contacts/{action_id}/permit")
    def permit(action_id: UUID,body: ContactPermit,owner: str=Depends(bridge_auth)):
        return service.authorize(str(action_id),body.digest,owner,body.observed)

    @app.post("/api/boss/contacts/{action_id}/pause")
    def pause(action_id: UUID,body: ContactPause,owner: str=Depends(bridge_auth)):
        service.defer(str(action_id),body.digest,body.message)
        return {"paused":True}

    @app.post("/api/boss/contacts/{action_id}/receipt")
    def receipt(action_id: UUID,body: ContactReceipt,owner: str=Depends(bridge_auth)):
        action = service.finish(str(action_id),owner,body.token,body.confirmed)
        return {"status":action.status}
