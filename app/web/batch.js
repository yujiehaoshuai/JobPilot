/* 勾选只是准备操作；必须逐条展示岗位与副作用，再由用户主动批准。 */
let batchRun=null,batchActions=[],batchTimer=null,batchRevision=0,confirmedBatch="";
const bossSelections=new Map();
const pendingSignature=()=>JSON.stringify(batchActions.filter(a=>a.status==="PENDING").map(a=>[a.id,a.digest]).sort());
byId("batch-confirm").onchange=()=>{confirmedBatch=byId("batch-confirm").checked?pendingSignature():"";};
function addBossSelection(card,runId,job) {
  const selected=bossSelections.get(runId)||new Set();bossSelections.set(runId,selected);
  const label=element("label",undefined,"selection");
  const checkbox=document.createElement("input");checkbox.type="checkbox";checkbox.checked=selected.has(job.id);
  checkbox.setAttribute("aria-label",`选择岗位：${job.title}`);
  checkbox.onchange=()=>{if(checkbox.checked)selected.add(job.id);else selected.delete(job.id);};
  label.append(checkbox,element("span","选择这个岗位"));card.append(label);
}
function updateBatchControls(run) {
  const available=run.source==="boss"&&run.status==="COMPLETED"&&!run.interrupts?.length;
  byId("batch-controls").hidden=!available;
  if(batchRun!==run.id) {
    batchRun=run.id;batchActions=[];batchRevision++;clearTimeout(batchTimer);
    byId("batch-panel").hidden=true;byId("batch-confirm").checked=false;
    if(available)void guarded(()=>refreshBatch(run.id));
  }
}
function renderBatch() {
  // 其他窗口新增或修改待批准列表后，旧勾选不能代表用户看过新的列表。
  if(confirmedBatch!==pendingSignature()){byId("batch-confirm").checked=false;confirmedBatch="";}
  byId("batch-panel").hidden=!batchActions.length;
  byId("batch-items").replaceChildren();
  const names={PENDING:"等待你批准",APPROVED:"已批准，等待助手",EXECUTING:"正在执行，不能重复点击",SUCCEEDED:"已发起沟通",UNCERTAIN:"结果待核查，后续批次已停止",REJECTED:"已取消"};
  for(const action of batchActions) {
    const card=element("article",undefined,"result");
    card.append(element("strong",`${action.payload.job.title} · ${action.payload.job.company}`),
      element("p",action.execution_paused?"等待人工处理网页":names[action.status]),element("p",action.payload.content,"hint"));
    if(action.receipt)card.append(element("p",action.receipt,"hint"));
    if(action.status==="APPROVED"&&action.execution_paused) {
      const button=element("button","网页已处理好，继续本次联系","secondary");
      button.onclick=()=>guarded(async()=>{await api(`/api/boss-actions/${action.id}/resume`,{method:"POST",body:JSON.stringify({id:action.id,digest:action.digest})});await refreshBatch(batchRun);},button);
      card.append(button);
    }
    if(action.status==="UNCERTAIN") {
      const label=element("label","先去 BOSS 核查，再写下看到的结果（至少 5 个字）");
      const note=document.createElement("textarea");note.rows=2;note.maxLength=1000;label.append(note);card.append(label);
      for(const [sent,text] of [[true,"我已核查：确实已联系"],[false,"我已核查：没有联系，取消此次操作"]]) {
        const button=element("button",text,"secondary");
        button.onclick=()=>guarded(async()=>{await api(`/api/actions/${action.id}/resolve`,{method:"POST",body:JSON.stringify({digest:action.digest,sent,note:note.value})});await refreshBatch(batchRun);},button);card.append(button);
      }
    }
    byId("batch-items").append(card);
  }
  byId("batch-approval").hidden=!batchActions.some(a=>a.status==="PENDING");
  byId("batch-cancel").hidden=!batchActions.some(a=>["PENDING","APPROVED"].includes(a.status));
}
async function refreshBatch(runId=batchRun) {
  if(!runId)return;
  const revision=batchRevision;
  const actions=await(await api(`/api/boss-actions?run_id=${runId}`)).json();
  if(runId!==batchRun || revision!==batchRevision)return;
  batchActions=actions;renderBatch();clearTimeout(batchTimer);
  if(actions.some(a=>["APPROVED","EXECUTING"].includes(a.status)))batchTimer=setTimeout(()=>void guarded(()=>refreshBatch(runId)),4000);
}
byId("batch-prepare").onclick=()=>guarded(async()=>{
  const runId=currentRun;
  const ids=[...(bossSelections.get(currentRun)||[])];
  if(!ids.length)throw new Error("请先勾选想联系的岗位。");
  if(ids.length>20)throw new Error("一次最多选择 20 个岗位，请先减少数量。");
  batchRevision++;clearTimeout(batchTimer);
  const result=await(await api(`/api/runs/${runId}/boss-actions`,{method:"POST",body:JSON.stringify({job_ids:ids})})).json();
  if(currentRun!==runId)return;
  batchRevision++;batchActions=result.actions;batchRun=runId;confirmedBatch="";byId("batch-confirm").checked=false;renderBatch();
  byId("batch-feedback").textContent=result.skipped.map(item=>item.reason).join("；")||"请逐条核对上面的岗位和操作说明。现在还没有联系任何招聘方。";
  byId("batch-panel").scrollIntoView({block:"start",behavior:"smooth"});
},byId("batch-prepare"));
async function decideBatch(approve) {
  if(approve&&(!byId("batch-confirm").checked || confirmedBatch!==pendingSignature()))throw new Error("请先核对 BOSS 账号、默认招呼和在线简历，并勾选确认。");
  const runId=batchRun,signature=pendingSignature();
  const selected=batchActions.filter(a=>approve?a.status==="PENDING":["PENDING","APPROVED"].includes(a.status));
  if(approve) {
    await ensureBossConnected();
    if(batchRun!==runId || signature!==pendingSignature())throw new Error("待批准岗位已经变化，请重新核对。");
  }
  if(!selected.length)throw new Error("没有可处理的操作，请刷新列表。");
  await api("/api/boss-actions/decision",{method:"POST",body:JSON.stringify({actions:selected.map(a=>({id:a.id,digest:a.digest})),approve,platform_details_confirmed:approve})});
  byId("batch-confirm").checked=false;confirmedBatch="";
  byId("batch-feedback").textContent=approve?"已批准，助手会逐条处理。遇到验证或结果不明就会停止，请保持助手页打开。":"未执行的操作已取消。";
  await refreshBatch(batchRun);
}
byId("batch-approve").onclick=()=>guarded(()=>decideBatch(true),byId("batch-approve"));
byId("batch-cancel").onclick=()=>guarded(()=>decideBatch(false),byId("batch-cancel"));
byId("batch-refresh").onclick=()=>guarded(()=>refreshBatch(),byId("batch-refresh"));
