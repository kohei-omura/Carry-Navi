// 画面の自動チェック（Playwright・ネットワーク不要）
//   node tests/ui/ui_check.js [スクショ保存先ディレクトリ]
// 1) 外部データ（指標名・ペア注記・エラー文）にHTMLが混ざっても実行されない（XSS）
// 2) 375px / 1280px で横スクロールが出ない
// 3) コンソールエラーが無い（Webフォント・外部連携の取得失敗は除く）
const http=require('http'),fs=require('fs'),path=require('path');
const {chromium}=require('playwright');
const ROOT=path.resolve(__dirname,'..','..'),OUT=process.argv[2]||null;
const EVIL='<img src=x onerror="window.__xss=(window.__xss||0)+1">';
function status(){
  const s=JSON.parse(fs.readFileSync(path.join(ROOT,'carry_status.json'),'utf8'));
  s.link=s.link||{};
  const t=new Date(Date.now()+9*3600e3+20*60e3).toISOString().slice(0,16).replace('T',' ');
  s.link.news=[{country:'USD',time:t,title:'NFP'+EVIL,min:20,pairs:['MXN_JPY']}];
  s.link.news_warn='警告'+EVIL;
  (s.universe||[]).forEach(u=>{u.note=u.note+EVIL;});
  (s.pairs||[]).forEach(p=>{p.reasons=(p.reasons||[]).concat([EVIL]);p.risk=true;p.risk_note=EVIL;
    p.news_hold={country:'USD',time:t,title:'FOMC'+EVIL,min:20};});
  return JSON.stringify(s);
}
const srv=http.createServer((q,r)=>{
  const u=new URL(q.url,'http://x');let f=decodeURIComponent(u.pathname);if(f==='/')f='/index.html';
  if(f==='/carry_status.json'){r.writeHead(200,{'Content-Type':'application/json'});return r.end(status());}
  if(f==='/px'){r.writeHead(500);return r.end('<b>boom</b>'+EVIL);}           // 壊れたWorker
  const p=path.join(ROOT,f);if(!p.startsWith(ROOT)||!fs.existsSync(p)){r.writeHead(404);return r.end();}
  const ct={'.html':'text/html','.json':'application/json','.js':'text/javascript','.png':'image/png'}[path.extname(p)]||'application/octet-stream';
  r.writeHead(200,{'Content-Type':ct});fs.createReadStream(p).pipe(r);
});
(async()=>{
  await new Promise(ok=>srv.listen(0,'127.0.0.1',ok));
  const base=`http://127.0.0.1:${srv.address().port}`;
  const b=await chromium.launch();let fail=[];
  for(const [w,h] of [[375,812],[1280,900]]){
    const ctx=await b.newContext({viewport:{width:w,height:h},serviceWorkers:'block'});
    const pg=await ctx.newPage(),errs=[];
    pg.on('pageerror',e=>errs.push(e.message));
    pg.on('console',m=>{if(m.type()==='error'&&!/Failed to load resource/.test(m.text()))errs.push(m.text());});
    await pg.route(/^https?:\/\/(?!127\.0\.0\.1)/,r=>r.abort());   // 外部には一切出ない
    await pg.addInitScript(u=>{try{localStorage.setItem('carry_worker',u+'/px');
      localStorage.setItem('carry_positions',JSON.stringify([{sym:'MXN_JPY',entry:8.4,lot:1,date:'2026-11-01',tp:8.6,sl:8.3}]));}catch(e){}},base);
    await pg.goto(base+'/index.html');await pg.waitForTimeout(1500);
    for(const t of ['signal','pos','pairs','set']){
      await pg.click(`.tb[data-tab="${t}"]`);await pg.waitForTimeout(250);
      const ov=await pg.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
      if(ov>0)fail.push(`${w}px ${t}タブで横スクロール ${ov}px`);
      if(OUT)await pg.screenshot({path:path.join(OUT,`ui_${w}_${t}.png`),fullPage:true});
    }
    const x=await pg.evaluate(()=>({xss:window.__xss||0,imgs:document.querySelectorAll('img[src="x"]').length}));
    if(x.xss||x.imgs)fail.push(`${w}px XSS: 実行${x.xss}回・注入タグ${x.imgs}個`);
    if(errs.length)fail.push(`${w}px コンソールエラー: ${errs.join(' | ')}`);
    await ctx.close();
  }
  await b.close();srv.close();
  if(fail.length){console.log('NG\n- '+fail.join('\n- '));process.exit(1);}
  console.log('OK: XSSなし・横スクロールなし・コンソールエラーなし（375px/1280px）');
})().catch(e=>{console.error(e);process.exit(2);});
