"""Local Edge benchmark. Optional --baseline-js/--baseline-css compare two versions.
Measures uncached token derivation, theme RAF callback CPU, CDP style/layout CPU,
and frame gaps (not a GPU/presentation benchmark). Writes ignored data/theme-benchmark.json.
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--baseline-js', type=Path)
parser.add_argument('--baseline-css', type=Path)
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[3]
INIT = """(() => {
 const raf = window.requestAnimationFrame.bind(window);
 window.themeSamples = [];
 window.requestAnimationFrame = callback => {
   const isTheme = new Error().stack.includes('theme-editor.js');
   return raf(time => {
     const begin = performance.now();
     try { callback(time); } finally {
       if (isTheme) window.themeSamples.push(performance.now() - begin);
     }
   });
 };
})();"""
ALGORITHM = """() => {
 const stats = values => {values.sort((a,b)=>a-b);return {medianMs:values[Math.floor(values.length/2)],p95Ms:values[Math.floor(values.length*.95)]}};
 const results={};
 for(const key of ['primary','background','surface','accent']) {
   const times=[];
   for(let i=0;i<180;i++) {
     const p=ACMTheme.createDefaultTheme().light;
     p.colors[key]='#'+((i*7919+135791)&0xffffff).toString(16).padStart(6,'0');
     const begin=performance.now(); ACMTheme.deriveTokens(p,false);
     if(i>=20)times.push(performance.now()-begin);
   }
   results[key]=stats(times);
 }
 return results;
}"""
DRAG = """async () => {
 const input=document.querySelector('#theme-color-primary');
 const gaps=[]; let last=null;
 window.themeSamples=[];
 for(let i=0;i<100;i++) {
   const timestamp=await new Promise(requestAnimationFrame);
   if(last!==null && i>=20)gaps.push(timestamp-last);
   last=timestamp;
   // Native color pickers can dispatch multiple input events before a paint.
   for(let j=0;j<4;j++) {
     input.value='#'+(((i*4+j)*4789+123456)&0xffffff).toString(16).padStart(6,'0');
     input.dispatchEvent(new Event('input',{bubbles:true}));
   }
 }
 await new Promise(requestAnimationFrame);
 const stats=values=>{values.sort((a,b)=>a-b);return {medianMs:values[Math.floor(values.length/2)],p95Ms:values[Math.floor(values.length*.95)]}};
 return {events:400,previewCallbacks:window.themeSamples.length,callback:stats(window.themeSamples.slice(20)),frameGap:stats(gaps),gapsOver25ms:gaps.filter(x=>x>25).length};
}"""

def run(browser, label, js=None, css=None):
    context = browser.new_context(viewport={'width':1440,'height':1000}, color_scheme='light')
    context.add_init_script(INIT)
    if js:
        context.route('**/assets/theme-editor.js*', lambda route: route.fulfill(path=str(js.resolve()), content_type='application/javascript'))
    if css:
        context.route('**/assets/theme-editor.css*', lambda route: route.fulfill(path=str(css.resolve()), content_type='text/css'))
    page=context.new_page()
    page.goto('http://127.0.0.1:8088/')
    page.locator('.theme-trigger').click()
    algorithm=page.evaluate(ALGORITHM)
    cdp=context.new_cdp_session(page)
    cdp.send('Performance.enable')
    def metrics():
        return {entry['name']:entry['value'] for entry in cdp.send('Performance.getMetrics')['metrics']}
    before=metrics()
    drag=page.evaluate(DRAG)
    after=metrics()
    result={'label':label, 'algorithm':algorithm, 'drag':drag,
            'styleLayoutMs':{key:round((after[key]-before[key])*1000,3) for key in ['RecalcStyleDuration','LayoutDuration']}}
    context.close()
    return result

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge')
    results=[]
    for trial in range(2):
        # Reverse order on second trial to reduce systematic warmup bias.
        versions=[('before',args.baseline_js,args.baseline_css),('after',None,None)] if args.baseline_js else [('current',None,None)]
        if trial: versions.reverse()
        for label,js,css in versions:
            result=run(browser,label,js,css);result['trial']=trial+1;results.append(result)
    browser.close()
output=ROOT/'data'/'theme-benchmark.json'
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
print('Report:',output)
