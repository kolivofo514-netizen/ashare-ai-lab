import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
ROOT=Path(__file__).resolve().parent
OUT=ROOT/"output"
SITE=ROOT/"site"
SITE.mkdir(exist_ok=True)
def csv(name):
    p=OUT/name
    if not p.exists(): return []
    try: return pd.read_csv(p).where(pd.notna(pd.read_csv(p)),None).to_dict(orient="records")
    except pd.errors.EmptyDataError: return []
def obj(name,default):
    p=OUT/name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
def build():
    coverage=obj("coverage.json",{})
    d={"generated_at":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),"coverage":coverage,"summary":obj("summary.json",[]),
       "signals":csv("signals.csv"),"trades_baseline":csv("trades_baseline.csv"),"trades_ai_proxy":csv("trades_ai_proxy.csv"),
       "equity_baseline":csv("equity_baseline.csv"),"equity_ai_proxy":csv("equity_ai_proxy.csv"),
       "verified_data":bool(coverage.get("ok",0)>0 and csv("equity_baseline.csv") and csv("equity_ai_proxy.csv"))}
    payload=json.dumps(d,ensure_ascii=False,allow_nan=False).replace("</","<\\/")
    html=(ROOT/"dashboard_template.html").read_text(encoding="utf-8").replace("__REPORT_JSON__",payload)
    (SITE/"index.html").write_text(html,encoding="utf-8")
    (SITE/"report.json").write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Generated",SITE/"index.html","verified_data=",d["verified_data"])
if __name__=="__main__":build()
