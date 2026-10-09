/** 完整读取循环用虚构页面验收：去重、边界、人工暂停和本机逐条保存。 */
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {collectSearch} from "../../extensions/boss_readonly/search.mjs";
const config=JSON.parse(readFileSync(new URL("../../extensions/boss_readonly/selectors.json",import.meta.url)));
const url=id=>`https://www.zhipin.com/job_detail/${id}.html`;
function fixture(searches,{fail=null,attempted=[],limit=10}={}) {
  let tabs=0,searchIndex=0;
  const reads=[],updates=[],clicks=[];
  const api={tabs:{create:async()=>({id:++tabs})},scripting:{executeScript:async spec=>{clicks.push(spec);return [{result:true}];}}};
  const observe=async(api,tabId,config,{navigateTo})=>{
    reads.push({tabId,navigateTo});
    if(fail && navigateTo===url(fail))return {report:{outcome:"manual_verification_required",jobs:[]}};
    if(tabId===1) {
      const value=searches[searchIndex++];
      assert.ok(value,"不应读取计划以外的页面");
      return {report:{outcome:"page_observed",jobs:[]},page:{empty:!value.ids.length,next_state:value.next||"end"},
        privateLinks:value.ids.map(id=>({url:url(id),navigation_url:url(id)}))};
    }
    const id=new URL(navigateTo).pathname.split("/").pop().replace(".html","");
    return {report:{outcome:"page_observed",jobs:[{source_job_id:id}]},privateLinks:[],
      page:{detail:{url:url(id),title:"虚构岗位",company:"虚构公司",description:"需要 Python"}}};
  };
  const task={id:"fixture",queries:["Python"],attempted,limit,pages:0};
  const run=()=>collectSearch(api,task,config,async value=>updates.push(value),{observe});
  return {task,reads,updates,clicks,run,tabCount:()=>tabs};
}
test("翻页后去重、逐条保存详情，不点击申请或沟通",async()=>{
  const f=fixture([{ids:["a","b"],next:"available"},{ids:["b","c"]}]);
  await f.run();
  assert.equal(f.clicks.length,1);
  assert.equal(f.clicks[0].func.name,"nextSearchPage");
  assert.deepEqual(f.updates.filter(x=>x.job).map(x=>x.job.url),[url("a"),url("b"),url("c")]);
  assert.equal(f.updates.at(-1).complete,true);
});
test("达到数量上限时明确说明未读完，不能继续翻页",async()=>{
  const f=fixture([{ids:["a","b"],next:"available"}],{limit:1});await f.run();
  assert.equal(f.reads.length,2);assert.equal(f.clicks.length,0);
  assert.equal(f.updates.at(-1).complete,false);assert.ok(f.updates.some(x=>/上限/.test(x.warning||"")));
});
test("登录验证中断保留前一个岗位，不自动重试或读下一个",async()=>{
  const f=fixture([{ids:["a","blocked","c"]}],{fail:"blocked"});
  await assert.rejects(f.run(),/登录或验证/);
  assert.equal(f.updates.filter(x=>x.job).length,1);
  assert.equal(f.updates.at(-1).paused,true);assert.equal(f.reads.length,3);
  assert.ok(!f.updates.some(x=>x.finished));
});
test("刷新后跳过服务器已经保存的岗位",async()=>{
  const f=fixture([{ids:["a","b"]}],{attempted:["a"]});await f.run();
  assert.deepEqual(f.updates.filter(x=>x.job).map(x=>x.job.url),[url("b")]);
});
test("重复页和找不到下一页都不能报告已覆盖全部",async()=>{
  for(const searches of [[{ids:["a"],next:"available"},{ids:["a"],next:"available"}],[{ids:["a"],next:"unknown"}]]) {
    const f=fixture(searches);await f.run();
    assert.equal(f.updates.filter(x=>x.job).length,1);
    assert.equal(f.updates.at(-1).complete,false);assert.ok(f.updates.some(x=>x.warning));
  }
});
test("搜索没有岗位时不预先打开空白详情页",async()=>{
  const f=fixture([{ids:[]}]);await f.run();
  assert.equal(f.tabCount(),1);assert.equal(f.updates.at(-1).finished,true);
});

test("先收集滚动产生的新编号，再读取详情，保留续页证据",async()=>{
  const f=fixture([{ids:["a","b"],next:"scroll"},{ids:["a","b","c"]}]);
  await f.run();
  assert.deepEqual(f.reads.map(r=>r.tabId),[1,1,2,2,2]);
  const samples=f.updates.filter(u=>u.page_sample).map(u=>u.page_sample);
  assert.equal(samples[0].continuation,"scroll");assert.deepEqual(samples[1].ids,["a","b","c"]);
});
