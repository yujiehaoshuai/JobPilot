/** 虚构 DOM 与浏览器 API 验证审批边界，所有点击都只是测试计数。 */
import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import {readFileSync} from "node:fs";
import {contactOnPage,executeContact,contactPauseMessage} from "../../extensions/boss_readonly/contact.mjs";

const config=JSON.parse(readFileSync(new URL("../../extensions/boss_readonly/selectors.json",import.meta.url)));
const action={id:"fixture-action",digest:"a".repeat(64),job_id:"fixture1",title:"虚构岗位",company:"虚构公司",
  kind:"boss_start_chat",url:"https://www.zhipin.com/job_detail/fixture1.html"};
const ticket=()=>({...action,token:"t".repeat(43),expires_at:Date.now()+15000});

function pageFixture({title=action.title,company=action.company,button="立即沟通",challenge=false,url=action.url,count=1}={}) {
  let clicks=0;
  const node=text=>({innerText:text,getClientRects:()=>[1],getAttribute:()=>null,click:()=>clicks++});
  const map=new Map([[config.site.title,[node(title)]],[config.site.company,[node(company)]],
    [config.contact_selector,Array.from({length:count},()=>node(button))],
    [config.challenge_selectors[0],challenge?[node("验证")]:[]]]);
  const document={title:"虚构测试页",querySelectorAll:selector=>map.get(selector)||[]};
  const context=vm.createContext({config,expected:action,permit:null,location:new URL(url),document,
    getComputedStyle:()=>({display:"block",visibility:"visible"})});
  return {clicks:()=>clicks,run:(permit=null)=>{
    context.permit=permit;
    return vm.runInContext(`(${contactOnPage.toString()})(config,expected,permit)`,context);
  }};
}

test("只读预检查不点击，合法许可也只点击一次",()=>{
  const page=pageFixture(),permit=ticket();
  assert.equal(page.run().state,"ready");assert.equal(page.clicks(),0);
  assert.equal(page.run(permit).state,"clicked");assert.equal(page.clicks(),1);
  assert.equal(page.run(permit).state,"duplicate_permit");assert.equal(page.clicks(),1);
});
test("失效、错误目标或错误摘要的许可不能点击",()=>{
  for(const patch of [{expires_at:Date.now()-1000},{expires_at:Date.now()+60000},{id:"other"},
    {job_id:"other"},{digest:"b".repeat(64)},{token:"bad"},{kind:"send_message"}]) {
    const page=pageFixture();assert.equal(page.run({...ticket(),...patch}).state,"invalid_permit");assert.equal(page.clicks(),0);
  }
});
test("岗位或公司变化、验证框、多按钮、已沟通都禁止点击",()=>{
  for(const [options,state] of [[{title:"其他岗位"},"wrong_target"],[{company:"其他公司"},"wrong_target"],
    [{challenge:true},"verification"],[{count:2},"button_missing"],[{count:0},"button_missing"],
    [{button:"继续沟通"},"already_contacted"],[{button:"发送"},"button_missing"],
    [{url:"https://www.zhipin.com/web/geek/chat"},"wrong_page"]]) {
    const page=pageFixture(options);assert.equal(page.run(ticket()).state,state);assert.equal(page.clicks(),0);
  }
});

function executorFixture({preflight="ready",after="already_contacted",lostPermit=false,clickThrows=false,currentUrl=action.url,pendingUrl}={}) {
  const calls=[],injections=[];
  let clicked=false;
  const api={tabs:{create:async()=>({id:1}),get:async()=>({id:1,url:currentUrl,pendingUrl,status:"loading"})},
    scripting:{executeScript:async spec=>{
      injections.push(spec);
      assert.equal(spec.func,contactOnPage);assert.equal(spec.world,"ISOLATED");
      if(spec.args[2]) {clicked=true;if(clickThrows)throw new Error("回执丢失");return [{result:{state:"clicked"}}];}
      return [{result:{state:clicked?after:preflight,observed:{job_id:action.job_id,title:action.title,company:action.company,button:"立即沟通"}}}];
    }}};
  const local=async(path,body)=>{calls.push({path,body});if(path.endsWith("permit")){if(lostPermit)throw new Error("许可响应丢失");return ticket();}return {};};
  return {calls,injections,run:()=>executeContact(api,action,config,local,{wait:async()=>{}})};
}
test("网页仍加载时可核对可见岗位；先拿许可，再点击，最后确认回执",async()=>{
  const f=executorFixture();assert.equal((await f.run()).state,"confirmed");
  assert.ok(f.calls[0].path.endsWith("permit"));assert.ok(f.calls[1].path.endsWith("receipt"));
  assert.equal(f.calls[1].body.confirmed,true);assert.equal(f.injections.filter(s=>s.args[2]).length,1);
});
test("验证和已沟通过只暂停，不申请许可",async()=>{
  for(const preflight of ["verification","already_contacted","wrong_target","button_missing"]) {
    const f=executorFixture({preflight});assert.equal((await f.run()).state,"paused");
    assert.equal(f.calls.length,1);assert.ok(f.calls[0].path.endsWith("pause"));
    assert.equal(f.injections.filter(s=>s.args[2]).length,0);
  }
});
test("许可响应丢失后不重试，也不假报未执行",async()=>{
  const f=executorFixture({lostPermit:true});assert.equal((await f.run()).state,"uncertain");
  assert.equal(f.calls.length,1);assert.equal(f.injections.filter(s=>s.args[2]).length,0);
});
test("点击异常或没有可靠结果只发不确定回执，绝不再次点击",async()=>{
  for(const options of [{clickThrows:true},{after:"ready"},{after:"verification"},{after:"wrong_page"}]) {
    const f=executorFixture(options);assert.equal((await f.run()).state,"uncertain");
    assert.equal(f.calls.at(-1).body.confirmed,false);assert.equal(f.injections.filter(s=>s.args[2]).length,1);
  }
});

test("跳回首页或尚在跳转时明确暂停，不读取旧文档或申请点击许可",async()=>{
  for(const [options,reason] of [[{currentUrl:"https://www.zhipin.com/"},"没有停留"],
    [{pendingUrl:action.url},"仍在跳转"]]) {
    const f=executorFixture(options);assert.equal((await f.run()).state,"paused");
    assert.equal(f.injections.length,0);assert.equal(f.calls.length,1);
    assert.ok(f.calls[0].path.endsWith("pause"));assert.ok(f.calls[0].body.message.includes(reason));
  }
});

test("暂停提示区分缺字段、岗位变化和多个按钮，不泄露网页正文",()=>{
  for(const [options,reason] of [[{title:""},"未读到"],[{title:"别的岗位"},"岗位名称"],
    [{company:"别的公司"},"公司名称"],[{count:2},"多个"],[{count:0},"没有可用"]]) {
    const page=pageFixture(options),observed=page.run();
    const message=contactPauseMessage(observed,"detail");
    assert.ok(message.includes(reason));assert.ok(!message.includes("别的"));assert.equal(page.clicks(),0);
  }
});
