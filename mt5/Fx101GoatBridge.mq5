#property strict
#property version "2.00"
#property description "Fx101 broker observation and SHADOW validation. AUTO unavailable."

enum FX101_MODE { MODE_OFF=0, MODE_OBSERVE=1, MODE_SHADOW=2, MODE_AUTO=3 };
input string InpApiBase="https://rfbc-usdjpy-monitor.onrender.com";
input string InpCredentialFile="Fx101Bridge\\token.txt";
input long InpExpectedLogin=315307814;
input string InpExpectedServer="GoatFunded-Server";
input FX101_MODE InpMode=MODE_SHADOW;
input bool InpLocalKill=true;
input int InpPollSeconds=5;

// Deliberately no Trade library, OrderSend, position modification or close calls.
string g_key="";
string g_session="";
ulong g_counter=0;
bool g_snapshot_ok=false;
string g_symbols[];

string Escape(string s)
  {
   StringReplace(s,"\\","\\\\"); StringReplace(s,"\"","\\\"");
   StringReplace(s,"\r"," "); StringReplace(s,"\n"," "); StringReplace(s,"\t"," ");
   for(int i=0;i<StringLen(s);i++)
      if(StringGetCharacter(s,i)<32) StringSetCharacter(s,i,32);
   return s;
  }
string Num(double v) { return DoubleToString(v,10); }
bool FinitePositive(double v) { return MathIsValidNumber(v) && v>0; }
bool Hex(string s,int size)
  {
   if(StringLen(s)!=size) return false;
   for(int i=0;i<size;i++)
     {
      ushort c=StringGetCharacter(s,i);
      if(!((c>='0' && c<='9') || (c>='a' && c<='f'))) return false;
     }
   return true;
  }
void Bytes(string s,uchar &out[])
  {
   int n=StringToCharArray(s,out,0,WHOLE_ARRAY,CP_UTF8);
   if(n>0) ArrayResize(out,n-1); // Do not sign/send the UTF-8 terminating NUL.
  }
string DigestHex(uchar &digest[])
  {
   string s="";
   for(int i=0;i<ArraySize(digest);i++) s+=StringFormat("%02x",(uint)digest[i]);
   return s;
  }
string Hmac(string message,string key)
  {
   uchar k[],data[],dummy[],hashed[],inner[],outer[],digest[];
   Bytes(key,k); Bytes(message,data);
   if(ArraySize(k)>64)
     {
      if(CryptEncode(CRYPT_HASH_SHA256,k,dummy,hashed)!=32) return "";
      ArrayCopy(k,hashed); ArrayResize(k,32);
     }
   ArrayResize(inner,64+ArraySize(data)); ArrayResize(outer,96);
   for(int i=0;i<64;i++)
     {
      uchar b=(uchar)(i<ArraySize(k) ? k[i] : 0);
      inner[i]=(uchar)(b^0x36); outer[i]=(uchar)(b^0x5c);
     }
   ArrayCopy(inner,data,64,0,ArraySize(data));
   if(CryptEncode(CRYPT_HASH_SHA256,inner,dummy,digest)!=32) return "";
   ArrayCopy(outer,digest,64,0,32);
   if(CryptEncode(CRYPT_HASH_SHA256,outer,dummy,digest)!=32) return "";
   return DigestHex(digest);
  }
bool Equal(string a,string b)
  {
   if(StringLen(a)!=StringLen(b)) return false;
   uint result=0;
   for(int i=0;i<StringLen(a);i++) result|=(uint)(StringGetCharacter(a,i)^StringGetCharacter(b,i));
   return result==0;
  }
bool AccountBound()
  {
   return AccountInfoInteger(ACCOUNT_LOGIN)==InpExpectedLogin && AccountInfoString(ACCOUNT_SERVER)==InpExpectedServer
          && AccountInfoString(ACCOUNT_CURRENCY)=="USD";
  }
bool Killed() { return InpLocalKill || FileIsExist("Fx101Bridge\\KILL"); }

bool WritePrivate(string path,string body)
  {
   int h=FileOpen(path,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(h==INVALID_HANDLE) return false;
   uint n=FileWriteString(h,body); FileFlush(h); FileClose(h);
   return n==(uint)StringLen(body);
  }
string ReadPrivate(string path)
  {
   int h=FileOpen(path,FILE_READ|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(h==INVALID_HANDLE) return "";
   string out=FileReadString(h); FileClose(h); return out;
  }
void AddSymbol(string symbol)
  {
   for(int i=0;i<ArraySize(g_symbols);i++) if(g_symbols[i]==symbol) return;
   int n=ArraySize(g_symbols); ArrayResize(g_symbols,n+1); g_symbols[n]=symbol;
  }
string OrderName(long type)
  {
   switch((int)type)
     {
      case ORDER_TYPE_BUY: return "BUY";
      case ORDER_TYPE_SELL: return "SELL";
      case ORDER_TYPE_BUY_LIMIT: return "BUY_LIMIT";
      case ORDER_TYPE_SELL_LIMIT: return "SELL_LIMIT";
      case ORDER_TYPE_BUY_STOP: return "BUY_STOP";
      case ORDER_TYPE_SELL_STOP: return "SELL_STOP";
      case ORDER_TYPE_BUY_STOP_LIMIT: return "BUY_STOP_LIMIT";
      case ORDER_TYPE_SELL_STOP_LIMIT: return "SELL_STOP_LIMIT";
     }
   return "UNKNOWN";
  }
string PositionJson()
  {
   string s="[";
   for(int i=0;i<PositionsTotal();i++)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) return "";
      string symbol=PositionGetString(POSITION_SYMBOL); AddSymbol(symbol);
      string side=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? "BUY" : "SELL";
      if(i>0) s+=",";
      s+=StringFormat("{\"ticket\":\"%I64u\",\"symbol\":\"%s\",\"side\":\"%s\",\"order_type\":\"%s\",",ticket,Escape(symbol),side,side);
      s+="\"volume\":"+Num(PositionGetDouble(POSITION_VOLUME))+",\"entry\":"+Num(PositionGetDouble(POSITION_PRICE_OPEN));
      s+=",\"sl\":"+Num(PositionGetDouble(POSITION_SL))+",\"tp\":"+Num(PositionGetDouble(POSITION_TP));
      s+=",\"profit\":"+Num(PositionGetDouble(POSITION_PROFIT))+",\"swap\":"+Num(PositionGetDouble(POSITION_SWAP));
      s+=StringFormat(",\"magic\":%I64d,\"comment\":\"%s\",\"stop_limit\":0,\"expires_at\":0}",PositionGetInteger(POSITION_MAGIC),Escape(PositionGetString(POSITION_COMMENT)));
     }
   return s+"]";
  }
string OrdersJson()
  {
   string s="[";
   for(int i=0;i<OrdersTotal();i++)
     {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0 || !OrderSelect(ticket)) return "";
      string symbol=OrderGetString(ORDER_SYMBOL); AddSymbol(symbol);
      string type=OrderName(OrderGetInteger(ORDER_TYPE));
      string side=StringFind(type,"BUY")==0 ? "BUY" : "SELL";
      if(i>0) s+=",";
      s+=StringFormat("{\"ticket\":\"%I64u\",\"symbol\":\"%s\",\"side\":\"%s\",\"order_type\":\"%s\",",ticket,Escape(symbol),side,type);
      s+="\"volume\":"+Num(OrderGetDouble(ORDER_VOLUME_CURRENT))+",\"entry\":"+Num(OrderGetDouble(ORDER_PRICE_OPEN));
      s+=",\"sl\":"+Num(OrderGetDouble(ORDER_SL))+",\"tp\":"+Num(OrderGetDouble(ORDER_TP));
      s+=StringFormat(",\"profit\":0,\"swap\":0,\"magic\":%I64d,\"comment\":\"%s\",\"stop_limit\":%s,\"expires_at\":%I64d}",
            OrderGetInteger(ORDER_MAGIC),Escape(OrderGetString(ORDER_COMMENT)),Num(OrderGetDouble(ORDER_PRICE_STOPLIMIT)),OrderGetInteger(ORDER_TIME_EXPIRATION));
     }
   return s+"]";
  }
string SpecJson(string symbol)
  {
   if(!SymbolSelect(symbol,true)) return "";
   MqlTick quote;
   if(!SymbolInfoTick(symbol,quote)) return "";
   double vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN),mb=0,ms=0;
   if(!FinitePositive(vmin) || !OrderCalcMargin(ORDER_TYPE_BUY,symbol,vmin,quote.ask,mb) || !OrderCalcMargin(ORDER_TYPE_SELL,symbol,vmin,quote.bid,ms)) return "";
   long utc_quote=(long)quote.time+(long)TimeGMT()-(long)TimeTradeServer();
   string s="{\"tick_size\":"+Num(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE));
   s+=",\"tick_value_loss\":"+Num(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE_LOSS));
   s+=",\"tick_value_profit\":"+Num(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE_PROFIT));
   s+=",\"contract_size\":"+Num(SymbolInfoDouble(symbol,SYMBOL_TRADE_CONTRACT_SIZE));
   s+=",\"volume_min\":"+Num(vmin)+",\"volume_max\":"+Num(SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX));
   s+=",\"volume_step\":"+Num(SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP));
   s+=StringFormat(",\"stops_level\":%I64d,\"freeze_level\":%I64d,\"trade_mode\":%I64d,\"order_mode\":%I64d,\"quote_at\":%I64d",
         SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL),SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL),SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE),SymbolInfoInteger(symbol,SYMBOL_ORDER_MODE),utc_quote);
   s+=",\"bid\":"+Num(quote.bid)+",\"ask\":"+Num(quote.ask)+",\"point\":"+Num(SymbolInfoDouble(symbol,SYMBOL_POINT));
   s+=",\"margin_buy\":"+Num(mb/vmin)+",\"margin_sell\":"+Num(ms/vmin)+"}";
   return s;
  }
string Snapshot()
  {
   string positions=PositionJson(),orders=OrdersJson();
   if(positions=="" || orders=="") return "";
   string specs="{"; bool first=true;
   for(int i=0;i<ArraySize(g_symbols);i++)
     {
      string spec=SpecJson(g_symbols[i]);
      if(spec=="")
        {
         // Never omit specifications for active manual exposure.
         bool active=false;
         for(int j=0;j<PositionsTotal();j++) if(PositionGetTicket(j)>0 && PositionGetString(POSITION_SYMBOL)==g_symbols[i]) active=true;
         for(int j=0;j<OrdersTotal();j++) if(OrderGetTicket(j)>0 && OrderGetString(ORDER_SYMBOL)==g_symbols[i]) active=true;
         if(active) return "";
         continue;
        }
      if(!first) specs+=","; first=false;
      specs+="\""+Escape(g_symbols[i])+"\":"+spec;
     }
   specs+="}";
   double balance=AccountInfoDouble(ACCOUNT_BALANCE),equity=AccountInfoDouble(ACCOUNT_EQUITY);
   string peak_key=StringFormat("FX101.%I64d.peak",InpExpectedLogin);
   double peak=MathMax(2500,equity);
   if(GlobalVariableCheck(peak_key)) peak=MathMax(peak,GlobalVariableGet(peak_key));
   GlobalVariableSet(peak_key,peak); GlobalVariablesFlush();
   MqlDateTime dt; TimeToStruct(TimeGMT()-22*3600,dt);
   string day=StringFormat("%04d-%02d-%02d",dt.year,dt.mon,dt.day);
   string s=StringFormat("{\"login\":%I64d,\"server\":\"%s\",\"currency\":\"%s\",\"captured_at\":%I64d,",AccountInfoInteger(ACCOUNT_LOGIN),Escape(AccountInfoString(ACCOUNT_SERVER)),Escape(AccountInfoString(ACCOUNT_CURRENCY)),(long)TimeGMT());
   s+="\"balance\":"+Num(balance)+",\"equity\":"+Num(equity)+",\"free_margin\":"+Num(AccountInfoDouble(ACCOUNT_MARGIN_FREE));
   s+=",\"margin\":"+Num(AccountInfoDouble(ACCOUNT_MARGIN))+",\"floating_pnl\":"+Num(AccountInfoDouble(ACCOUNT_PROFIT));
   s+=",\"terminal_connected\":"+(TerminalInfoInteger(TERMINAL_CONNECTED) ? "true" : "false");
   s+=",\"daily_anchor\":"+Num(MathMax(balance,equity))+",\"high_water_equity\":"+Num(peak)+",\"anchors_verified\":false,\"day_key\":\""+day+"\"";
   s+=",\"positions\":"+positions+",\"orders\":"+orders+",\"symbols\":"+specs+"}";
   return s;
  }
bool Http(string method,string path,string body,string &response,string &nonce)
  {
   if(!Hex(g_key,64) || !AccountBound() || StringFind(InpApiBase,"https://")!=0) return false;
   string stamp=(string)(long)TimeGMT(); g_counter++;
   nonce=Hmac(g_session+":"+(string)g_counter+":"+(string)GetMicrosecondCount(),g_key);
   string signature=Hmac(method+"\n"+path+"\n"+stamp+"\n"+nonce+"\n"+body,g_key);
   if(!Hex(signature,64) || !Hex(nonce,64)) return false;
   string headers="Content-Type: application/json\r\nX-FX101-Time: "+stamp+"\r\nX-FX101-Nonce: "+nonce+"\r\nX-FX101-Signature: "+signature+"\r\n";
   uchar encoded[]; Bytes(body,encoded);
   char data[],result[]; ArrayCopy(data,encoded);
   string result_headers;
   ResetLastError();
   int code=WebRequest(method,InpApiBase+path,headers,3000,data,result,result_headers);
   int error=GetLastError();
   WritePrivate("Fx101Bridge\\transport.txt",StringFormat("http_status=%d last_error=%d utc=%I64d",code,error,(long)TimeGMT()));
   if(code!=200) { Print("FX101 transport unavailable code=",code," error=",error); return false; }
   if(ArraySize(result)>16384) return false;
   response=CharArrayToString(result,0,-1,CP_UTF8);
   return true;
  }
bool StrictNumber(string s,double &v)
  {
   int digits=0,dots=0;
   for(int i=0;i<StringLen(s);i++)
     {
      ushort c=StringGetCharacter(s,i);
      if(c=='.') dots++;
      else if(c>='0' && c<='9') digits++;
      else return false;
     }
   v=StringToDouble(s);
   return digits>0 && dots<=1 && MathIsValidNumber(v) && v>=0;
  }
bool ExistingRisk(double &total,string symbol,string side,string &reason)
  {
   total=0;
   for(int group=0;group<2;group++)
     {
      int count=group==0 ? PositionsTotal() : OrdersTotal();
      for(int i=0;i<count;i++)
        {
         ulong ticket=group==0 ? PositionGetTicket(i) : OrderGetTicket(i);
         if(ticket==0) { reason="exposure_selection_failed"; return false; }
         string sym=group==0 ? PositionGetString(POSITION_SYMBOL) : OrderGetString(ORDER_SYMBOL);
         string dir=group==0 ? (PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? "BUY" : "SELL") : (StringFind(OrderName(OrderGetInteger(ORDER_TYPE)),"BUY")==0 ? "BUY" : "SELL");
         if(sym==symbol) { reason=side==dir ? "duplicate_symbol" : "hedging_prohibited"; return false; }
         double sl=group==0 ? PositionGetDouble(POSITION_SL) : OrderGetDouble(ORDER_SL);
         double volume=group==0 ? PositionGetDouble(POSITION_VOLUME) : OrderGetDouble(ORDER_VOLUME_CURRENT);
         if(!FinitePositive(sl)) { reason="existing_exposure_without_sl"; return false; }
         MqlTick q; if(!SymbolInfoTick(sym,q)) { reason="exposure_quote_failed"; return false; }
         double entry=dir=="BUY" ? q.bid : q.ask;
         if(group==1)
           {
            entry=OrderGetDouble(ORDER_PRICE_OPEN);
            long type=OrderGetInteger(ORDER_TYPE);
            if(type==ORDER_TYPE_BUY_STOP_LIMIT || type==ORDER_TYPE_SELL_STOP_LIMIT) entry=OrderGetDouble(ORDER_PRICE_STOPLIMIT);
           }
         double profit=0;
         if(!OrderCalcProfit(dir=="BUY" ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,sym,volume,entry,sl,profit)) { reason="exposure_risk_failed"; return false; }
         total+=MathMax(0,-profit);
        }
     }
   return true;
  }
bool Plan(string &f[],double &volume,double &usd,string &reason)
  {
   volume=0; usd=0;
   if(!AccountBound() || !TerminalInfoInteger(TERMINAL_CONNECTED)) { reason="account_or_connection"; return false; }
   if(f[3]!=(string)InpExpectedLogin || f[4]!=InpExpectedServer || f[5]!="SHADOW") { reason="account_or_mode"; return false; }
   double created=0,expires=0,entry=0,sl=0,tp=0,pct=0,stoplimit=0,cancel=0;
   if(!StrictNumber(f[6],created) || !StrictNumber(f[7],expires) || !StrictNumber(f[10],entry) || !StrictNumber(f[11],sl) || !StrictNumber(f[12],tp) || !StrictNumber(f[13],pct) || !StrictNumber(f[14],stoplimit) || !StrictNumber(f[16],cancel)) { reason="invalid_number"; return false; }
   long now=(long)TimeGMT();
   if(created>now || now-created>30 || expires<=now || expires>created+30) { reason="stale_command"; return false; }
   if(f[17]!="0" && f[17]!="1") { reason="invalid_synthetic_flag"; return false; }
   // Only synthetic SHADOW planning can bypass unknown historical rule anchors.
   if(f[17]!="1") { reason="historical_anchors_unverified"; return false; }
   string symbol=f[8],type=f[9]; bool allowed=false;
   for(int i=0;i<ArraySize(g_symbols);i++) if(g_symbols[i]==symbol && StringSubstr(symbol,StringLen(symbol)-2)==".x") allowed=true;
   if(!allowed || !SymbolSelect(symbol,true)) { reason="symbol_unavailable"; return false; }
   int order=-1;
   for(int i=0;i<8;i++) if(OrderName(i)==type) order=i;
   if(order<0) { reason="order_type"; return false; }
   bool buy=StringFind(type,"BUY")==0; string side=buy ? "BUY" : "SELL";
   long trade_mode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);
   if(trade_mode!=SYMBOL_TRADE_MODE_FULL && !(trade_mode==SYMBOL_TRADE_MODE_LONGONLY && buy) && !(trade_mode==SYMBOL_TRADE_MODE_SHORTONLY && !buy)) { reason="trade_mode"; return false; }
   long bits=SymbolInfoInteger(symbol,SYMBOL_ORDER_MODE);
   long needed=order<2 ? 1 : order<4 ? 2 : order<6 ? 4 : 8;
   if((bits&needed)==0 || (bits&16)==0 || (bits&32)==0) { reason="broker_order_mode"; return false; }
   MqlTick quote; if(!SymbolInfoTick(symbol,quote)) { reason="quote_failed"; return false; }
   if(TimeTradeServer()-quote.time>10 || quote.time>TimeTradeServer()+1) { reason="stale_quote"; return false; }
   double tick=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE),tv=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE_LOSS);
   double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP),vmin=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN),vmax=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
   if(!FinitePositive(tick) || !FinitePositive(tv) || !FinitePositive(step) || !FinitePositive(vmin) || !FinitePositive(vmax) || !FinitePositive(SymbolInfoDouble(symbol,SYMBOL_TRADE_CONTRACT_SIZE))) { reason="contract_invalid"; return false; }
   if(quote.ask<quote.bid || (quote.ask-quote.bid)/tick>30) { reason="spread"; return false; }
   if(order<2)
     {
      double actual=buy ? quote.ask : quote.bid;
      if(MathAbs(actual-entry)/tick>5) { reason="entry_moved"; return false; }
      entry=actual;
     }
   if(!(buy ? sl<entry && entry<tp : tp<entry && entry<sl) || !FinitePositive(sl) || !FinitePositive(tp)) { reason="sltp_geometry"; return false; }
   double price_values[]={entry,sl,tp};
   for(int i=0;i<3;i++) if(MathAbs(price_values[i]/tick-MathRound(price_values[i]/tick))>1e-6) { reason="tick_alignment"; return false; }
   long levels=MathMax(SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL),SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL));
   double distance=(double)levels*SymbolInfoDouble(symbol,SYMBOL_POINT),ref=buy ? quote.bid : quote.ask;
   if(MathMin(MathMin(MathAbs(entry-sl),MathAbs(tp-entry)),MathMin(MathAbs(ref-sl),MathAbs(tp-ref)))<=distance) { reason="stop_freeze_level"; return false; }
   if(order>=2)
     {
      double market=buy ? quote.ask : quote.bid; bool limit=order==2 || order==3;
      bool geometry=limit ? (buy ? entry<market : entry>market) : (buy ? entry>market : entry<market);
      if(!geometry || MathAbs(entry-market)<=distance) { reason="pending_geometry"; return false; }
     }
   if(order>=6)
     {
      if(!(buy ? sl<stoplimit && stoplimit<=entry && entry<tp : tp<entry && entry<=stoplimit && stoplimit<sl) || MathAbs(stoplimit/tick-MathRound(stoplimit/tick))>1e-6) { reason="stop_limit_geometry"; return false; }
     }
   else if(stoplimit!=0) { reason="unexpected_stop_limit"; return false; }
   if(f[15]!="price_below" && f[15]!="price_above") { reason="unmeasurable_cancellation"; return false; }
   if(!FinitePositive(cancel) || (f[15]=="price_below" && quote.bid<=cancel) || (f[15]=="price_above" && quote.ask>=cancel)) { reason="cancel_condition_met"; return false; }
   if(pct<=0 || pct>0.25) { reason="per_trade_risk"; return false; }
   double balance=AccountInfoDouble(ACCOUNT_BALANCE),equity=AccountInfoDouble(ACCOUNT_EQUITY),floating=AccountInfoDouble(ACCOUNT_PROFIT);
   if(!FinitePositive(balance) || !FinitePositive(equity) || floating<=-balance*0.007) { reason="floating_loss"; return false; }
   double existing=0; if(!ExistingRisk(existing,symbol,side,reason)) return false;
   double budget=MathMin(MathMin(balance,equity)*pct/100,MathMin(balance,equity)*0.006-existing);
   budget=MathMin(budget,balance*0.007+floating);
   string peak_key=StringFormat("FX101.%I64d.peak",InpExpectedLogin);
   if(!GlobalVariableCheck(peak_key)) { reason="missing_peak"; return false; }
   budget=MathMin(budget,equity-GlobalVariableGet(peak_key)*0.955);
   if(budget<=0) { reason="aggregate_or_drawdown"; return false; }
   double profit=0,worst=entry+(buy ? 5*tick : -5*tick);
   ENUM_ORDER_TYPE market_type=buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(!OrderCalcProfit(market_type,symbol,vmin,worst,sl,profit) || profit>=0) { reason="risk_calculation"; return false; }
   double unit=MathMax(-profit/vmin,(MathAbs(entry-sl)/tick+5)*tv);
   volume=MathFloor(MathMin(vmax,budget/unit)/step)*step; // Always DOWN, without an upward epsilon.
   if(volume<vmin || volume<=0) { volume=0; reason="lot_minimum"; return false; }
   usd=unit*volume;
   if(usd>budget) { reason="risk_rounding"; return false; }
   double margin=0;
   if(!OrderCalcMargin(market_type,symbol,volume,entry,margin) || margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.8) { reason="margin"; return false; }
   reason="synthetic_shadow_only";
   return true;
  }
void Ack(string id,string body)
  {
   string response,nonce;
   if(Http("POST","/fx101/mt5/ack",body,response,nonce))
     {
      if(!WritePrivate("Fx101Bridge\\"+id+".sent","ACKED")) Print("FX101 ACK marker failed; retry remains safe");
      Print("FX101 ACK confirmed command=",id);
     }
  }
void DrainAcks()
  {
   string name;
   long handle=FileFindFirst("Fx101Bridge\\*.ack",name);
   if(handle==INVALID_HANDLE) return;
   int attempted=0;
   do
     {
      if(StringLen(name)!=36 || !Hex(StringSubstr(name,0,32),32)) continue;
      string id=StringSubstr(name,0,32);
      if(FileIsExist("Fx101Bridge\\"+id+".sent")) continue;
      string body=ReadPrivate("Fx101Bridge\\"+name);
      if(body=="") continue;
      Ack(id,body); attempted++;
      // Bound traffic; durable ACK retry is independent of command expiry.
      if(attempted>=2) break;
     }
   while(FileFindNext(handle,name));
   FileFindClose(handle);
  }
void Poll()
  {
   if(InpMode!=MODE_SHADOW || Killed() || !g_snapshot_ok) return;
   string response,nonce;
   if(!Http("GET","/fx101/mt5/command","",response,nonce) || response=="NONE") return;
   string f[]; int count=StringSplit(response,'|',f);
   if(count!=19 || f[0]!="FX101v2" || !Equal(f[1],nonce) || !Hex(f[2],32) || !Hex(f[18],64)) { Print("FX101 invalid command envelope"); return; }
   int split=StringLen(response)-65;
   if(!Equal(Hmac(StringSubstr(response,0,split),g_key),f[18])) { Print("FX101 invalid command signature"); return; }
   string journal="Fx101Bridge\\"+f[2]+".ack";
   if(FileIsExist(journal))
     {
      string existing=ReadPrivate(journal);
      if(existing!="") Ack(f[2],existing);
      else Print("FX101 corrupt journal; command blocked");
      return;
     }
   double volume=0,usd=0; string reason="";
   bool ok=Plan(f,volume,usd,reason);
   string body=StringFormat("{\"command_id\":\"%s\",\"login\":%I64d,\"server\":\"%s\",\"status\":\"%s\",\"volume\":%s,\"risk_usd\":%s,\"detail\":\"%s\"}",
                  f[2],InpExpectedLogin,Escape(InpExpectedServer),ok ? "SHADOW_OK" : "REJECTED",Num(volume),Num(usd),reason);
   // Persist and flush before ACK. Failed ACK is replayed from disk on next poll/restart.
   if(!WritePrivate(journal,body)) { Print("FX101 journal unavailable; blocked"); return; }
   Print("FX101 SHADOW command=",f[2]," status=",ok ? "SHADOW_OK" : "REJECTED"," volume=",Num(volume)," risk_usd=",Num(usd)," reason=",reason);
   Ack(f[2],body);
  }
int OnInit()
  {
   if(InpMode==MODE_AUTO) { Print("FX101 AUTO unavailable: critical paths unvalidated"); return INIT_PARAMETERS_INCORRECT; }
   if(InpExpectedLogin!=315307814 || InpExpectedServer!="GoatFunded-Server") return INIT_PARAMETERS_INCORRECT;
   if(StringFind(InpApiBase,"https://")!=0 || StringFind(InpApiBase,"\r")>=0 || StringFind(InpApiBase,"\n")>=0 || InpPollSeconds<5 || InpPollSeconds>10) return INIT_PARAMETERS_INCORRECT;
   if(Hmac("The quick brown fox jumps over the lazy dog","key")!="f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8") { Print("FX101 cryptographic selftest failed"); return INIT_FAILED; }
   FolderCreate("Fx101Bridge");
   g_key=ReadPrivate(InpCredentialFile);
   if(g_key!="" && !Hex(g_key,64)) return INIT_PARAMETERS_INCORRECT;
   string counter_path="Fx101Bridge\\boot.txt";
   double boot=StringToDouble(ReadPrivate(counter_path))+1;
   if(!WritePrivate(counter_path,DoubleToString(boot,0))) return INIT_FAILED;
   g_session=DoubleToString(boot,0)+":"+(string)(long)TimeGMT()+":"+(string)GetMicrosecondCount();
   string symbols="EURUSD.x,GBPUSD.x,GBPJPY.x,USDCAD.x,EURJPY.x,AUDUSD.x,NZDUSD.x,USDCHF.x,EURGBP.x,CADJPY.x,CHFJPY.x,EURAUD.x,GBPAUD.x,EURCAD.x,GBPCAD.x,XAUUSD.x,USDJPY.x,AUDJPY.x";
   StringSplit(symbols,',',g_symbols);
   for(int i=0;i<ArraySize(g_symbols);i++) SymbolSelect(g_symbols[i],true);
   if(!EventSetTimer(InpPollSeconds)) return INIT_FAILED;
   Print("FX101 v2 started SHADOW/OBSERVE only login=",InpExpectedLogin," server=",InpExpectedServer," markets=",ArraySize(g_symbols)," local_kill=",Killed());
   return INIT_SUCCEEDED;
  }
void OnDeinit(const int reason) { EventKillTimer(); }
void OnTimer()
  {
   if(InpMode==MODE_OFF || !AccountBound()) return;
   string body=Snapshot(); g_snapshot_ok=false;
   if(body=="") { Print("FX101 incomplete broker snapshot; commands blocked"); return; }
   if(!WritePrivate("Fx101Bridge\\snapshot.json",body)) return;
   string response,nonce;
   g_snapshot_ok=Http("POST","/fx101/mt5/snapshot",body,response,nonce);
   if(g_snapshot_ok && InpMode==MODE_SHADOW && !Killed()) DrainAcks();
   Poll();
  }
