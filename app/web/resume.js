/* 正文和技能只留在当前页面；原始文件不会落盘，也不会发送给模型。 */
function addResumeSkill(quote="") {
  const card=element("div",undefined,"resume-skill");
  const skill=element("input"); skill.placeholder="原文中的技能名称，例如 Python";
  skill.maxLength=80; skill.setAttribute("aria-label","技能名称"); skill.className="resume-skill-name";
  const level=element("select"); level.className="resume-skill-level"; level.setAttribute("aria-label","技能程度");
  for (const [value,label] of [["","请选择真实程度"],["learning","正在学习"],["project_experience","项目中使用过"],["professional","工作中使用过"]]) {
    const option=element("option",label); option.value=value; level.append(option);
  }
  const evidence=element("textarea"); evidence.rows=3; evidence.maxLength=10000;
  evidence.value=quote; evidence.placeholder="从上方原文复制一句相关经历，例如：在课程项目中，我使用 Python 编写了一个记账工具。";
  evidence.className="resume-skill-quote"; evidence.setAttribute("aria-label","简历原文证据");
  const remove=element("button","移除此条","quiet"); remove.type="button";
  remove.onclick=()=>{card.remove();byId("resume-confirm").checked=false;invalidateCandidate();};
  card.append(skill,level,evidence,remove); byId("resume-skills").append(card);
  byId("resume-confirm").checked=false;
}
byId("resume-builder").addEventListener("input",event=>{
  if(event.target.id!=="resume-confirm") byId("resume-confirm").checked=false;
  invalidateCandidate();
});
byId("resume-add").onclick=()=>{
  const text=byId("resume-text");
  addResumeSkill(text.value.slice(text.selectionStart,text.selectionEnd));
  invalidateCandidate();
};
byId("resume-file").onchange=event=>guarded(async()=>{
  const file=event.target.files[0]; if(!file)return;
  if(file.size>1000000)throw new Error("简历文件不能超过 1 MB");
  const extension=file.name.split(".").pop().toLowerCase();
  if(!["txt","md","docx"].includes(extension))throw new Error("请选择 TXT、Markdown 或 DOCX；PDF 请复制正文。");
  const result=await (await api(`/api/resume/extract?format=${extension==="docx"?"docx":"txt"}`,{
    method:"POST",body:file,headers:{"Content-Type":"application/octet-stream"}
  })).json();
  byId("resume-text").value=result.text; byId("resume-skills").replaceChildren();
  addResumeSkill(); invalidateCandidate(); message("正文已读取，请填写技能及相关原句，并核对内容。");
});
byId("resume-build").onclick=()=>guarded(async()=>{
  if(!byId("resume-name").value.trim())throw new Error("请先填写姓名或昵称。");
  if(!byId("resume-text").value.trim())throw new Error("请先填写简历或经历原文。");
  if(!byId("resume-confirm").checked)throw new Error("请先核对技能证据和程度，再勾选确认。");
  const skills=[...document.querySelectorAll(".resume-skill")].map(card=>({
    skill:card.querySelector(".resume-skill-name").value.trim(),
    level:card.querySelector(".resume-skill-level").value,
    quote:card.querySelector(".resume-skill-quote").value.trim()
  }));
  if(!skills.length||skills.some(item=>!item.skill||!item.level||!item.quote))throw new Error("请至少填写一条完整的技能、程度和原文证据。");
  const split=id=>byId(id).value.split(/[,，\n]/).map(item=>item.trim()).filter(Boolean);
  const candidate=await (await api("/api/resume/profile",{method:"POST",body:JSON.stringify({
    text:byId("resume-text").value,name:byId("resume-name").value,skills,
    target_roles:split("resume-roles"),target_cities:split("resume-cities"),confirmed:true
  })})).json();
  useCandidate(candidate);
  message("个人资料已准备好。继续第 2 步，填写关键词并点击“帮我找岗位”。");
},byId("resume-build"));

// 初次打开就展示一项技能，减少第一次使用时的查找步骤。
addResumeSkill();
