"""新搜索沿用同一 LangGraph；失败恢复不能重新提炼或重复生成动作。"""

import time
import pytest
from fastapi.testclient import TestClient
from app.api.server import create_app
from app.exceptions import LLMError
from app.llm.offline import OfflineLLMClient
from app.models.search import ResumeSearch
from app.workflow.runtime import open_graph, graph_config


class Source:
    def __init__(self,jobs): self.jobs=jobs
    def search_jobs(self,queries): return self.jobs


def incoming():
    body=ResumeSearch(text="虚构同学在课程项目中使用 Python 编写工具。",intent="后端",source="mock",mode="offline",available_days_per_week=3)
    return dict(run_id="ranked",source="mock",mode="offline",ranking=True,analysis_only=True,queries=[],resume_search=body.model_dump(mode="json"))


def test_top_five_review_resumes_without_repeating_resume_or_finished_jobs(tmp_path,make_job):
    calls=[]
    class FailReview(OfflineLLMClient):
        def complete(self,task,*args):
            calls.append(task)
            if task=="deep_review" and calls.count(task)==2: raise LLMError("模拟第二条详细分析失败")
            return super().complete(task,*args)
    jobs=[make_job(id=f"job-{i}",source_job_id=str(i),description="需要 Python",url=f"https://example.com/jobs/{i}",
                   employment_type="internship",required_days_per_week=5) for i in range(7)]
    config=graph_config("ranked")
    with open_graph(tmp_path,adapter=Source(jobs),client=FailReview()) as (graph,actions):
        with pytest.raises(LLMError): graph.invoke(incoming(),config)
        state=graph.get_state(config)
        assert state.next == ("refine",) and state.values["review_index"]==1
        assert len(state.values["results"])==7 and not actions.list()
    assert calls.count("resume")==1 and calls.count("search_analyze")==7
    class ResumeOnly(OfflineLLMClient):
        def complete(self,task,*args):
            assert task=="deep_review", "恢复不应重跑简历或已分析岗位"
            return super().complete(task,*args)
    with open_graph(tmp_path,adapter=Source(jobs),client=ResumeOnly()) as (graph,actions):
        graph.invoke(None,config)
        state=graph.get_state(config).values
        assert state["status"]=="COMPLETED" and state["review_index"]==5
        assert sum("deep_review" in row for row in state["results"])==5
        assert not actions.list()


def test_one_request_creates_a_ranked_readonly_task(tmp_path):
    with TestClient(create_app(tmp_path,token="test")) as client:
        body=incoming()["resume_search"]
        assert client.post("/api/search",json=body).status_code==401
        client.headers["X-JobPilot-Token"]="test"
        response=client.post("/api/search",json=body)
        assert response.status_code==202
        run_id=response.json()["id"]
        for _ in range(200):
            run=client.get("/api/runs/"+run_id).json()
            if run["status"] in {"COMPLETED","FAILED","PAUSED"}:break
            time.sleep(.05)
        assert run["status"]=="COMPLETED",run.get("error")
        assert run["snapshot"]["candidate"]["skills"]
        assert run["snapshot"]["ranking"] and run["snapshot"]["analysis_only"]
        assert client.get("/api/actions?run_id="+run_id).json()==[]
