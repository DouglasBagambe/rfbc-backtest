#property strict
#property version   "1.00"
#property description "G's Fx101 first-party MT5 execution bridge for GoatFunded Stride"

// Live broker operations are deliberately absent pending critical-path validation.

enum FX101_MODE
  {
   MODE_OFF=0,
   MODE_OBSERVE=1,
   MODE_SHADOW=2,
   MODE_AUTO=3
  };

input string InpApiBase="https://rfbc-usdjpy-monitor.onrender.com";
input string InpBridgeToken="";
input long   InpExpectedLogin=315307814;
input string InpExpectedServer="GoatFunded-Server";
input FX101_MODE InpMode=MODE_SHADOW;
input int    InpPollSeconds=5;
input double InpPerTradeRiskCapPct=0.50;
input double InpAggregateRiskGuardPct=0.75;
input double InpFloatingLossGuardPct=0.80;
input double InpDailyDdGuardPct=2.50;
input double InpTrailingDdGuardPct=4.50;
input double InpInitialBalance=2500.0;
input int    InpFirmResetHourUTC=22;
input ulong  InpMagic=5010101;


double g_high_water=0.0;
double g_daily_anchor=0.0;
string g_day_key="";
string g_last_command="";

string EscapeJson(string s)
  {
   StringReplace(s,"\\","\\\\");
   StringReplace(s,"\"","\\\"");
   StringReplace(s,"\r"," ");
   StringReplace(s,"\n"," ");
   return s;
  }

string SideFromPosition(const long type)
  {
   return type==POSITION_TYPE_BUY ? "BUY" : "SELL";
  }

string SideFromOrder(const long type)
  {
   if(type==ORDER_TYPE_BUY || type==ORDER_TYPE_BUY_LIMIT || type==ORDER_TYPE_BUY_STOP || type==ORDER_TYPE_BUY_STOP_LIMIT)
      return "BUY";
   return "SELL";
  }

string CurrentDayKey()
  {
   datetime now=TimeGMT();
   long secs=(long)now-(InpFirmResetHourUTC*3600);
   MqlDateTime dt;
   TimeToStruct((datetime)secs,dt);
   return StringFormat("%04d-%02d-%02d",dt.year,dt.mon,dt.day);
  }

void UpdateRiskAnchors()
  {
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   double balance=AccountInfoDouble(ACCOUNT_BALANCE);
   if(g_high_water<=0.0)
      g_high_water=MathMax(InpInitialBalance,equity);
   if(equity>g_high_water)
      g_high_water=equity;

   string key=CurrentDayKey();
   if(g_day_key!=key)
     {
      g_day_key=key;
      g_daily_anchor=MathMax(balance,equity);
     }
   else if(g_daily_anchor<=0.0)
      g_daily_anchor=MathMax(balance,equity);
  }

double SymbolRiskUsd(string symbol,double volume,double entry,double stop)
  {
   if(volume<=0.0 || entry<=0.0 || stop<=0.0)
      return 0.0;
   double tick_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
   double tick_value=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tick_value<=0.0)
      tick_value=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE);
   if(tick_size<=0.0 || tick_value<=0.0)
      return 0.0;
   return MathAbs(entry-stop)/tick_size*tick_value*volume;
  }

double OpenRiskUsd()
  {
   double total=0.0;
   for(int i=0;i<PositionsTotal();i++)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket))
         continue;
      string symbol=PositionGetString(POSITION_SYMBOL);
      double volume=PositionGetDouble(POSITION_VOLUME);
      double entry=PositionGetDouble(POSITION_PRICE_OPEN);
      double sl=PositionGetDouble(POSITION_SL);
      if(sl<=0.0)
         return DBL_MAX;
      total+=SymbolRiskUsd(symbol,volume,entry,sl);
     }
   for(int i=0;i<OrdersTotal();i++)
     {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0 || !OrderSelect(ticket))
         continue;
      string symbol=OrderGetString(ORDER_SYMBOL);
      double volume=OrderGetDouble(ORDER_VOLUME_CURRENT);
      double entry=OrderGetDouble(ORDER_PRICE_OPEN);
      double sl=OrderGetDouble(ORDER_SL);
      if(sl<=0.0)
         return DBL_MAX;
      total+=SymbolRiskUsd(symbol,volume,entry,sl);
     }
   return total;
  }

bool LocalAccountGuard(string &reason)
  {
   if((long)AccountInfoInteger(ACCOUNT_LOGIN)!=InpExpectedLogin)
     {
      reason="wrong_account";
      return false;
     }
   if(AccountInfoString(ACCOUNT_SERVER)!=InpExpectedServer)
     {
      reason="wrong_server";
      return false;
     }
   UpdateRiskAnchors();
   double balance=AccountInfoDouble(ACCOUNT_BALANCE);
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   double floating=AccountInfoDouble(ACCOUNT_PROFIT);
   if(balance<=0.0 || equity<=0.0)
     {
      reason="invalid_equity";
      return false;
     }
   if(floating<-(balance*InpFloatingLossGuardPct/100.0))
     {
      reason="floating_loss_guard";
      return false;
     }
   if(equity<g_daily_anchor*(1.0-InpDailyDdGuardPct/100.0))
     {
      reason="daily_dd_guard";
      return false;
     }
   double floor=MathMin(InpInitialBalance,g_high_water-InpInitialBalance*InpTrailingDdGuardPct/100.0);
   if(equity<=floor)
     {
      reason="trailing_dd_guard";
      return false;
     }
   return true;
  }

bool HasSymbolExposure(string symbol,string side,string &reason)
  {
   for(int i=0;i<PositionsTotal();i++)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL)!=symbol)
         continue;
      string existing=SideFromPosition(PositionGetInteger(POSITION_TYPE));
      reason=(existing==side ? "duplicate_symbol" : "hedging_prohibited");
      return true;
     }
   for(int i=0;i<OrdersTotal();i++)
     {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0 || !OrderSelect(ticket))
         continue;
      if(OrderGetString(ORDER_SYMBOL)!=symbol)
         continue;
      string existing=SideFromOrder(OrderGetInteger(ORDER_TYPE));
      reason=(existing==side ? "duplicate_symbol_order" : "hedging_prohibited");
      return true;
     }
   return false;
  }

double NormalizeVolume(string symbol,double raw)
  {
   double vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   if(step<=0.0)
      return 0.0;
   double v=MathFloor(raw/step+1e-9)*step;
   v=MathMin(vmax,v);
   if(v<vmin-1e-12)
      return 0.0;
   int digits=2;
   if(step<0.01) digits=3;
   if(step<0.001) digits=4;
   return NormalizeDouble(v,digits);
  }

double RiskSizedVolume(string symbol,double entry,double stop,double risk_pct,double requested)
  {
   double balance=AccountInfoDouble(ACCOUNT_BALANCE);
   double risk_money=balance*risk_pct/100.0;
   double tick_size=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
   double tick_value=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tick_value<=0.0)
      tick_value=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE);
   if(tick_size<=0.0 || tick_value<=0.0 || MathAbs(entry-stop)<=0.0)
      return 0.0;
   double per_lot=MathAbs(entry-stop)/tick_size*tick_value;
   if(per_lot<=0.0)
      return 0.0;
   double by_risk=NormalizeVolume(symbol,risk_money/per_lot);
   double req=NormalizeVolume(symbol,requested);
   if(by_risk<=0.0)
      return 0.0;
   if(req<=0.0)
      return by_risk;
   return MathMin(by_risk,req);
  }

string PositionJson()
  {
   string out="[";
   bool first=true;
   for(int i=0;i<PositionsTotal();i++)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket))
         continue;
      string symbol=PositionGetString(POSITION_SYMBOL);
      double volume=PositionGetDouble(POSITION_VOLUME);
      double entry=PositionGetDouble(POSITION_PRICE_OPEN);
      double sl=PositionGetDouble(POSITION_SL);
      double risk=sl>0.0 ? SymbolRiskUsd(symbol,volume,entry,sl) : 1e12;
      if(!first) out+=",";
      first=false;
      out+=StringFormat("{\"ticket\":\"%I64u\",\"symbol\":\"%s\",\"side\":\"%s\",\"volume\":%.8f,\"entry\":%.10f,\"sl\":%.10f,\"tp\":%.10f,\"profit\":%.2f,\"risk_usd\":%.2f}",
                        ticket,EscapeJson(symbol),SideFromPosition(PositionGetInteger(POSITION_TYPE)),volume,entry,sl,
                        PositionGetDouble(POSITION_TP),PositionGetDouble(POSITION_PROFIT),risk);
     }
   out+="]";
   return out;
  }

string OrdersJson()
  {
   string out="[";
   bool first=true;
   for(int i=0;i<OrdersTotal();i++)
     {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0 || !OrderSelect(ticket))
         continue;
      string symbol=OrderGetString(ORDER_SYMBOL);
      double volume=OrderGetDouble(ORDER_VOLUME_CURRENT);
      double entry=OrderGetDouble(ORDER_PRICE_OPEN);
      double sl=OrderGetDouble(ORDER_SL);
      double risk=sl>0.0 ? SymbolRiskUsd(symbol,volume,entry,sl) : 1e12;
      if(!first) out+=",";
      first=false;
      out+=StringFormat("{\"ticket\":\"%I64u\",\"symbol\":\"%s\",\"side\":\"%s\",\"volume\":%.8f,\"entry\":%.10f,\"sl\":%.10f,\"tp\":%.10f,\"risk_usd\":%.2f}",
                        ticket,EscapeJson(symbol),SideFromOrder(OrderGetInteger(ORDER_TYPE)),volume,entry,sl,
                        OrderGetDouble(ORDER_TP),risk);
     }
   out+="]";
   return out;
  }

bool Http(string method,string path,string body,string &response)
  {
   if(StringLen(InpBridgeToken)<16)
     {
      Print("FX101 bridge token missing/too short.");
      return false;
     }
   string url=InpApiBase+path;
   string headers="Content-Type: application/json\r\nX-FX101-MT5-Token: "+InpBridgeToken+"\r\n";
   char data[];
   char result[];
   StringToCharArray(body,data,0,WHOLE_ARRAY,CP_UTF8);
   string result_headers;
   ResetLastError();
   int code=WebRequest(method,url,headers,10000,data,result,result_headers);
   if(code<0)
     {
      Print("WebRequest failed ",GetLastError()," ",url);
      return false;
     }
   response=CharArrayToString(result,0,-1,CP_UTF8);
   if(code<200 || code>=300)
     {
      Print("FX101 HTTP ",code,": ",response);
      return false;
     }
   return true;
  }

string JsonString(string json,string key)
  {
   string needle="\""+key+"\":";
   int p=StringFind(json,needle);
   if(p<0) return "";
   p+=StringLen(needle);
   while(p<StringLen(json) && StringGetCharacter(json,p)==' ') p++;
   if(p>=StringLen(json) || StringGetCharacter(json,p)!='\"') return "";
   p++;
   int e=p;
   while(e<StringLen(json))
     {
      if(StringGetCharacter(json,e)=='\"' && StringGetCharacter(json,e-1)!='\\') break;
      e++;
     }
   return StringSubstr(json,p,e-p);
  }

double JsonNumber(string json,string key)
  {
   string needle="\""+key+"\":";
   int p=StringFind(json,needle);
   if(p<0) return 0.0;
   p+=StringLen(needle);
   while(p<StringLen(json) && StringGetCharacter(json,p)==' ') p++;
   int e=p;
   while(e<StringLen(json))
     {
      ushort c=StringGetCharacter(json,e);
      if(c==',' || c=='}' || c==']') break;
      e++;
     }
   return StringToDouble(StringSubstr(json,p,e-p));
  }

bool JsonNullCommand(string json)
  {
   return StringFind(json,"\"command\":null")>=0;
  }

void SendSnapshot()
  {
   UpdateRiskAnchors();
   string body=StringFormat(
      "{\"login\":%I64d,\"server\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"free_margin\":%.2f,\"floating_pnl\":%.2f,\"day_key\":\"%s\",\"daily_anchor\":%.2f,\"high_water_equity\":%.2f,\"terminal_connected\":%s,\"trade_allowed\":%s,\"positions\":%s,\"orders\":%s}",
      AccountInfoInteger(ACCOUNT_LOGIN),EscapeJson(AccountInfoString(ACCOUNT_SERVER)),
      AccountInfoDouble(ACCOUNT_BALANCE),AccountInfoDouble(ACCOUNT_EQUITY),
      AccountInfoDouble(ACCOUNT_MARGIN_FREE),AccountInfoDouble(ACCOUNT_PROFIT),
      g_day_key,g_daily_anchor,g_high_water,
      TerminalInfoInteger(TERMINAL_CONNECTED)?"true":"false",
      TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)?"true":"false",
      PositionJson(),OrdersJson());
   string response;
   Http("POST","/fx101/mt5/snapshot",body,response);
  }

void Ack(string command_id,string status,string detail,string ticket="")
  {
   string body=StringFormat("{\"command_id\":\"%s\",\"status\":\"%s\",\"detail\":\"%s\",\"broker_ticket\":\"%s\"}",
                            EscapeJson(command_id),EscapeJson(status),EscapeJson(detail),EscapeJson(ticket));
   string response;
   Http("POST","/fx101/mt5/ack",body,response);
  }

bool ValidateSymbolTrade(string symbol,double entry,double sl,double tp,string &reason)
  {
   if(!SymbolSelect(symbol,true))
     {
      reason="symbol_unavailable";
      return false;
     }
   long trade_mode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);
   if(trade_mode==SYMBOL_TRADE_MODE_DISABLED)
     {
      reason="symbol_trade_disabled";
      return false;
     }
   int stops=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
   if(stops>0 && (MathAbs(entry-sl)<stops*point || MathAbs(tp-entry)<stops*point))
     {
      reason="broker_stops_level";
      return false;
     }
   return true;
  }

bool ExecuteCommand(string json,string &detail,string &ticket)
  {
   string command_id=JsonString(json,"command_id");
   string symbol=JsonString(json,"symbol");
   string side=JsonString(json,"side");
   string order_type=JsonString(json,"order_type");
   double entry=JsonNumber(json,"entry");
   double stop=JsonNumber(json,"stop");
   double target=JsonNumber(json,"target");
   double requested=JsonNumber(json,"requested_volume");
   double risk_pct=JsonNumber(json,"risk_pct");
   double stop_trigger=JsonNumber(json,"stop_trigger");

   if(command_id=="" || symbol=="" || (side!="BUY" && side!="SELL"))
     {
      detail="malformed_command";
      return false;
     }
   if(command_id==g_last_command)
     {
      detail="duplicate_command";
      return false;
     }
   if(risk_pct<=0.0 || risk_pct>InpPerTradeRiskCapPct+1e-9)
     {
      detail="risk_cap";
      return false;
     }
   string guard="";
   if(!LocalAccountGuard(guard))
     {
      detail=guard;
      return false;
     }
   if(HasSymbolExposure(symbol,side,guard))
     {
      detail=guard;
      return false;
     }

   double open_risk=OpenRiskUsd();
   double balance=AccountInfoDouble(ACCOUNT_BALANCE);
   if(open_risk==DBL_MAX)
     {
      detail="existing_position_without_sl";
      return false;
     }
   if((open_risk/balance*100.0)+risk_pct>InpAggregateRiskGuardPct+1e-9)
     {
      detail="aggregate_risk_guard";
      return false;
     }

   if(!ValidateSymbolTrade(symbol,entry,stop,target,guard))
     {
      detail=guard;
      return false;
     }

   double volume=RiskSizedVolume(symbol,entry,stop,risk_pct,requested);
   if(volume<=0.0)
     {
      detail="volume_below_broker_min_or_invalid_tick_value";
      return false;
     }
   double exact_risk=SymbolRiskUsd(symbol,volume,entry,stop);
   if(exact_risk>balance*InpPerTradeRiskCapPct/100.0+0.05)
     {
      detail="calculated_risk_exceeds_cap";
      return false;
     }

   if(InpMode!=MODE_AUTO)
     {
      detail=StringFormat("shadow_ok volume=%.4f risk=$%.2f",volume,exact_risk);
      g_last_command=command_id;
      return true;
     }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
     {
      detail="algo_trading_not_allowed";
      return false;
     }

   detail="auto_validation_incomplete";
   return false;
  }

void PollCommand()
  {
   if(InpMode==MODE_OFF || InpMode==MODE_OBSERVE)
      return;
   string response;
   string path=StringFormat("/fx101/mt5/command?login=%I64d",AccountInfoInteger(ACCOUNT_LOGIN));
   if(!Http("GET",path,"",response))
      return;
   if(JsonNullCommand(response))
      return;

   string command_id=JsonString(response,"command_id");
   if(command_id=="" || command_id==g_last_command)
      return;

   string server_mode=JsonString(response,"mode");
   if(server_mode=="AUTO" && InpMode!=MODE_AUTO)
     {
      // Local terminal mode is always authoritative. Never execute if local is SHADOW.
      string detail="",ticket="";
      bool ok=ExecuteCommand(response,detail,ticket);
      Ack(command_id,ok ? "SHADOW_OK" : "REJECTED",detail,ticket);
      return;
     }

   string detail="",ticket="";
   bool ok=ExecuteCommand(response,detail,ticket);
   if(InpMode==MODE_AUTO && server_mode=="AUTO")
      Ack(command_id,ok ? "EXECUTED" : "REJECTED",detail,ticket);
   else
      Ack(command_id,ok ? "SHADOW_OK" : "REJECTED",detail,ticket);
  }

int OnInit()
  {
   if(InpMode==MODE_AUTO)
     {
      Print("AUTO disabled: validation incomplete.");
      return INIT_PARAMETERS_INCORRECT;
     }
   UpdateRiskAnchors();
   EventSetTimer(MathMax(2,InpPollSeconds));
   Print("FX101 MT5 Bridge started. Mode=",EnumToString(InpMode),
         " Login=",AccountInfoInteger(ACCOUNT_LOGIN)," Server=",AccountInfoString(ACCOUNT_SERVER));
   if((long)AccountInfoInteger(ACCOUNT_LOGIN)!=InpExpectedLogin || AccountInfoString(ACCOUNT_SERVER)!=InpExpectedServer)
      Print("WARNING: account/server mismatch. Execution is fail-closed.");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   if(InpMode==MODE_OFF)
      return;
   SendSnapshot();
   PollCommand();
  }
