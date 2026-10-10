import argparse, json, logging, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; OUT=ROOT/'output'
for p in (DATA,OUT): p.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[logging.FileHandler(OUT/'run.log',encoding='utf-8'),logging.StreamHandler()])
LOG=logging.getLogger('lab')
COL={'日期':'date','开盘':'open','收盘':'close','最高':'high','最低':'low','成交量':'volume','成交额':'amount'}

def download(symbols,start,end,refresh=False):
    import akshare as ak
    ok=[]; errors={}
    for code in symbols:
        path=DATA/f'{code}.csv'
        if path.exists() and not refresh: ok.append(code);continue
        try:
            df=ak.stock_zh_a_hist(symbol=code,period='daily',start_date=start,end_date=end,adjust='')
            if df is None or len(df)<100: raise ValueError('不足100行历史记录')
            df=df.rename(columns=COL)
            df[['date','open','high','low','close','volume','amount']].to_csv(path,index=False)
            ok.append(code)
        except Exception as e:
            errors[code]=str(e);LOG.warning('%s download failed: %s',code,e)
        time.sleep(.25)
    (OUT/'coverage.json').write_text(json.dumps({'requested':len(symbols),'ok':len(ok),'failed':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    if not ok: raise RuntimeError('无可用行情数据；没有使用虚构数据替代')
    return ok

def read(code):
    d=pd.read_csv(DATA/f'{code}.csv',dtype={'date':str})
    if not {'date','open','high','low','close','volume','amount'}.issubset(d): raise ValueError('缺少必需字段')
    d=d.sort_values('date').drop_duplicates('date').reset_index(drop=True)
    for c in ['open','high','low','close','volume','amount']: d[c]=pd.to_numeric(d[c],errors='coerce')
    if d[['open','high','low','close','volume']].isna().any().any() or (d[['open','high','low','close']]<=0).any().any():raise ValueError('异常行情')
    if (d.high<d[['open','close','low']].max(axis=1)).any() or (d.low>d[['open','close']].min(axis=1)).any():raise ValueError('OHLC不一致')
    return d

def features(d):
    d=d.copy();c=d.close;v=d.volume
    d['ma20']=c.rolling(20).mean();d['ma60']=c.rolling(60).mean()
    d['vol20']=v.shift(1).rolling(20).mean()
    d['prev20high']=d.high.shift(1).rolling(20).max()
    d['momentum20']=c/c.shift(20)-1
    d['volatility20']=c.pct_change().rolling(20).std()
    d['baseline']=(c>d.ma20)&(d.ma20>d.ma60)&(c>d.prev20high)&(v>1.5*d.vol20)&(d.amount>=2e7)
    # AI候选研究的可复现实验代理：在同一基础信号中进一步依据动量、波动和流动性排序。
    # 没有LLM连接时不得称作真实LLM决策。
    d['ai_score']=(d.momentum20.clip(-.2,.3).fillna(0)*100)-(d.volatility20.fillna(.1)*60)+np.log1p(d.amount.clip(lower=0))/5
    d['ai_candidate']=d.baseline & (d.momentum20>0.06) & (d.volatility20<.055)
    return d

def scan(symbols):
    rows=[]
    for code in symbols:
        try:
            d=features(read(code));x=d.iloc[-1]
            if bool(x.baseline): rows.append({'code':code,'date':x.date,'close':float(x.close),'baseline':True,'ai_candidate':bool(x.ai_candidate),'ai_score':round(float(x.ai_score),4)})
        except Exception as e: LOG.warning('scan %s: %s',code,e)
    out=pd.DataFrame(rows,columns=['code','date','close','baseline','ai_candidate','ai_score'])
    out.to_csv(OUT/'signals.csv',index=False);LOG.info('scan signals=%s',len(out));return out

def backtest(symbols,mode,capital=100000,fee=.0005,slip=.001,max_positions=5):
    # 每日收盘信号；下一交易日开盘模拟成交；当日收盘后才能决定下一日退出。
    # 无分红配股调整、精确涨跌停价与历史成分股：仅研究原型，不得当成生产级回测。
    universe={}
    for s in symbols:
        try: universe[s]=features(read(s)).set_index('date')
        except Exception as e:LOG.warning('backtest skip %s %s',s,e)
    dates=sorted(set().union(*(set(d.index) for d in universe.values()))) if universe else []
    cash=float(capital);positions={};pending={};trades=[];equity=[]
    for date in dates:
        # 先执行上一交易日形成的订单；未有当日数据则不成交
        for s,action in list(pending.items()):
            if s not in universe or date not in universe[s].index:continue
            row=universe[s].loc[date];price=float(row.open)
            if action=='sell' and s in positions:
                pos=positions.pop(s);cash+=pos['shares']*price*(1-fee-slip)
                trades.append({'mode':mode,'code':s,'entry':pos['date'],'exit':date,'entry_price':pos['price'],'exit_price':price,'shares':pos['shares'],'pnl':pos['shares']*(price*(1-fee-slip)-pos['price']*(1+fee+slip))})
            elif action=='buy' and s not in positions and len(positions)<max_positions:
                budget=min(cash,capital/max_positions);shares=int(budget/(price*(1+fee+slip))//100)*100
                if shares>0:
                    cash-=shares*price*(1+fee+slip);positions[s]={'shares':shares,'price':price,'date':date,'bars':0}
            pending.pop(s,None)
        marked=cash
        for s,pos in positions.items():
            if date in universe[s].index:
                row=universe[s].loc[date];pos['bars']+=1
                marked+=pos['shares']*float(row.close)
                if pos['bars']>=30 or row.close<row.ma20 or row.close<pos['price']*.95:pending[s]='sell'
            else:
                # 无行情时采用最后已知收盘价估值，不可当成可成交价格
                old=universe[s].loc[:date]
                if len(old):marked+=pos['shares']*float(old.iloc[-1].close)
        # 同一日两组从同一基线候选池选择；AI代理只改变排序和额外过滤
        slots=max_positions-len(positions)-sum(1 for x in pending.values() if x=='buy')
        if slots>0:
            candidates=[]
            for s,d in universe.items():
                if s in positions or s in pending or date not in d.index:continue
                r=d.loc[date]
                if bool(r.ai_candidate if mode=='ai_proxy' else r.baseline):candidates.append((s,float(r.ai_score if mode=='ai_proxy' else r.momentum20)))
            for s,_ in sorted(candidates,key=lambda t:(-t[1],t[0]))[:slots]:pending[s]='buy'
        equity.append({'date':date,'mode':mode,'equity':round(marked,2),'cash':round(cash,2),'positions':len(positions)})
    return pd.DataFrame(equity),pd.DataFrame(trades,columns=['mode','code','entry','exit','entry_price','exit_price','shares','pnl'])

def report(eq,tr):
    if eq.empty:return {}
    v=eq.equity.astype(float);dd=v/v.cummax()-1
    return {'mode':eq['mode'].iloc[0],'first_date':eq.date.iloc[0],'last_date':eq.date.iloc[-1], 'net_return':round(float(v.iloc[-1]/v.iloc[0]-1),5),'max_drawdown':round(float(dd.min()),5),'closed_trades':len(tr),'win_rate':round(float((tr.pnl>0).mean()),5) if len(tr) else None,'ending_equity':float(v.iloc[-1])}

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['fetch','scan','evaluate','all']);p.add_argument('--symbols',default='000001,600036,600519,000858,002594,300750');p.add_argument('--start',default='20220101');p.add_argument('--end',default='20261010');p.add_argument('--refresh',action='store_true');a=p.parse_args()
    symbols=[x.strip() for x in a.symbols.split(',') if x.strip()]
    if a.command in ('fetch','all'):download(symbols,a.start,a.end,a.refresh)
    if a.command in ('scan','all'):scan(symbols)
    if a.command in ('evaluate','all'):
        summaries=[]
        for mode in ('baseline','ai_proxy'):
            eq,tr=backtest(symbols,mode);eq.to_csv(OUT/f'equity_{mode}.csv',index=False);tr.to_csv(OUT/f'trades_{mode}.csv',index=False);summaries.append(report(eq,tr))
        (OUT/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8');LOG.info('summary %s',summaries)
if __name__=='__main__':main()
