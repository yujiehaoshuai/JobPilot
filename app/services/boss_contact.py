"""BOSS 批量联系：复用 PendingAction，只在本机用户批准后发放单次执行许可。"""

import hashlib
import secrets
from datetime import UTC, datetime
from filelock import FileLock
from app.models.action import ActionPayload
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.exceptions import ConfirmationRequiredError, InvalidTransitionError


CONTACT_NOTICE = ("点击此岗位的“立即沟通”。BOSS 可能向招聘方发送你在该账号中设置的默认招呼，"
                  "并按网站规则展示在线简历。助手无法提前读取默认招呼正文，请先到 BOSS 核对。"
                  "本操作不发送 JobPilot 的 AI 草稿，也不上传附件简历。")


class BossContactService:
    """单机批量队列使用既有动作表，无需额外数据库或后台发送线程。"""

    def __init__(self, actions, runs, tracker, data_dir):
        self.actions, self.runs, self.tracker = actions, runs, tracker
        self.data_dir = data_dir
        self.lock = FileLock(str(data_dir / "boss-contact.lock"))

    def prepare(self, run_id, job_ids):
        """从已保存的搜索结果准备操作，忽略前端自报的标题、公司和正文。

        同一岗位已有联系记录时复用或跳过，防止再次搜索后重复联系。
        此方法只保存 PENDING，既不批准，也不向扩展发放执行许可。
        """
        run = self.runs.get(run_id)
        if run["source"] != "boss" or run["status"] != "COMPLETED" or run.get("interrupts"):
            raise InvalidTransitionError("请先完成 BOSS 岗位搜索和匹配，再选择要联系的岗位")
        profile = CandidateProfile.model_validate(run["snapshot"]["candidate"])
        rows = {row["job"]["id"]: row for row in run["snapshot"].get("results", [])}
        if not set(job_ids) <= rows.keys():
            raise InvalidTransitionError("只能选择这次搜索结果中的岗位")
        prepared, skipped = [], []
        with self.lock:
            existing = self.actions.list()
            for job_id in dict.fromkeys(job_ids):
                job = JobPosting.model_validate(rows[job_id]["job"])
                duplicate = next((a for a in existing if a.payload.kind == "boss_start_chat"
                    and a.payload.job.source_job_id == job.source_job_id
                    and (a.status != "REJECTED" or a.run_id == run_id)), None)
                if duplicate:
                    if duplicate.run_id == run_id:
                        prepared.append(duplicate)
                    else:
                        skipped.append({"job_id":job_id,"reason":"此岗位已有联系记录或待处理操作，已跳过以避免重复联系"})
                    continue
                payload = ActionPayload(kind="boss_start_chat", candidate=profile, job=job,
                    content=CONTACT_NOTICE, evidence_ids=[], simulated=False)
                action = self.actions.prepare(run_id, payload)
                prepared.append(action)
                existing.append(action)
        return {"actions":prepared,"skipped":skipped,"notice":CONTACT_NOTICE}

    def decide(self, decisions, approve, acknowledged):
        """用户核对副作用后整批决定；任一摘要失效则整批回滚。"""
        if approve and not acknowledged:
            raise ConfirmationRequiredError("请先确认 BOSS 账号、默认招呼和在线简历，再批准所选岗位")
        if len({item.id for item in decisions}) != len(decisions):
            raise ConfirmationRequiredError("同一操作不能重复出现在批次中")
        for item in decisions:
            if self.actions.get(item.id).payload.kind != "boss_start_chat":
                raise ConfirmationRequiredError("批量入口只能处理 BOSS 联系操作")
        return self.actions.decide_many([(item.id,item.digest) for item in decisions], approve, "authenticated-local-user")

    def list(self, run_id=None):
        """执行许可超时只能进入待核查，服务或面板重启不能导致自动重发。"""
        result = []
        for action in self.actions.list(run_id):
            if action.payload.kind != "boss_start_chat":
                continue
            if action.status == "EXECUTING" and action.execution_started_at and (
                    datetime.now(UTC) - action.execution_started_at).total_seconds() > 90:
                try:
                    action = self.actions.transition(action.id,"EXECUTING","UNCERTAIN",
                        receipt="执行许可已发出，但没有收到可靠回执，请到 BOSS 核查；不会自动重发")
                except InvalidTransitionError:
                    action = self.actions.get(action.id)
            result.append(action)
            self.sync_tracker(action)
        return result

    def next(self):
        """串行处理获批岗位；有未核查结果时，其他批次也一起等待。"""
        actions = self.list()
        # 任何不确定结果或人工暂停都会阻止后面的批量动作，避免连续误操作。
        if any(a.status in {"EXECUTING","UNCERTAIN"} or a.status == "APPROVED" and a.execution_paused for a in actions):
            return None
        approved = sorted((a for a in actions if a.status == "APPROVED"), key=lambda a:a.created_at)
        return self.public(approved[0]) if approved else None

    @staticmethod
    def public(action):
        """扩展只得到目标和操作摘要，不得到整份简历或主 API 权限。"""
        job = action.payload.job
        return dict(id=action.id,digest=action.digest,job_id=job.source_job_id,url=job.url,
                    title=job.title,company=job.company,kind=action.payload.kind)

    def authorize(self, action_id, digest, owner, observed):
        """对照浏览器刚读到的岗位，只为已批准的队首动作发一次短期许可。"""
        with self.lock:
            next_action = self.next()
            if not next_action or next_action["id"] != action_id or next_action["digest"] != digest:
                raise ConfirmationRequiredError("操作尚未批准、已经领取或队列已暂停")
            action = self.actions.get(action_id)
            job = action.payload.job
            if (observed.job_id != job.source_job_id or observed.title.strip() != job.title.strip()
                    or observed.company.strip() != job.company.strip() or observed.button != "立即沟通"):
                raise ConfirmationRequiredError("当前网页与批准的岗位或操作不一致，禁止点击")
            token = secrets.token_urlsafe(32)
            started = datetime.now(UTC)
            self.actions.transition(action_id,"APPROVED","EXECUTING",execution_owner=owner,
                execution_started_at=started,execution_token_hash=hashlib.sha256(token.encode()).hexdigest())
        return dict(token=token,expires_at=int(started.timestamp()*1000)+15000,**self.public(action))

    def defer(self, action_id, digest, message):
        """尚未点击时保留批准并暂停，等待用户处理登录或页面问题。"""
        action = self.actions.get(action_id)
        if action.payload.kind != "boss_start_chat" or action.digest != digest:
            raise ConfirmationRequiredError("操作摘要不一致")
        return self.actions.transition(action_id,"APPROVED","APPROVED",execution_paused=True,receipt=message)

    def resume(self, action_id, digest):
        """人工继续只解除点击前的暂停，不能重新执行已领取的动作。"""
        action = self.actions.get(action_id)
        if action.payload.kind != "boss_start_chat" or action.digest != digest:
            raise ConfirmationRequiredError("操作摘要不一致")
        return self.actions.transition(action_id,"APPROVED","APPROVED",execution_paused=False,receipt=None)

    def finish(self, action_id, owner, token, confirmed):
        """只接受原执行者的回执；没有可靠确认时，等待人工核查。"""
        action = self.actions.get(action_id)
        if (action.payload.kind != "boss_start_chat" or action.execution_owner != owner
                or not secrets.compare_digest(action.execution_token_hash or "",hashlib.sha256(token.encode()).hexdigest())):
            raise ConfirmationRequiredError("回执与执行许可不匹配")
        if action.status in {"SUCCEEDED","UNCERTAIN"}:
            self.sync_tracker(action)
            return action  # 回执可以重复传输，但不再次点击。
        action = self.actions.transition(action_id,"EXECUTING","SUCCEEDED" if confirmed else "UNCERTAIN",
            receipt="原岗位显示“继续沟通”，已发起联系；不代表附件简历已投递" if confirmed else "未得到可靠页面确认，请人工核查，禁止自动重试")
        self.sync_tracker(action)
        return action

    def resolve(self, action_id, digest, sent, note):
        """只有执行窗口结束后才能人工核查，避免用户取消时浏览器仍在点击。"""
        from app.services.action_service import resolve_after_review
        with self.lock:
            self.list()  # 先将超过 90 秒仍无回执的许可转为待核查。
            if self.actions.get(action_id).status != "UNCERTAIN":
                raise InvalidTransitionError("执行尚未结束或已有明确结果，请等待待核查状态")
            action = resolve_after_review(self.actions, self.data_dir,
                action_id, digest, sent, note, "authenticated-local-user")
            self.sync_tracker(action)
            return action

    def sync_tracker(self, action):
        """明确确认联系后才更新 Tracker，保留已进入面试等后续状态的记录。"""
        if action.status != "SUCCEEDED" or action.payload.kind != "boss_start_chat":
            return
        with self.lock:
            application = self.tracker.track(action.payload.candidate.id,action.payload.job.id)
            stages = ["NEW","ANALYZED","SHORTLISTED","CONTACT_READY","CONTACTED"]
            if application.status in stages:
                for status in stages[stages.index(application.status)+1:]:
                    self.tracker.update_status(application.id,status,confirmed=True)
