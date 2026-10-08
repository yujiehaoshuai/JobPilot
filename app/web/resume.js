/* 表单是唯一资料来源：不缓存“已确认版本”，每次搜索都读取当前输入。 */
function addResumeSkill(quote="", name="", degree="") {
  const card=element("div",undefined,"resume-skill");
  const skill=element("input"); skill.placeholder="技能名称，例如 Python";
  skill.maxLength=80; skill.setAttribute("aria-label","技能名称"); skill.className="resume-skill-name"; skill.value=name;
  const level=element("select"); level.className="resume-skill-level"; level.setAttribute("aria-label","技能程度");
  for (const [value,label] of [["","请选择真实程度"],["learning","正在学习"],["project_experience","项目中使用过"],["professional","工作中使用过"]]) {
    const option=element("option",label); option.value=value; level.append(option);
  }
  level.value=degree;
  const evidence=element("textarea"); evidence.rows=2; evidence.maxLength=10000;
  evidence.value=quote; evidence.placeholder="从上方原文复制一句相关经历";
  evidence.className="resume-skill-quote"; evidence.setAttribute("aria-label","简历原文证据");
  const remove=element("button","移除此项","quiet"); remove.type="button"; remove.onclick=()=>card.remove();
  card.append(skill,level,evidence,remove); byId("resume-skills").append(card);
}
function updateAvailability() {
  const fullTime=byId("resume-employment").value==="full_time";
  byId("availability").hidden=fullTime;
  byId("resume-days").disabled=fullTime; byId("resume-months").disabled=fullTime;
}
function fillExample(candidate) {
  // 示例也是可编辑的普通表单。没有显示的旧字段（排除词等）不参与本次筛选。
  byId("resume-name").value=candidate.name;
  byId("resume-skills").replaceChildren();
  const quotes=candidate.skills.map(item=>`${item.skill}：${item.evidence}`);
  byId("resume-text").value=[candidate.name,...(candidate.education||[]),...(candidate.projects||[]),...quotes].join("\n");
  candidate.skills.forEach((item,index)=>addResumeSkill(quotes[index],item.skill,item.level));
  byId("resume-roles").value=(candidate.target_roles||[]).join("，");
  byId("resume-cities").value=(candidate.target_cities||[]).join("，");
  byId("resume-employment").value=candidate.employment_type||"any";
  byId("resume-days").value=candidate.available_days_per_week??"";
  byId("resume-months").value=candidate.internship_duration_months??"";
  byId("profile-notice").textContent="已填入虚构示例。可以直接体验，也可以修改任意输入框；搜索使用修改后的内容。";
  updateAvailability();
}
function readProfileForm() {
  // 在按下搜索按钮时一次性取值，之后的异步请求不会夹带旧资料。
  const skills=[...document.querySelectorAll(".resume-skill")].map(card=>({
    skill:card.querySelector(".resume-skill-name").value.trim(),
    level:card.querySelector(".resume-skill-level").value,
    quote:card.querySelector(".resume-skill-quote").value.trim()
  })).filter(item=>item.skill||item.level||item.quote);
  if(!skills.length||skills.some(item=>!item.skill||!item.level||!item.quote))throw new Error("请至少填写一项技能、真实程度和相关原句；不用的空项可以移除。");
  const split=id=>byId(id).value.split(/[,，\n]/).map(item=>item.trim()).filter(Boolean);
  const optionalNumber=id=>byId(id).disabled||byId(id).value==="" ? null : Number(byId(id).value);
  return {text:byId("resume-text").value,name:byId("resume-name").value,skills,
    target_roles:split("resume-roles"),target_cities:split("resume-cities"),
    employment_type:byId("resume-employment").value,
    available_days_per_week:optionalNumber("resume-days"),internship_duration_months:optionalNumber("resume-months")};
}
byId("resume-add").onclick=()=>{
  const text=byId("resume-text");addResumeSkill(text.value.slice(text.selectionStart,text.selectionEnd));
};
byId("resume-employment").onchange=updateAvailability;
byId("resume-file").onchange=event=>guarded(async()=>{
  const file=event.target.files[0]; if(!file)return;
  if(file.size>1000000)throw new Error("简历文件不能超过 1 MB");
  const extension=file.name.split(".").pop().toLowerCase();
  if(!["txt","md","docx"].includes(extension))throw new Error("请选择 TXT、Markdown 或 DOCX；PDF 请复制正文。");
  const result=await (await api(`/api/resume/extract?format=${extension==="docx"?"docx":"txt"}`,{
    method:"POST",body:file,headers:{"Content-Type":"application/octet-stream"}
  })).json();
  byId("resume-text").value=result.text; byId("resume-skills").replaceChildren(); addResumeSkill();
  byId("profile-notice").textContent="正文已读取。填写技能及相关原句后，直接点击“帮我找岗位”。";
  message("正文已填入表单，请补充技能和求职条件。");
});
addResumeSkill();
