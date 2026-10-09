/** 同一函数用于只读预检查与获批后的单次点击，不接触其他聊天或账号页面。 */
export function contactOnPage(config, expected, permit=null) {
  const visible = element=>getComputedStyle(element).display!=="none" && getComputedStyle(element).visibility!=="hidden" && element.getClientRects().length>0;
  const read = selector=>[...document.querySelectorAll(selector)].filter(visible).map(e=>e.innerText?.trim()||"").filter(Boolean).join("\n");
  const match = location.pathname.match(/^\/job_detail\/([A-Za-z0-9_-]+)\.html$/);
  if(location.protocol!=="https:" || !config.site.hosts.includes(location.hostname) || location.port
      || !match || match[1]!==expected.job_id)return {state:"wrong_page"};
  if(config.challenge_titles.some(word=>document.title.includes(word))
      || config.challenge_selectors.some(selector=>[...document.querySelectorAll(selector)].some(visible)))return {state:"verification"};
  const observed={job_id:match[1],title:read(config.site.title),company:read(config.site.company),button:""};
  if(observed.title!==expected.title || observed.company!==expected.company)return {state:"wrong_target"};
  const buttons=[...document.querySelectorAll(config.contact_selector)].filter(visible);
  if(buttons.some(e=>["继续沟通","已沟通"].includes(e.innerText.trim())))return {state:"already_contacted",observed};
  const choices=buttons.filter(e=>e.innerText.trim()==="立即沟通" && !e.disabled && e.getAttribute("aria-disabled")!=="true");
  if(choices.length!==1)return {state:"button_missing"};
  observed.button="立即沟通";
  if(!permit)return {state:"ready",observed};
  if(permit.id!==expected.id || permit.digest!==expected.digest || permit.kind!=="boss_start_chat"
      || permit.job_id!==expected.job_id || !Number.isFinite(permit.expires_at) || permit.expires_at<Date.now()
      || permit.expires_at>Date.now()+16000 || !/^[A-Za-z0-9_-]{40,60}$/.test(permit.token))return {state:"invalid_permit"};
  // 每个文档的隔离环境内额外防重；刷新后仍由后端 EXECUTING 状态阻止再次发放许可。
  const used=globalThis.__jobpilotContactPermits || (globalThis.__jobpilotContactPermits=new Set());
  if(used.has(permit.token))return {state:"duplicate_permit"};
  used.add(permit.token);
  choices[0].click();
  return {state:"clicked"};
}

/** 许可响应丢失、点击异常或回执不明均不重试点击，交给用户到网站核查。 */
export async function executeContact(api, action, config, local, options={}) {
  const wait=options.wait || (ms=>new Promise(resolve=>setTimeout(resolve,ms)));
  let permit=null,requested=false;
  const url=new URL(action.url);
  if(action.kind!=="boss_start_chat" || url.protocol!=="https:" || !config.site.hosts.includes(url.hostname)
      || url.username || url.password || url.port || url.pathname!==`/job_detail/${action.job_id}.html`)throw new Error("未经批准的目标地址");
  let tab;
  const read=async ticket=>{
    const [result]=await api.scripting.executeScript({target:{tabId:tab.id,frameIds:[0]},world:"ISOLATED",
      func:contactOnPage,args:[config,action,ticket||null]});
    return result?.result;
  };
  try {
    tab=await api.tabs.create({url:action.url,active:true});
    let observation;
    for(let step=0;step<20;step++) {
      const current=await api.tabs.get(tab.id);
      if(!current.pendingUrl && current.url && new URL(current.url).pathname===url.pathname) {
        observation=await read();
        if(["ready","verification","already_contacted"].includes(observation?.state))break;
      }
      await wait(500);
    }
    if(observation?.state!=="ready") {
      await local(`/api/boss/contacts/${action.id}/pause`,{digest:action.digest,message:observation?.state==="already_contacted"
        ?"BOSS 已显示沟通过，此次没有点击，请取消重复联系。":"岗位、按钮或登录状态需要核对。请检查 BOSS 页面后在 JobPilot 点击继续。"});
      return {state:"paused"};
    }
    requested=true;
    permit=await local(`/api/boss/contacts/${action.id}/permit`,{digest:action.digest,observed:observation.observed});
    const clicked=await read(permit);
    let confirmed=false;
    if(clicked?.state==="clicked") {
      for(let step=0;step<15;step++) {
        await wait(1000);
        const after=await read();
        if(after?.state==="already_contacted"){confirmed=true;break;}
        if(after?.state==="verification" || after?.state==="wrong_page")break;
      }
    }
    await local(`/api/boss/contacts/${action.id}/receipt`,{token:permit.token,confirmed});
    return {state:confirmed?"confirmed":"uncertain"};
  } catch {
    if(permit) {
      try {await local(`/api/boss/contacts/${action.id}/receipt`,{token:permit.token,confirmed:false});}catch{}
    } else if(!requested) {
      try {await local(`/api/boss/contacts/${action.id}/pause`,{digest:action.digest,message:"浏览器读取中断，此次尚未申请执行许可，请处理后继续。"});}catch{}
    }
    return {state:requested?"uncertain":"paused"};
  }
}
