/* 只用原生 DOM；岗位、简历和模型内容都按文本显示，不能成为网页代码。 */
const byId = id => document.getElementById(id);
let currentRun = null;
let streamController = null;
const statusNames = {QUEUED:"排队中",RUNNING:"执行中",PAUSED:"等待人工处理",FAILED:"执行失败，可恢复",COMPLETED:"已完成",PENDING:"待审批",APPROVED:"已批准",REJECTED:"已拒绝",SUCCEEDED:"已执行",UNCERTAIN:"结果不确定，请人工核查",EXECUTING:"执行中，请勿重发"};
function element(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}
function message(text, error=false) {
  byId("message").textContent = text;
  byId("message").className = error ? "error" : "";
}
async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{"X-JobPilot-Token":byId("token").value.trim(),"Content-Type":"application/json",...(options.headers||{})}});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `请求失败（${response.status}），请检查资料格式与配置。`);
  }
  return response;
}
async function guarded(action, button) {
  if (button) button.disabled = true;
  try { await action(); } catch (error) { message(error.message,true); }
  finally { if (button) button.disabled = false; }
}
function showMatch(parent, match) {
  for (const [key,label,style] of [["matched_skills","已具备",""],["partial_skills","学习中","partial"],["missing_skills","未提供证据","missing"]]) {
    const line = element("div"); line.append(element("span",label+"：","hint"));
    for (const skill of match[key] || []) line.append(element("span",skill,"skill "+style));
    parent.append(line);
  }
  const evidence = element("details"); evidence.append(element("summary","查看 JD 引用与候选人原文证据"));
  for (const item of match.evidence || []) evidence.append(element("p",`${item.requirement}\n岗位引用：${item.jd_quote}\n候选人证据：${item.candidate_evidence || "无"}`,"evidence"));
  parent.append(evidence);
  for (const risk of match.risks || []) parent.append(element("p",risk,"hint"));
}
function showState(run) {
  byId("run-status").textContent = statusNames[run.status] || run.status;
  byId("run-id").textContent = `任务 ${run.id} · ${run.source} / ${run.mode}`;
  byId("run-detail").replaceChildren();
  const state = run.snapshot || {};
  byId("run-detail").append(element("p",`已处理 ${state.index || 0} / ${(state.jobs || []).length} 个岗位`,"hint"));
  if (run.error) byId("run-detail").append(element("p",run.error));
  for (const item of run.interrupts || []) if (["browser","action_recovery"].includes(item.kind)) byId("run-detail").append(element("p",item.message));
  byId("resume").hidden = !["PAUSED","FAILED","RUNNING"].includes(run.status);
  const results = byId("results"); results.replaceChildren();
  const rows = [...(state.results || [])];
  if (state.match && state.jobs && state.index < state.jobs.length) rows.push({job:state.jobs[state.index],match:state.match,outcome:"审阅中"});
  for (const row of rows) {
    const card = element("article",undefined,"result");
    card.append(element("h3",row.job.title), element("p",`${row.job.company} · ${row.job.city || "城市未注明"}`,"hint"));
    showMatch(card,row.match); card.append(element("p",statusNames[row.outcome] || row.outcome,"hint")); results.append(card);
  }
  if (!rows.length) results.append(element("p","等待岗位分析","muted"));
}
async function showActions() {
  const runId = currentRun;
  const actions = await (await api(`/api/actions?run_id=${encodeURIComponent(runId)}`)).json();
  if (runId !== currentRun) return;
  const container = byId("actions"); container.replaceChildren();
  for (const action of actions) {
    const p = action.payload; const card = element("article",undefined,"action");
    card.dataset.actionId=action.id; card.dataset.status=action.status;
    card.append(element("span",`${p.simulated ? "模拟动作" : "真实平台动作"} · ${statusNames[action.status]}`,"badge"),element("h3",p.job.title),element("p",`${p.job.company} · ${p.job.source} · 候选人：${p.candidate.name}`,"hint"));
    const link = element("a","查看岗位原页"); link.href=p.job.url; link.target="_blank"; link.rel="noopener noreferrer"; card.append(link);
    card.append(element("p",p.content,"draft"),element("p","审批摘要："+action.digest,"digest"));
    if (action.receipt) card.append(element("p",action.receipt,"digest"));
    if (["EXECUTING","UNCERTAIN"].includes(action.status)) {
      card.append(element("p","请先在平台人工核查此消息。若任务仍在执行，系统会拒绝修改结果。","hint"));
      const note = element("textarea"); note.placeholder="填写核查依据，例如收件人、时间及平台显示的结果（至少五个字）";
      note.maxLength=1000; note.setAttribute("aria-label","发送结果核查依据"); card.append(note);
      const controls = element("div",undefined,"row");
      for (const sent of [true,false]) {
        const button = element("button",sent ? "已人工确认送达" : "确认未发送，结束此动作","secondary");
        button.addEventListener("click",()=>guarded(async()=>{
          if(note.value.trim().length<5)throw new Error("请先填写至少五个字的核查依据。");
          await api(`/api/actions/${action.id}/resolve`,{method:"POST",body:JSON.stringify({digest:action.digest,sent,note:note.value.trim()})});
          message("已保存人工核查结果，没有重新发送。可以恢复任务。"); await selectRun(action.run_id);
        },button)); controls.append(button);
      }
      card.append(controls);
    }
    if (action.status === "PENDING") {
      const controls = element("div",undefined,"row");
      for (const approve of [true,false]) {
        const button = element("button",approve ? (p.simulated ? "批准本条（模拟）" : "批准此全文并执行") : "拒绝本条",approve ? "" : "reject");
        button.addEventListener("click",() => guarded(async () => {
          for (const control of controls.querySelectorAll("button")) control.disabled=true;
          await api(`/api/actions/${action.id}/decision`,{method:"POST",body:JSON.stringify({digest:action.digest,approve})});
          await api(`/api/runs/${action.run_id}/resume`,{method:"POST"});
          message(approve ? "已批准本条，任务将继续。" : "已拒绝本条，继续分析下一岗位。");
          await selectRun(action.run_id);
        },button)); controls.append(button);
      }
      card.append(controls);
    }
    container.append(card);
  }
  if (!actions.length) container.append(element("p","暂无待审草稿。未批准的消息不会发送。","empty"));
}
async function refreshRuns() {
  const runs = await (await api("/api/runs")).json();
  byId("runs").replaceChildren();
  for (const run of runs.slice().reverse()) {
    const button = element("button",`${statusNames[run.status]} · ${run.source}\n${run.id.slice(0,8)}`);
    button.addEventListener("click",() => guarded(() => selectRun(run.id))); byId("runs").append(button);
  }
}
async function watchRun(runId) {
  if (streamController) streamController.abort();
  const controller=new AbortController();
  streamController=controller;
  let failures=0;
  // 服务端会定期结束状态流；只要任务仍在执行，就取新快照并续接。
  while (currentRun===runId && !controller.signal.aborted) {
    try {
      const response=await api(`/api/runs/${runId}/events`,{signal:controller.signal});
      const reader=response.body.getReader(); const decoder=new TextDecoder(); let buffer="";
      while (true) {
        const {value,done}=await reader.read(); if(done)break;
        buffer+=decoder.decode(value,{stream:true});
        let position;
        while ((position=buffer.indexOf("\n\n"))>=0) {
          const block=buffer.slice(0,position); buffer=buffer.slice(position+2);
          const line=block.split("\n").find(item=>item.startsWith("data: "));
          if(line && currentRun===runId && !controller.signal.aborted) {
            showState(JSON.parse(line.slice(6))); await showActions();
          }
        }
      }
      if(currentRun!==runId || controller.signal.aborted)return;
      const run=await (await api(`/api/runs/${runId}`,{signal:controller.signal})).json();
      if(currentRun!==runId || controller.signal.aborted)return;
      showState(run); await showActions(); await refreshRuns();
      if(["PAUSED","FAILED","COMPLETED"].includes(run.status))return;
      failures=0;
    } catch(error) {
      if(controller.signal.aborted || currentRun!==runId)return;
      failures+=1;
      if(failures>=3){message("状态连接连续失败，请刷新任务列表后重新选择任务。已保存的进度不会丢失。",true);return;}
    }
    // 只重连只读状态查询，不重复提交任务、审批或发送操作。
    await new Promise(resolve=>setTimeout(resolve,1000));
  }
}
async function selectRun(runId) {
  currentRun=runId;
  if(streamController)streamController.abort();
  const run=await (await api(`/api/runs/${runId}`)).json();
  if(currentRun!==runId)return;
  showState(run); await showActions();
  if(currentRun===runId)void watchRun(runId);
}
byId("example").onclick=()=>guarded(async()=>{byId("profile").value=JSON.stringify(await (await api("/api/candidate-example")).json(),null,2); message("已载入虚构示例，仅用于演示。请勿把示例经历当成自己的经历。");},byId("example"));
byId("profile-file").onchange=event=>guarded(async()=>{const file=event.target.files[0]; if(!file)return; if(file.size>500000)throw new Error("资料文件过大"); byId("profile").value=JSON.stringify(JSON.parse(await file.text()),null,2); message("资料已载入页面，开始任务后保存到本机数据库。");});
byId("start").onclick=()=>guarded(async()=>{
  const candidate=JSON.parse(byId("profile").value); const query=byId("query").value.trim();
  const result=await (await api("/api/runs",{method:"POST",body:JSON.stringify({candidate,queries:query?[query]:[],source:byId("source").value,mode:byId("mode").value})})).json();
  message("任务已创建。草稿生成后会等待你逐条审批。"); await refreshRuns(); await selectRun(result.id);
},byId("start"));
byId("refresh").onclick=()=>guarded(refreshRuns,byId("refresh"));
byId("resume").onclick=()=>guarded(async()=>{await api(`/api/runs/${currentRun}/resume`,{method:"POST"}); await selectRun(currentRun);},byId("resume"));
