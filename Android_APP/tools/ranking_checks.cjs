// Synthetic leaderboard rows exist only in this test browser.
module.exports=async({evaluate,check,cdp})=>{
  await evaluate(`document.querySelectorAll('dialog[open]').forEach(d=>d.close());clearAccount();apiBase='https://test.invalid';capabilities={};checkedAt=Date.now();state.rankPage=1;state.rankPageSize=5;state.days='7';state.query='';window.rankRequests=[];window.modernRank=true;window.rankFixtures=Array.from({length:13},(_,i)=>({name:'Test rank '+i,status:'Test only',total_count:i<10?13-i:0}));window.fetch=async address=>{
    const url=new URL(address);rankRequests.push(Object.fromEntries(url.searchParams));const size=Number(url.searchParams.get('page_size'))||20,page=Number(url.searchParams.get('page'))||1;
    const data=modernRank?rankFixtures.filter(row=>row.total_count>0):rankFixtures;
    return new Response(JSON.stringify({rows:data.slice((page-1)*size,page*size),total:data.length,page,page_size:size,...(modernRank?{positive_only:true,period:url.searchParams.get('period'),timezone:'Asia/Shanghai'}:{})}));
  };await show('rank')`);
  await check("document.querySelectorAll('#ranks .rank-row').length===5 && document.querySelector('.rank-position span').textContent==='（共2页）' && document.querySelectorAll('#rank-page-size option').length===4",'Five positive rows and accurate total pages with four size choices');
  await evaluate("document.getElementById('rank-next').click();await new Promise(r=>setTimeout(r,30))");
  await check("state.rankPage===2 && document.querySelector('.rank-number').textContent==='6' && document.getElementById('rank-next').disabled",'Second page uses continuous ranks and disables next');
  for(const value of ['', '0','-1','3','2.5','abc','9999999999999999999999']){
    await evaluate(`state.rankPage=2;await show('rank');document.getElementById('rank-page').value=${JSON.stringify(value)};document.getElementById('rank-page').dispatchEvent(new Event('change'));await new Promise(r=>setTimeout(r,20))`);
    await check("state.rankPage===1 && document.getElementById('rank-page').value==='1'",'Invalid page '+JSON.stringify(value)+' resets to first');
  }
  await evaluate("document.getElementById('rank-page').value='2';document.getElementById('rank-page').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter'}));await new Promise(r=>setTimeout(r,20))");
  await check("state.rankPage===2",'Typed valid page jumps on Enter');
  await evaluate("document.getElementById('rank-page-size').value='100';document.getElementById('rank-page-size').dispatchEvent(new Event('change'));await new Promise(r=>setTimeout(r,20))");
  await check("state.rankPage===1 && state.rankPageSize===100 && document.querySelectorAll('.rank-row').length===10 && document.querySelector('.rank-position span').textContent==='（共1页）'",'Size change resets first page and shows only positive members');
  await evaluate("modernRank=false;state.rankPageSize=5;state.rankPage=2;await show('rank')");
  await check("document.querySelectorAll('.rank-row').length===5 && document.querySelector('.rank-number').textContent==='6' && document.querySelector('.rank-position span').textContent==='（共2页）' && rankRequests.some(r=>r.page_size==='100')",'Old server is filtered before local pagination');
  await evaluate("state.days='today';await show('rank')");
  await check("document.querySelector('#ranks .error-box').textContent.includes('无API接口')",'Old server cannot masquerade as today statistics');
  await evaluate("modernRank=true;await show('rank')");
  await check("document.querySelectorAll('.rank-row').length===5 && rankRequests.at(-1).period==='today' && rankRequests.at(-1).positive_only==='1'",'Today requests explicit calendar period and positive filtering');
  await cdp('Emulation.setDeviceMetricsOverride',{width:360,height:800,deviceScaleFactor:1,mobile:true});
  await check("document.querySelector('.rank-pager').getBoundingClientRect().right<=innerWidth && document.documentElement.scrollWidth<=innerWidth",'Pager stays within 360px mobile viewport');
  await cdp('Emulation.setDeviceMetricsOverride',{width:440,height:900,deviceScaleFactor:1,mobile:true});
  await evaluate("document.getElementById('rank-filter').click();document.getElementById('rank-sort').value='cf_count';document.getElementById('rank-filter').click();document.getElementById('rank-filter').click()");
  await check("document.querySelectorAll('dialog[open]').length===1 && document.getElementById('rank-sort').value==='cf_count'",'Queued filter clicks retain one dialog and edited selection');
  await evaluate("showInfo('Test alert','Test only');showInfo('Test alert','Again');document.getElementById('top-tools-button').click()");
  await check("document.querySelectorAll('dialog[open]').length===1 && document.getElementById('info-dialog').open",'Alert replaces prior dialog and blocks clicks behind it');
  await evaluate("document.getElementById('info-dialog').close();capabilities={own_public_profile:true};checkedAt=Date.now();window.popupCalls=0;window.fetch=async()=>{popupCalls++;return new Promise(resolve=>window.releasePopup=()=>resolve(new Response('{\"motto\":\"Test only\"}')))};window.popupPromises=[accountAction('motto'),accountAction('motto'),accountAction('motto')];await new Promise(r=>setTimeout(r,0))");
  await check("popupCalls===1",'Asynchronous popup buttons share one pending request');
  await evaluate("releasePopup();await Promise.all(popupPromises);document.getElementById('edit-value').value='Unsaved';await accountAction('motto')");
  await check("document.querySelectorAll('dialog[open]').length===1 && popupCalls===1 && document.getElementById('edit-value').value==='Unsaved'",'Repeated open preserves form inputs and sends no further request');
  await evaluate("document.querySelectorAll('dialog[open]').forEach(d=>d.close());state.days='7';state.rankPage=1;state.rankPageSize=20;clearAccount()");
  console.log('Ranking/modal checks passed: today, zero filtering, accurate paging, invalid inputs, page sizes, narrow layout and popup single-flight.');
};
