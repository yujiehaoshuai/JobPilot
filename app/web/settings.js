/* 本机连接码只用于本机页面会话；DeepSeek 密钥不写入浏览器存储。 */
let modelConfigured=false;
function updateModeHint() {
  const source=byId("source").value;
  byId("boss-setup").hidden=source!=="boss";
  byId("mode-hint").textContent=source==="mock"
    ? "示例只用本机规则演示，不调用 AI、不收费。"
    : "自动提炼简历并逐条比较，前 5 名再做详细分析；分数不是录用概率。";
  byId("source-hint").textContent=source==="mock" ? "使用虚构岗位，可以放心练习。"
    : "逐页搜索，每次最多读取 100 条、每个关键词最多 20 页；没搜完会明确提示。" + (source==="nowcoder"
    ? "牛客会打开专用 Edge 窗口，请等待它自行关闭。登录失效或遇到验证会暂停。" : source==="boss"
    ? "BOSS 使用正常浏览器中的助手读取，请保持助手页打开。城市最终按岗位地点严格筛选；搜索范围以网站当前条件为准。" : "");
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
  if(status.configured)message("AI 设置已保存。粘贴简历并填写岗位意向后即可搜索，也可以先查看以前的搜索结果。");
  await refreshRuns();
}
byId("model-save").onclick=()=>guarded(async()=>{
  const key=byId("model-key").value.trim();
  if(!key)throw new Error("请先粘贴 DeepSeek 服务密钥。");
  const status=await (await api("/api/model-settings",{method:"POST",body:JSON.stringify({api_key:key})})).json();
  byId("model-key").value=""; showModelStatus(status); updateModeHint();
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
