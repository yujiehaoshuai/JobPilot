/* 只用原生 DOM；岗位、简历和模型内容都按文本显示，不能成为网页代码。 */
const byId = id => document.getElementById(id);
let currentRun = null;
let localAccess = "";
const sourceNames = {mock:"示例岗位",shixiseng:"实习僧",boss:"BOSS 直聘",nowcoder:"牛客"};
const modeNames = {offline:"基础演示，未调用 AI",live:"AI 分析"};
let streamController = null;
const statusNames = {QUEUED:"排队中",RUNNING:"执行中",PAUSED:"等待人工处理",FAILED:"执行失败，可恢复",COMPLETED:"已完成",PENDING:"待审批",APPROVED:"已批准",REJECTED:"已拒绝",SUCCEEDED:"已执行",UNCERTAIN:"结果不确定，请人工核查",EXECUTING:"执行中，请勿重发",NOT_SHORTLISTED:"暂未找到与你经历对应的技能",REJECTED_BY_USER:"你已拒绝这条草稿",SIMULATED_SENT:"已完成模拟发送"};
function element(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}
statusNames.DELETING="清理中，请再次点击清理历史";
function message(text, error=false) {
  byId("message").textContent = text;
  byId("message").className = error ? "error" : "";
}
async function api(path, options={}) {
  if (!localAccess) throw new Error("尚未连接本机程序，请双击 start.cmd 打开页面。");
  const response = await fetch(path, {...options, headers:{"X-JobPilot-Token":localAccess,"Content-Type":"application/json",...(options.headers||{})}});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `操作未完成（${response.status}），请检查填写内容后重试。`);
  }
  return response;
}
async function guarded(action, button) {
  if (button) button.disabled = true;
  try { await action(); } catch (error) { message(error.message,true); }
  finally { if (button) button.disabled = false; }
}
function showMatch(parent, match) {
  if(match.score!==null && match.score!==undefined) {
    parent.append(element("p",`${match.score} / 100 · 匹配参考分`,"score"));
    const parts=element("details");parts.append(element("summary","分数是怎么算的？"));
    for(const [label,value] of Object.entries(match.score_breakdown||{}))parts.append(element("p",`${label}：${value}`,"hint"));
    parts.append(element("p","技能按必需项和加分项加权，学习中的技能算部分符合。分数用于本轮比较，不是录用概率。","hint"));parent.append(parts);
  }
  for (const [key,label,style] of [["matched_skills","已具备",""],["partial_skills","学习中","partial"],["missing_skills","资料中未提到","missing"]]) {
    const line = element("div"); line.append(element("span",label+"：","hint"));
    for (const skill of match[key] || []) line.append(element("span",skill,"skill "+style));
    if(!(match[key] || []).length)line.append(element("span",key==="missing_skills" ? "本次未发现" : "暂无","hint"));
    parent.append(line);
  }
  const evidence = element("details"); evidence.append(element("summary","为什么这样匹配？查看双方原文"));
  for (const item of match.evidence || []) evidence.append(element("p",`${item.requirement}\n岗位引用：${item.jd_quote}\n我的经历：${item.candidate_evidence || "无"}`,"evidence"));
  parent.append(evidence);
  for (const risk of match.risks || []) parent.append(element("p",plainRisk(risk),"hint"));
  for (const note of match.availability_notes || []) parent.append(element("p",note,"availability-note"));
}
function showReview(parent, review) {
  if(!review)return;
  const section=element("div",undefined,"review");section.append(element("strong","前几名的详细分析"));
  for(const point of review.reasons||[]) {
    section.append(element("p",`${point.requirement}：${point.reason}。`));
    section.append(element("p",`岗位原句：${point.jd_quote}\n简历依据：${point.candidate_evidence||"原文未提供，不能视为已掌握"}`,"evidence"));
  }
  for(const quote of review.cautions||[])section.append(element("p",`需要留意的岗位原句：${quote}`,"hint"));
  for(const question of review.questions||[])section.append(element("p",`建议向招聘方确认：${question}`,"hint"));
  parent.append(section);
}
function showState(run) {
  byId("run-status").textContent = statusNames[run.status] || run.status;
  byId("run-id").textContent = `${sourceNames[run.source] || run.source} · ${modeNames[run.mode] || run.mode}`;
  byId("run-detail").replaceChildren();
  const state = run.snapshot || {};
  const analysisOnly = state.analysis_only ?? run.input?.analysis_only ?? false;
  const steps = state.ranking || run.input?.ranking ? ["理解简历", "寻找岗位", "比较评分", "复核前几名"] : analysisOnly ? ["寻找岗位", "按条件筛选", "逐条比较", "保存结果"] : ["搜索 / 过滤", "分析 / 匹配", "草稿 / 审批", "执行 / 跟踪"];
  document.querySelector(".steps").replaceChildren(...steps.map(text => element("span", text)));
  if (state.candidate) byId("run-detail").append(element("p",`本次使用的资料：${state.candidate.name}`,"hint"));
  if(state.ranking && state.candidate) {
    const profile=element("details",undefined,"profile-extract");
    profile.append(element("summary",`已从简历整理 ${state.candidate.skills.length} 项技能 · 查看原文依据`));
    for(const skill of state.candidate.skills)profile.append(element("p",`${skill.skill}：${skill.evidence}`,"evidence"));
    for(const quote of [...state.candidate.education,...state.candidate.projects,...state.candidate.experience])profile.append(element("p",quote,"hint"));
    byId("run-detail").append(profile);
  }
  for(const warning of state.profile_warnings||[])byId("run-detail").append(element("p",warning,"hint"));
  if(state.queries?.length)byId("run-detail").append(element("p",`本次搜索词：${state.queries.join("、")}`,"hint"));
  if(state.search_coverage?.pages)byId("run-detail").append(element("p",`已读取 ${state.search_coverage.pages} 页；${state.search_coverage.complete?"本轮搜索词已到末页，不代表全站岗位。":"还有未覆盖的结果，原因见下方。"}`,"hint"));
  if(state.review_count!==undefined)byId("run-detail").append(element("p",`靠前岗位详细复核：${state.review_index||0} / ${state.review_count}`,"hint"));
  if (state.discovery) {
    const count = state.discovery;
    byId("run-detail").append(element("p",`读取 ${count.received} 条，不符合条件 ${count.rejected} 条，重复 ${count.duplicates} 条，留下 ${count.retained} 条供比较。`,"hint"));
  }
  if (state.analysis_only) byId("run-detail").append(element("p","本次只帮你找工作、比较要求，没有发送消息或投递。","hint"));
  byId("run-detail").append(element("p",`已处理 ${state.index || 0} / ${(state.jobs || []).length} 个岗位`,"hint"));
  if (run.error) byId("run-detail").append(element("p",run.error));
  for (const warning of state.source_warnings || []) byId("run-detail").append(element("p",warning,"hint"));
  for (const item of run.interrupts || []) if (["browser","action_recovery"].includes(item.kind)) byId("run-detail").append(element("p",item.message));
  byId("resume").hidden = !["PAUSED","FAILED","RUNNING","QUEUED"].includes(run.status) || (run.interrupts||[]).some(item=>item.kind==="approval");
  const expand = byId("search-more");
  const limit = run.input?.search_limit || 100;
  expand.hidden = run.status !== "COMPLETED" || !state.ranking || !state.search_coverage?.limit_reached || limit + 50 > 1000;
  expand.dataset.limit = String(limit);
  if(state.ranking)byId("run-detail").append(element("p",`当前读取上限：${limit} 条`,"hint"));
  const results = byId("results"); results.replaceChildren();
  const rows = [...(state.results || [])];
  if (state.match && Object.keys(state.match).length && state.jobs && state.index < state.jobs.length) rows.push({job:state.jobs[state.index],match:state.match,outcome:"分析中"});
  if(state.ranking)rows.sort((a,b)=>(b.match.score??0)-(a.match.score??0));
  const more=element("details");more.append(element("summary",`查看其余 ${Math.max(0,rows.length-5)} 条岗位`));
  for (const [index,row] of rows.entries()) {
    const card = element("article",undefined,"result");
    if(run.source==="boss" && run.status==="COMPLETED")addBossSelection(card,run.id,row.job);
    card.append(element("h3",row.job.title), element("p",`${row.job.company} · ${row.job.city || "城市未注明"}`,"hint"));
    const link = element("a","查看岗位原页"); link.href=row.job.url; link.target="_blank"; link.rel="noopener noreferrer"; card.append(link);
    showMatch(card,row.match);if(index<5)showReview(card,row.deep_review);
    card.append(element("p",row.outcome === "MATCHED" ? "有技能匹配，仍需核对完整要求" : statusNames[row.outcome] || row.outcome,"hint"));
    if(state.ranking&&index>=5)more.append(card);else results.append(card);
  }
  if(state.ranking&&rows.length>5)results.append(more);
  const emptyMessage = state.discovery?.received === 0 ? "没有搜索到岗位，可以换个关键词再试。" : "本轮没有通过规则筛选的岗位，请查看排除原因。";
  if (!rows.length) results.append(element("p",run.status === "COMPLETED" ? emptyMessage : "等待岗位分析","muted"));
  for (const row of state.rejected_jobs || []) {
    const detail = element("details"); detail.append(element("summary",`已排除：${row.job.title} · ${row.job.company}`));
    for (const reason of row.reasons) detail.append(element("p",plainReason(reason),"hint"));
    results.append(detail);
  }
  updateBatchControls(run);
}
async function refreshRuns() {
  const runs = await (await api("/api/runs")).json();
  byId("runs").replaceChildren();
  if(!runs.length)byId("runs").append(element("p","暂无搜索记录","muted"));
  for (const run of runs.slice().reverse()) {
    const button = element("button",`${statusNames[run.status]} · ${sourceNames[run.source] || run.source} · ${modeNames[run.mode] || run.mode}\n${run.snapshot?.candidate?.name || run.input?.candidate?.name || run.input?.resume_search?.intent || "已保存的搜索"}`);
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
            showState(JSON.parse(line.slice(6)));
          }
        }
      }
      if(currentRun!==runId || controller.signal.aborted)return;
      const run=await (await api(`/api/runs/${runId}`,{signal:controller.signal})).json();
      if(currentRun!==runId || controller.signal.aborted)return;
      showState(run); await refreshRuns();
      if(run.status==="PAUSED" && run.source==="boss" && run.input?.analysis_only) {
        const bridge=await(await api(`/api/boss/status?run_id=${runId}`,{signal:controller.signal})).json();
        const task=bridge.task;
        if(task) {
          byId("run-status").textContent=task.status==="paused"?"等待你处理 BOSS 页面":task.status==="ready"?"准备开始匹配":"浏览器正在读取岗位";
          byId("run-detail").append(element("p",`${task.message} · 已处理 ${task.attempted.length} 条、读取 ${task.pages} 页`,"hint"));
          if(!bridge.connected)byId("run-detail").append(element("p","BOSS 助手暂未连接，请保持助手页面打开，或点击左侧“连接 BOSS 助手”。","hint"));
        }
        // 等待浏览器属于可恢复的只读阶段；轮询状态以便自动展示后续 AI 结果。
        await new Promise(resolve=>setTimeout(resolve,2500));continue;
      }
      if(["PAUSED","FAILED","COMPLETED"].includes(run.status)) {
        if(run.status==="COMPLETED"&&byId("message").textContent.startsWith("正在理解简历"))message("搜索和比较已完成，优先看看排名靠前的岗位及时间差距提示。");
        return;
      }
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
  showState(run);
  if(currentRun===runId)void watchRun(runId);
}
function plainReason(text) {
  const exact={"Empty job description":"岗位没有提供完整说明", "Title does not contain a target role or preferred keyword":"岗位名称不包含你填写的岗位方向或偏好关键词"};
  if(exact[text])return exact[text];
  for(const [prefix,label] of [["City outside target cities: ","工作城市不在你的选择范围："],["Excluded role in title: ","属于你排除的岗位："],["Excluded keyword: ","包含你不希望出现的内容："],["Employment type mismatch: ","工作类型与你的要求不符："]]) {
    if(text.startsWith(prefix))return label+text.slice(prefix.length).replace("full_time","全职").replace("internship","实习");
  }
  const duration=text.match(/^Internship requires (\d+) (months|days\/week); candidate available for (\d+)$/);
  if(duration)return `岗位要求${duration[2]==="months" ? "实习" : "每周到岗"} ${duration[1]} ${duration[2]==="months" ? "个月" : "天"}，你填写的是 ${duration[3]} ${duration[2]==="months" ? "个月" : "天"}。`;
  return text;
}
function plainRisk(text) {
  if(text==="离线词表演示结果，尚未执行真实 LLM 语义分析")return "这是基础演示，只识别少量常见技能；选择 AI 分析可进一步读取岗位要求。";
  if(text==="存在未满足的要求，请人工查看 JD")return "有些岗位要求尚未在你的资料中找到依据，请展开原文仔细核对。";
  return text;
}
byId("example").onclick=()=>guarded(async()=>{
  fillExample(await (await api("/api/candidate-example")).json());
  message("示例已填好，点击“帮我找岗位”即可体验简历提炼、评分和排序。");
},byId("example"));
byId("search-form").onsubmit=event=>{
  event.preventDefault();
  void guarded(async()=>{
    const body=readSearchForm();
    if(body.mode==="live"&&!modelConfigured) {
      byId("ai-settings").open=true;byId("model-key").focus();
      throw new Error("请先连接 DeepSeek，或者选择免费的示例演示。");
    }
    if(body.source==="boss")await ensureBossConnected();
    const result=await (await api("/api/search",{method:"POST",body:JSON.stringify(body)})).json();
    message("正在理解简历并寻找岗位，结果会陆续出现。");await refreshRuns();await selectRun(result.id);
  },byId("start"));
};
byId("search-more").onclick=()=>guarded(async()=>{
  const id=currentRun;
  const result=await(await api(`/api/runs/${id}/expand`,{method:"POST",body:JSON.stringify({expected_limit:Number(byId("search-more").dataset.limit)})})).json();
  message(`读取上限已增加到 ${result.search_limit} 条，已有结果保留。`);
  await selectRun(id);
},byId("search-more"));
byId("refresh").onclick=()=>guarded(refreshRuns,byId("refresh"));
byId("clear-history").onclick=()=>guarded(async()=>{
  if(!window.confirm("清理已结束的搜索结果和简历副本？清理后无法恢复。进行中、等待处理和有联系记录的任务会保留。"))return;
  const result=await(await api("/api/runs/history",{method:"DELETE"})).json();
  if(result.deleted_ids.includes(currentRun)) {
    currentRun=null;if(streamController)streamController.abort();
    batchRun=null;batchActions=[];batchRevision++;clearTimeout(batchTimer);
    byId("run-status").textContent="尚未开始";byId("run-id").textContent="";
    byId("run-detail").replaceChildren();
    byId("results").replaceChildren(element("p","搜索记录已清理，可以开始新的搜索。","muted"));
    for(const id of ["resume","search-more","batch-controls","batch-panel"])byId(id).hidden=true;
  }
  for(const id of result.deleted_ids)bossSelections.delete(id);
  await refreshRuns();
  message(`已清理 ${result.deleted_count} 条搜索，保留 ${result.kept_count} 条进行中或有关联记录的任务。`);
},byId("clear-history"));
byId("resume").onclick=()=>guarded(async()=>{await api(`/api/runs/${currentRun}/resume`,{method:"POST"}); await selectRun(currentRun);},byId("resume"));
