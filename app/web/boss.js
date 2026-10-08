/* 本机页面与本项目助手连接，不向扩展传入简历、主页面凭据或 DeepSeek 密钥。 */
function detectBossHelper() {
  return new Promise(resolve=>{
    const receive=event=>{
      if(event.source===window && event.origin===location.origin && event.data?.type==="jobpilot-boss-installed") {
        clearTimeout(timer);window.removeEventListener("message",receive);resolve(true);
      }
    };
    const timer=setTimeout(()=>{window.removeEventListener("message",receive);resolve(false);},1200);
    window.addEventListener("message",receive);
    window.postMessage({type:"jobpilot-boss-ping"},location.origin);
  });
}
async function connectBoss() {
  if(!await detectBossHelper()) {
    byId("boss-install").open=true;
    byId("boss-status").textContent="还没有检测到助手，请按下面的步骤添加，然后刷新本页。";
    throw new Error("BOSS 需要先添加浏览器助手。左侧已经展开安装步骤，添加后刷新即可。");
  }
  const result=await(await api("/api/boss/connect",{method:"POST"})).json();
  window.postMessage({type:"jobpilot-boss-connect",connection:result.connection},location.origin);
  byId("boss-status").textContent="正在打开助手。请保持助手页面打开，读取完成会自动开始匹配。";
  for(let attempt=0;attempt<10;attempt++) {
    await new Promise(resolve=>setTimeout(resolve,500));
    if((await(await api("/api/boss/status")).json()).connected) {
      byId("boss-status").textContent="BOSS 助手已连接，可以开始搜索。";return;
    }
  }
  throw new Error("助手尚未连接。请检查是否出现助手页面，或重新加载扩展后再试。");
}
async function ensureBossConnected() {
  if(!(await(await api("/api/boss/status")).json()).connected)await connectBoss();
}
byId("boss-connect").onclick=()=>guarded(connectBoss,byId("boss-connect"));
