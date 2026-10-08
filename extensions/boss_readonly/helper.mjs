import {collectSearch} from "./search.mjs";
const element = id=>document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
if(location.hash)history.replaceState(null,"",location.pathname);
if(fragment.get("connection"))sessionStorage.setItem("boss-connection",JSON.stringify(Object.fromEntries(fragment)));
const connection = JSON.parse(sessionStorage.getItem("boss-connection") || "null");
const owner = sessionStorage.getItem("boss-reader") || crypto.randomUUID();
sessionStorage.setItem("boss-reader",owner);
let busy=false, stopped=false, pausedId=sessionStorage.getItem("boss-paused"), stoppedPolling=false;
const config = await(await fetch("selectors.json")).json();
const say=text=>element("status").textContent=text;
async function api(path, body) {
  const response=await fetch(connection.server+path,{method:body?"POST":"GET",redirect:"error",credentials:"omit",
    headers:{"Content-Type":"application/json","X-JobPilot-Bridge":connection.connection,"X-JobPilot-Reader":owner},
    ...(body?{body:JSON.stringify(body)}:{})});
  if(!response.ok) {
    if(response.status===401)stoppedPolling=true;
    throw new Error(response.status===401 ? "助手连接已失效，请回 JobPilot 点击“连接 BOSS 助手”。" : "本机程序暂时没有接收结果，请保持程序运行后继续。");
  }
  return response.json();
}
async function poll() {
  if(busy || stoppedPolling)return;
  busy=true;
  try {
    const {task,paused}=await api("/api/boss/next");
    if(task) {
      pausedId=null;sessionStorage.removeItem("boss-paused");element("resume").hidden=true;
      stopped=false;element("pause").disabled=false;
      try {
        await collectSearch(chrome,task,config,body=>api(`/api/boss/tasks/${task.id}`,body),
          {stopped:()=>stopped,onProgress:say});
        say("岗位已经交给 JobPilot，AI 正在比较。可以回到主页面查看结果。");
      } catch(error) {
        pausedId=task.id;sessionStorage.setItem("boss-paused",pausedId);
        element("resume").hidden=false;say(error.message);
      } finally {element("pause").disabled=true;}
    } else if(paused) {
      pausedId=paused.id;sessionStorage.setItem("boss-paused",pausedId);
      element("resume").hidden=false;say(paused.message);
    }
  } catch(error) {say(error.message);}
  finally {busy=false;if(!stoppedPolling)setTimeout(poll,3000);}
}
element("pause").onclick=()=>{stopped=true;say("将在当前只读步骤结束后暂停，保留已保存的岗位。");};
element("resume").onclick=async()=>{
  if(!pausedId)return;
  try {await api(`/api/boss/tasks/${pausedId}/continue`,{});element("resume").hidden=true;say("正在继续，已保存岗位不会重复读取。");}
  catch(error){say(error.message);}
};
let valid=false;
try {const url=new URL(connection?.server);valid=url.protocol==="http:"&&url.hostname==="127.0.0.1"&&url.origin===connection.server
  && /^[A-Za-z0-9_-]{40,60}$/.test(connection.connection);}catch{}
if(valid) {
  element("dashboard").href=connection.server;
  element("resume").hidden=!pausedId;
  say(pausedId?"上次读取已暂停；处理好 BOSS 页面后点击继续。":"已连接。请保持本页打开，回 JobPilot 开始搜索。");
  // 同一浏览器资料下只允许一个助手面板工作，避免重复打开页面。
  void navigator.locks.request("jobpilot-boss-reader",{ifAvailable:true},async lock=>{
    if(!lock){say("另一个 BOSS 助手页面正在工作，请回到那个页面继续。");return;}
    void poll();await new Promise(()=>{});
  });
} else say("请先双击 start.cmd 打开 JobPilot，选择 BOSS 直聘，再点击“连接 BOSS 助手”。");
