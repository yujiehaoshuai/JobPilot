/* 正文和意向是唯一输入来源，AI 整理结果只在右侧展示。 */
function updateAvailability() {
  const fullTime=byId("resume-employment").value==="full_time";
  byId("availability").hidden=fullTime;
  byId("resume-days").disabled=fullTime;byId("resume-months").disabled=fullTime;
}
function fillExample(candidate) {
  const quotes=candidate.skills.map(item=>`${item.skill}：${item.evidence}`);
  byId("resume-text").value=[candidate.name,...(candidate.education||[]),...(candidate.projects||[]),...quotes].join("\n");
  byId("query").value="Python";
  byId("resume-cities").value=(candidate.target_cities?.length?candidate.target_cities:["上海"]).join("，");
  byId("resume-employment").value=candidate.employment_type||"any";
  byId("resume-days").value=candidate.available_days_per_week??"";
  byId("resume-months").value=candidate.internship_duration_months??"";
  byId("source").value="mock";
  byId("profile-notice").textContent="这是虚构资料，可直接体验，也可修改。换成真实网站时会调用 AI。";
  updateAvailability();updateModeHint();
}
function readSearchForm() {
  const optionalNumber=id=>byId(id).disabled||byId(id).value==="" ? null : Number(byId(id).value);
  const source=byId("source").value;
  if(!byId("resume-cities").value.split(/[,，、\n]/).some(value=>value.trim()))throw new Error("请填写工作城市。");
  return {text:byId("resume-text").value,intent:byId("query").value,
    cities:byId("resume-cities").value.split(/[,，、\n]/).map(value=>value.trim()).filter(Boolean),
    employment_type:byId("resume-employment").value,
    available_days_per_week:optionalNumber("resume-days"),internship_duration_months:optionalNumber("resume-months"),
    source,mode:source==="mock"?"offline":"live"};
}
byId("resume-employment").onchange=updateAvailability;
byId("resume-file").onchange=event=>guarded(async()=>{
  const file=event.target.files[0];if(!file)return;
  if(file.size>5000000)throw new Error("文件不能超过 5 MB");
  const extension=file.name.split(".").pop().toLowerCase();
  if(!["txt","md","docx","pdf"].includes(extension))throw new Error("请选择 PDF、Word 或文本文件。");
  const result=await(await api(`/api/resume/extract?format=${extension==="md"?"txt":extension}`,{
    method:"POST",body:file,headers:{"Content-Type":"application/octet-stream"}})).json();
  if(result.text.length>30000)throw new Error("简历超过三万字，请缩短后粘贴。");
  byId("resume-text").value=result.text;
  message("正文已填入，请核对后开始搜索。");
  event.target.value="";
});
