// index.html の carryEval（画面側のライブ再計算）を実ブラウザで実行して結果をJSONで返す
//   node tests/ui/eval_js.js input.json   … input = {rates:{...}, cases:[{symbol, ohlc:[[h,l,c],...]}]}
const fs=require('fs'),path=require('path');const {chromium}=require('playwright');
(async()=>{
  const inp=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
  const b=await chromium.launch();const pg=await (await b.newContext({serviceWorkers:'block'})).newPage();
  await pg.route(/^https?:/,r=>r.abort());
  await pg.goto('file://'+path.resolve(__dirname,'..','..','index.html'));
  const out=await pg.evaluate(inp=>{RATES=inp.rates;return inp.cases.map(c=>carryEval(c.symbol,c.ohlc));},inp);
  await b.close();process.stdout.write(JSON.stringify(out));
})().catch(e=>{console.error(e);process.exit(2);});
