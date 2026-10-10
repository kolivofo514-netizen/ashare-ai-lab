import unittest, tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from lab import features, backtest

class Checks(unittest.TestCase):
 def test_no_lookahead_breakout(self):
  n=90;d=pd.DataFrame({'date':pd.date_range('2024-01-01',periods=n,freq='B').strftime('%Y-%m-%d'),'open':np.linspace(10,20,n),'high':np.linspace(10.2,20.2,n),'low':np.linspace(9.8,19.8,n),'close':np.linspace(10,20,n),'volume':[100]*n,'amount':[3e7]*n})
  a=features(d);d.loc[n-1,'close']=200;d.loc[n-1,'high']=200;b=features(d)
  self.assertEqual(a.loc[n-2,'prev20high'],b.loc[n-2,'prev20high'])
  self.assertEqual(a.loc[n-2,'baseline'],b.loc[n-2,'baseline'])
 def test_future_bar_does_not_change_past_features(self):
  n=100;d=pd.DataFrame({'date':pd.date_range('2023-01-01',periods=n,freq='B').strftime('%Y-%m-%d'),'open':np.arange(n)+10.,'high':np.arange(n)+11.,'low':np.arange(n)+9.,'close':np.arange(n)+10.,'volume':[200]*n,'amount':[5e7]*n})
  a=features(d);d.loc[99,['open','high','close','volume']]=[2000,2001,2000,999999];b=features(d)
  pd.testing.assert_series_equal(a.ai_score.iloc[:99],b.ai_score.iloc[:99])
if __name__=='__main__':unittest.main()
