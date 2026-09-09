#property strict
#property script_show_inputs

// Read-only symbol/account export. Run from MT5; it never sends trade requests.
input string InpSymbol = "USDJPYc";
input string InpFile = "usdjpyc_symbol_properties.json";

string Q(const string value) {
   string escaped = value;
   StringReplace(escaped, "\\", "\\\\");
   StringReplace(escaped, "\"", "\\\"");
   return "\"" + escaped + "\"";
}

void OnStart() {
   if(!SymbolSelect(InpSymbol, true)) {
      Print("Cannot select ", InpSymbol, "; check the exact Market Watch symbol.");
      return;
   }
   MqlTick tick;
   if(!SymbolInfoTick(InpSymbol, tick)) {
      Print("No current tick for ", InpSymbol);
      return;
   }

   int handle = FileOpen(InpFile, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(handle == INVALID_HANDLE) {
      Print("FileOpen failed: ", GetLastError());
      return;
   }

   double point = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   double pip = ((int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS)==3 || (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS)==5) ? point*10.0 : point;
   string body = "{\n";
   body += "  \"capture_status\": \"captured_from_mt5\",\n";
   body += "  \"captured_at_utc\": " + Q(TimeToString(TimeGMT(), TIME_DATE|TIME_SECONDS)+"Z") + ",\n";
   body += "  \"symbol\": {\n";
   body += "    \"name\": " + Q(InpSymbol) + ",\n";
   body += "    \"digits\": " + IntegerToString((int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS)) + ",\n";
   body += "    \"point\": " + DoubleToString(point, 10) + ",\n";
   body += "    \"pip_size\": " + DoubleToString(pip, 10) + ",\n";
   body += "    \"contract_size\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_CONTRACT_SIZE), 10) + ",\n";
   body += "    \"tick_size\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_SIZE), 10) + ",\n";
   body += "    \"tick_value\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_VALUE), 10) + ",\n";
   body += "    \"tick_value_profit\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_VALUE_PROFIT), 10) + ",\n";
   body += "    \"tick_value_loss\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_VALUE_LOSS), 10) + ",\n";
   body += "    \"volume_min\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN), 10) + ",\n";
   body += "    \"volume_step\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP), 10) + ",\n";
   body += "    \"volume_max\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX), 10) + ",\n";
   body += "    \"stops_level_points\": " + IntegerToString((int)SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_STOPS_LEVEL)) + ",\n";
   body += "    \"freeze_level_points\": " + IntegerToString((int)SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_FREEZE_LEVEL)) + ",\n";
   body += "    \"swap_long\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_SWAP_LONG), 10) + ",\n";
   body += "    \"swap_short\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_SWAP_SHORT), 10) + ",\n";
   body += "    \"swap_mode\": " + IntegerToString((int)SymbolInfoInteger(InpSymbol, SYMBOL_SWAP_MODE)) + ",\n";
   body += "    \"triple_swap_day\": " + IntegerToString((int)SymbolInfoInteger(InpSymbol, SYMBOL_SWAP_ROLLOVER3DAYS)) + ",\n";
   body += "    \"trade_calc_mode\": " + IntegerToString((int)SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_CALC_MODE)) + ",\n";
   body += "    \"margin_initial\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_MARGIN_INITIAL), 10) + ",\n";
   body += "    \"margin_maintenance\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_MARGIN_MAINTENANCE), 10) + ",\n";
   body += "    \"margin_long\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_MARGIN_LONG), 10) + ",\n";
   body += "    \"margin_short\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_MARGIN_SHORT), 10) + ",\n";
   body += "    \"margin_hedged\": " + DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_MARGIN_HEDGED), 10) + "\n";
   body += "  },\n";
   body += "  \"account\": {\n";
   body += "    \"currency\": " + Q(AccountInfoString(ACCOUNT_CURRENCY)) + ",\n";
   body += "    \"leverage\": " + IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE)) + ",\n";
   body += "    \"balance\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 10) + ",\n";
   body += "    \"equity\": " + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 10) + "\n";
   body += "  },\n";
   body += "  \"quote\": {\n";
   body += "    \"bid\": " + DoubleToString(tick.bid, 10) + ",\n";
   body += "    \"ask\": " + DoubleToString(tick.ask, 10) + ",\n";
   body += "    \"spread_pips\": " + DoubleToString((tick.ask-tick.bid)/pip, 5) + "\n";
   body += "  }\n}\n";
   FileWriteString(handle, body);
   FileClose(handle);
   Print("Saved read-only export to Common\\Files\\", InpFile, ". Copy it to broker_validation/output/.");
}
