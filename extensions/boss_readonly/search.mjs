import {observeTab} from "./probe.mjs";
import {nextSearchPage} from "./collector.mjs";
import {searchUrl, readableUrl} from "./core.mjs";

/** 关键词搜索、分页与详情读取都发生在普通标签页；每步结果立即回传本机。 */
export async function collectSearch(api, task, config, save, options={}) {
  const observe = options.observe || observeTab;
  const attempted = new Set(task.attempted);
  let pages = task.pages, searchTab, detailTab, complete = true;
  const collected = new Map();
  const progress = async value => save({pages, ...value});
  const checkStop = () => { if(options.stopped?.())throw new Error("已暂停读取。点击继续后会跳过已保存的岗位。"); };
  async function read(tabId, url=null) {
    checkStop();
    const result = await observe(api, tabId, config, {navigateTo:url, duration:10000});
    checkStop();
    if(result.report.outcome !== "page_observed") {
      const last=result.report.observations?.at(-1);
      const lastUrl=result.report.events?.filter(event=>event.url).at(-1)?.url;
      let pagePath="";try {pagePath=new URL(lastUrl).pathname;}catch{}
      await progress({diagnostic:{outcome:result.report.outcome,tab_id:tabId,elapsed_ms:result.report.elapsed_ms||0,
        error_type:result.report.events?.find(event=>event.kind==="observation.error")?.error_type||"",
        observations:result.report.observations?.length||0,body_length:last?.body_length||0,listing_count:last?.listing_count||0,
        page_path:pagePath}});
      throw new Error(result.report.outcome === "manual_verification_required"
        ? "BOSS 需要登录或验证。请在刚打开的网页里手动完成，再点击继续。"
        : "BOSS 页面未能正常读取。请检查网页；若出现空白、登录或验证，处理后再继续。");
    }
    return result;
  }
  try {
    // 不接管用户已有标签页。详情页等有岗位链接后才创建，避免留下无用空白页。
    searchTab = await api.tabs.create({url:"about:blank",active:true});
    searchQueries: for(const query of task.queries) {
      checkStop();
      const signatures = new Set();
      let result = await read(searchTab.id, searchUrl(query, config.site));
      for(let pageNumber=1; pageNumber<=20; pageNumber++) {
        pages++;
        options.onProgress?.(`搜索“${query}”：第 ${pageNumber} 页，已处理 ${attempted.size} 条岗位。`);
        const links = result.privateLinks.filter(item=>readableUrl(item.navigation_url));
        if(!links.length) {
          if(!result.page?.empty)throw new Error("页面没有读到岗位，也没有明确的空结果提示。请检查登录状态或页面结构。");
          await progress({});break;
        }
        await progress({page_sample:{query_index:task.queries.indexOf(query),page_number:pageNumber,
          ids:links.map(link=>new URL(link.url).pathname.match(/\/job_detail\/([A-Za-z0-9_-]+)\.html$/)?.[1]).filter(Boolean),
          continuation:result.page?.next_state||"unknown",scroll:result.page?.scroll||[]}});
        const signature = links.map(item=>item.url).sort().join("|");
        if(signatures.has(signature)) {
          complete=false;await progress({warning:`“${query}”翻页后仍是相同岗位，已停止这个关键词；未确认后续结果。`});break;
        }
        signatures.add(signature);
        for(const link of links) {
          const id = new URL(link.url).pathname.match(/\/job_detail\/([A-Za-z0-9_-]+)\.html$/)?.[1];
          if(!id || attempted.has(id))continue;
          if(attempted.size+collected.size>=task.limit)break;
          collected.set(id,link);
        }
        if(attempted.size+collected.size>=task.limit) {
          complete=false;
          await progress({warning:`达到本次 ${task.limit} 条读取上限，可能还有未读取的岗位。`});
          break searchQueries;
        }
        if(result.page?.next_state === "end")break;
        if(!["available","scroll"].includes(result.page?.next_state)) {
          complete=false;await progress({warning:`“${query}”当前页已读取，但未识别到下一页控件，不能确认已读完。`});break;
        }
        if(pageNumber===20) {
          complete=false;await progress({warning:`“${query}”达到 20 页上限，后续结果未读取。`});break;
        }
        checkStop();
        const [clicked] = await api.scripting.executeScript({target:{tabId:searchTab.id,frameIds:[0]},
          world:"ISOLATED",func:nextSearchPage,args:[config]});
        if(!clicked?.result)throw new Error("下一页控件已变化，请检查 BOSS 页面后继续。");
        result = await read(searchTab.id);
      }
    }
    // 先验证列表续页，再读取详情；链接含导航参数，仅在当前面板内存中保留。
    for(const [id,link] of collected) {
      if(!detailTab)detailTab=await api.tabs.create({url:"about:blank",active:false});
      const detail = await read(detailTab.id, link.navigation_url);
      if(detail.report.jobs.length && detail.page?.detail) {
        if(detail.report.jobs[0].source_job_id!==id)throw new Error("岗位详情跳到了另一条岗位，已暂停，请核对网页。");
        await progress({job:detail.page.detail});
      } else {
        complete=false;
        await progress({skipped_id:id,warning:`岗位 ${id} 缺少标题、公司或完整说明，已跳过，未生成匹配结论。`});
      }
      attempted.add(id);
      options.onProgress?.(`已处理 ${attempted.size} 条岗位，正在保存。`);
    }
    await progress({finished:true,complete});
  } catch(error) {
    // 网站验证和结构变化不重试；保留浏览器页面、已收到的岗位以及人工处理提示。
    const message = error instanceof Error && /^(BOSS|页面|岗位|下一页|已暂停)/.test(error.message)
      ? error.message : "助手读取暂时中断。已保存的岗位会保留，请检查本机连接和 BOSS 页面后继续。";
    await progress({paused:true,warning:message});
    throw new Error(message);
  }
}
