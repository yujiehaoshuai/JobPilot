/* 本机连接码只用于本机页面会话；DeepSeek 密钥不写入浏览器存储。 */
let modelConfigured=false;
function updateModeHint() {
  const offline=byId("mode").value==="offline";
  byId("mode-hint").textContent=offline
    ? "基础演示只识别少量常见技能，不调用 AI，也不代表完整匹配能力。"
    : "AI 会读懂岗位说明。每个岗位单独分析，费用从你的 DeepSeek 账户扣除。";
  byId("search-limit").disabled=byId("source").value==="mock";
}
function showModelStatus(status) {
  modelConfigured=status.configured;
  byId("ai-status").textContent=status.configured ? `${status.provider} · 已保存设置` : "需要填写服务密钥";
  byId("model-key").placeholder=status.configured ? "已经保存；需要更换时再填写" : "只在这里填写，不用发到聊天里";
  byId("model-test").disabled=!status.configured;
}
async function connectLocal() {
  const status=await (await api("/api/model-settings")).json();
  // 页面刷新后可继续使用；不把密钥放入地址查询参数、日志或持久的 localStorage。
  try {sessionStorage.setItem("jobpilot-connection",localAccess);} catch {}
  byId("connection-status").textContent="已连接本机";
  showModelStatus(status);
  byId("ai-settings").open=!status.configured;
  if(status.configured)message("AI 设置已保存。填写个人情况后即可搜索，也可以先查看以前的搜索结果。");
  await refreshRuns();
}
byId("model-save").onclick=()=>guarded(async()=>{
  const key=byId("model-key").value.trim();
  if(!key)throw new Error("请先粘贴 DeepSeek 服务密钥。");
  const status=await (await api("/api/model-settings",{method:"POST",body:JSON.stringify({api_key:key})})).json();
  byId("model-key").value=""; showModelStatus(status); byId("mode").value="live"; updateModeHint();
  byId("model-feedback").textContent="密钥已保存到本机。点击“测试连接”，确认 AI 能正常回答。";
  message("已保存 DeepSeek 设置，接着点击“测试连接”。");
},byId("model-save"));
byId("model-test").onclick=()=>guarded(async()=>{
  if(byId("model-key").value.trim())throw new Error("你填写了新密钥，请先保存再测试。");
  byId("model-feedback").textContent="正在让 AI 回答一个简单测试问题，请稍等……";
  try {
    const result=await (await api("/api/model-settings/test",{method:"POST"})).json();
    byId("model-feedback").textContent=result.message;
    byId("ai-status").textContent="DeepSeek · 连接测试通过"; message(result.message);
  } catch(error) {
    byId("model-feedback").textContent=error.message; throw error;
  }
},byId("model-test"));
byId("mode").onchange=updateModeHint;
byId("source").onchange=updateModeHint;
// 启动器在地址片段中传入本机连接码；立即清掉地址，片段不会发给 HTTP 服务。
const access=new URLSearchParams(location.hash.slice(1)).get("access");
if(access)history.replaceState(null,"",location.pathname+location.search);
try {localAccess=access || sessionStorage.getItem("jobpilot-connection") || "";} catch {localAccess=access || "";}
updateModeHint();
if(localAccess)void guarded(connectLocal);
else {
  byId("connection-status").textContent="尚未连接本机";
  message("请双击项目文件夹中的 start.cmd，它会自动打开并连接这个页面。",true);
}
