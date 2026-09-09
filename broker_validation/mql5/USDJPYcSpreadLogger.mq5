#property strict
#property version   "1.0"

// Read-only timer logger. It does not call any order or position function.
input string InpSymbol = "USDJPYc";
input int InpIntervalSeconds = 60;
input string InpFile = "usdjpyc_spread_log.csv";

int OnInit() {
   if(InpIntervalSeconds < 30 || !SymbolSelect(InpSymbol, true)) return INIT_PARAMETERS_INCORRECT;
   EventSetTimer(InpIntervalSeconds);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); }

void OnTimer() {
   MqlTick tick;
   if(!SymbolInfoTick(InpSymbol, tick) || tick.bid <= 0 || tick.ask <= 0) return;
   double point = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   double pip = (digits == 3 || digits == 5) ? point * 10.0 : point;
   bool exists = FileIsExist(InpFile, FILE_COMMON);
   int handle = FileOpen(InpFile, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(handle == INVALID_HANDLE) { Print("Spread logger FileOpen failed: ", GetLastError()); return; }
   if(!exists) FileWrite(handle, "timestamp_utc", "bid", "ask", "spread_pips");
   FileSeek(handle, 0, SEEK_END);
   FileWrite(handle, TimeToString(TimeGMT(), TIME_DATE|TIME_SECONDS)+"Z", DoubleToString(tick.bid, digits), DoubleToString(tick.ask, digits), DoubleToString((tick.ask-tick.bid)/pip, 5));
   FileClose(handle);
}
