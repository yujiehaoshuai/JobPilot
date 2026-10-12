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
  if(observed.title!==expected.title || observed.company!==expected.company)return {state:"wrong_target",
    missing_title:!observed.title,missing_company:!observed.company,
    title_changed:observed.title!==expected.title,company_changed:observed.company!==expected.company};
  const buttons=[...document.querySelectorAll(config.contact_selector)].filter(visible);
  if(buttons.some(e=>["继续沟通","已沟通"].includes(e.innerText.trim())))return {state:"already_contacted",observed};
  const choices=buttons.filter(e=>e.innerText.trim()==="立即沟通" && !e.disabled && e.getAttribute("aria-disabled")!=="true");
  if(choices.length!==1)return {state:"button_missing",button_count:choices.length};
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

/** 仅解释未点击的原因；不保存账号信息、完整地址或网页正文。 */
export function contactPauseMessage(observation, navigation="unknown") {
  if(navigation==="loading")return "岗位页面仍在跳转，尚未点击。请等待页面加载后再继续。";
  if(navigation==="wrong_page")return "网页没有停留在这条岗位详情，可能跳到首页或岗位已下线；尚未点击。请重新搜索有效岗位。";
  if(observation?.state==="already_contacted")return "BOSS 已显示沟通过，此次没有点击，请取消重复联系。";
  if(observation?.state==="verification")return "网页出现登录或验证提示，尚未点击。请手动处理后再继续。";
  if(observation?.state==="wrong_target") {
    if(observation.missing_title || observation.missing_company)return "岗位详情尚未完整显示，未读到岗位名称或公司名称，尚未点击。";
    const fields=[observation.title_changed?"岗位名称":"",observation.company_changed?"公司名称":""].filter(Boolean).join("和");
    return `当前网页的${fields||"岗位信息"}与批准记录不同，尚未点击。请重新搜索并核对。`;
  }
  if(observation?.state==="button_missing")return observation.button_count>1
    ?"网页有多个可用的“立即沟通”按钮，无法确定目标，尚未点击。"
    :"岗位详情没有可用的“立即沟通”按钮，尚未点击。请检查岗位状态。";
  return "没有读到可核对的岗位详情，尚未点击。请检查 BOSS 页面后再继续。";
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
    let observation,navigation="unknown";
    for(let step=0;step<20;step++) {
      const current=await api.tabs.get(tab.id);
      navigation=current.pendingUrl?"loading":current.url && new URL(current.url).pathname===url.pathname?"detail":"wrong_page";
      if(!current.pendingUrl && current.url && new URL(current.url).pathname===url.pathname) {
        observation=await read();
        if(["ready","verification","already_contacted"].includes(observation?.state))break;
      }
      await wait(500);
    }
    if(observation?.state!=="ready") {
      await local(`/api/boss/contacts/${action.id}/pause`,{digest:action.digest,message:contactPauseMessage(observation,navigation)});
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
