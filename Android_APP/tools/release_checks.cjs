// Test-only responses; no data or credentials from this file enter the APK.
module.exports=async({evaluate,check,cdp})=>{
  await evaluate("updateUrl='';await checkForUpdates()");
  await check("document.querySelector('#account-detail-content .error-box').textContent==='无API接口' && !document.getElementById('account-detail-dialog').textContent.includes('已是最新版')",'Missing release endpoint never claims latest');
  await evaluate("document.getElementById('account-detail-dialog').close()");
  await cdp('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});
  await evaluate("await checkForUpdates()");
  await check("document.querySelector('#account-detail-content .error-box').textContent==='无网络'",'Offline update reports no network');
  await cdp('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  await evaluate("document.getElementById('account-detail-dialog').close();updateUrl='https://updates.test.invalid/latest.json';window.manifest={packageName:'com.giraffeslovebeauty.acmforever',versionCode:APP_VERSION_CODE,versionName:'0.1.12',apkUrl:'https://updates.test.invalid/app.apk',sha256:'a'.repeat(64)};window.fetch=async()=>new Response(JSON.stringify(manifest));await checkForUpdates()");
  await check("document.getElementById('account-detail-content').textContent.includes('已是最新版')",'Valid current manifest reports latest');
  await evaluate("manifest.versionCode=APP_VERSION_CODE+1;manifest.versionName='0.1.13';await checkForUpdates()");
  await check("document.getElementById('download-update').textContent==='更新0.1.13版本' && document.getElementById('download-update').href==='https://updates.test.invalid/app.apk'",'New version offers real HTTPS APK');
  await evaluate("manifest.apkUrl='http://unsafe.invalid/app.apk';await checkForUpdates()");
  await check("!!document.querySelector('#account-detail-content .error-box') && !document.getElementById('download-update')",'HTTP APK cannot be offered');
  await evaluate("window.updateCalls=0;window.fetch=async()=>{updateCalls++;return new Promise(resolve=>window.releaseUpdate=()=>resolve(new Response('{}',{status:404})));};window.updatePending=checkForUpdates();checkForUpdates();checkForUpdates()");
  await check("updateCalls===1 && updateChecking",'Duplicate update clicks share pending check');
  await evaluate("releaseUpdate();await updatePending;document.getElementById('account-detail-dialog').close();clearAccount();apiBase='https://test.invalid';await show('account')");
  await check("!!document.getElementById('save-password') && !document.getElementById('account-area').textContent.includes('连接与更新设置')",'Login save password control and simplified update entry exist');
  await evaluate("window.PasswordCredential=class{constructor(value){Object.assign(this,value)}};Object.defineProperty(navigator,'credentials',{configurable:true,value:{store:async value=>window.storedCredential=value}});await show('account');document.getElementById('save-password').checked=true;document.getElementById('save-password').dispatchEvent(new Event('change'));window.fetch=async address=>new Response(JSON.stringify(address.endsWith('/auth/me')?{authenticated:true,role:'member',csrf_token:'test-token'}:address.endsWith('/me/profile')?{user:{name:'Contract'},platform_counts:{},total_count:0}:[]));document.getElementById('qq').value='90000001';document.getElementById('password').value='Synthetic-Password!';await document.getElementById('login-form').onsubmit({preventDefault(){}})");
  await check("storedCredential.id==='90000001' && storedCredential.password==='Synthetic-Password!' && !Object.values(localStorage).some(value=>value.includes('Synthetic-Password!')||value.includes('test-token'))",'Opt-in password passes only to browser credential manager');
  await evaluate("delete window.storedCredential;clearAccount();updateUrl='';localStorage.clear()");
};
