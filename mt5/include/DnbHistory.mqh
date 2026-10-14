#ifndef DNB_HISTORY_MQH
#define DNB_HISTORY_MQH
// Freeze each capture before paging. A partial capture never establishes completeness.
string g_history_orders[],g_history_deals[];
string g_history_capture="";
long g_history_at=0,g_history_to=0;
int g_history_kind=0,g_history_page=0;
bool g_history_dirty=true;
string DnbOrderHistoryJson(ulong t)
  {
   string s=StringFormat("{\"ticket\":\"%I64u\",\"position_id\":\"%I64d\",\"magic\":%I64d,",t,HistoryOrderGetInteger(t,ORDER_POSITION_ID),HistoryOrderGetInteger(t,ORDER_MAGIC));
   s+="\"comment\":\""+Escape(HistoryOrderGetString(t,ORDER_COMMENT))+"\",\"symbol\":\""+Escape(HistoryOrderGetString(t,ORDER_SYMBOL))+"\",";
   s+=StringFormat("\"type\":%I64d,\"state\":%I64d,\"reason\":%I64d,",HistoryOrderGetInteger(t,ORDER_TYPE),HistoryOrderGetInteger(t,ORDER_STATE),HistoryOrderGetInteger(t,ORDER_REASON));
   s+="\"volume_initial\":"+Num(HistoryOrderGetDouble(t,ORDER_VOLUME_INITIAL))+",\"volume_current\":"+Num(HistoryOrderGetDouble(t,ORDER_VOLUME_CURRENT));
   s+=",\"price\":"+Num(HistoryOrderGetDouble(t,ORDER_PRICE_OPEN))+",\"sl\":"+Num(HistoryOrderGetDouble(t,ORDER_SL))+",\"tp\":"+Num(HistoryOrderGetDouble(t,ORDER_TP));
   s+=",\"stop_limit\":"+Num(HistoryOrderGetDouble(t,ORDER_PRICE_STOPLIMIT));
   s+=StringFormat(",\"created_at\":%I64d,\"done_at\":%I64d,\"expires_at\":%I64d}",HistoryOrderGetInteger(t,ORDER_TIME_SETUP),HistoryOrderGetInteger(t,ORDER_TIME_DONE),HistoryOrderGetInteger(t,ORDER_TIME_EXPIRATION));
   return s;
  }
string DnbDealHistoryJson(ulong t)
  {
   string s=StringFormat("{\"ticket\":\"%I64u\",\"order_ticket\":\"%I64d\",\"position_id\":\"%I64d\",\"magic\":%I64d,",t,HistoryDealGetInteger(t,DEAL_ORDER),HistoryDealGetInteger(t,DEAL_POSITION_ID),HistoryDealGetInteger(t,DEAL_MAGIC));
   s+="\"comment\":\""+Escape(HistoryDealGetString(t,DEAL_COMMENT))+"\",\"symbol\":\""+Escape(HistoryDealGetString(t,DEAL_SYMBOL))+"\",";
   s+=StringFormat("\"type\":%I64d,\"entry\":%I64d,\"reason\":%I64d,",HistoryDealGetInteger(t,DEAL_TYPE),HistoryDealGetInteger(t,DEAL_ENTRY),HistoryDealGetInteger(t,DEAL_REASON));
   s+="\"volume\":"+Num(HistoryDealGetDouble(t,DEAL_VOLUME))+",\"price\":"+Num(HistoryDealGetDouble(t,DEAL_PRICE));
   s+=",\"profit\":"+Num(HistoryDealGetDouble(t,DEAL_PROFIT))+",\"commission\":"+Num(HistoryDealGetDouble(t,DEAL_COMMISSION));
   s+=",\"swap\":"+Num(HistoryDealGetDouble(t,DEAL_SWAP))+",\"fee\":"+Num(HistoryDealGetDouble(t,DEAL_FEE));
   s+=StringFormat(",\"time\":%I64d}",HistoryDealGetInteger(t,DEAL_TIME));return s;
  }
bool DnbBeginHistory()
  {
   g_history_to=(long)TimeTradeServer();
   if(!HistorySelect(0,(datetime)g_history_to)) return false;
   int orders=HistoryOrdersTotal(),deals=HistoryDealsTotal();
   if(orders>100000 || deals>100000) return false;
   ArrayResize(g_history_orders,orders);ArrayResize(g_history_deals,deals);
   for(int i=0;i<orders;i++) { ulong t=HistoryOrderGetTicket(i);if(t==0)return false;g_history_orders[i]=DnbOrderHistoryJson(t); }
   for(int i=0;i<deals;i++) { ulong t=HistoryDealGetTicket(i);if(t==0)return false;g_history_deals[i]=DnbDealHistoryJson(t); }
   g_history_at=(long)TimeGMT();g_counter++;
   g_history_capture=StringSubstr(Hmac(g_session+":history:"+(string)g_counter,g_key),0,32);
   g_history_kind=0;g_history_page=0;g_history_dirty=false;
   return Hex(g_history_capture,32);
  }
void DnbPumpHistory()
  {
   if(g_history_capture=="")
     {
      if(!g_history_dirty && (long)TimeGMT()-g_history_at<30) return;
      if(!DnbBeginHistory()) return;
     }
   int total=g_history_kind==0 ? ArraySize(g_history_orders) : ArraySize(g_history_deals);
   int pages=MathMax(1,(total+99)/100),start=g_history_page*100,end=MathMin(total,start+100);
   string body=StringFormat("{\"capture_id\":\"%s\",\"login\":%I64d,\"server\":\"%s\",\"captured_at\":%I64d,\"from_server_time\":0,\"to_server_time\":%I64d,\"kind\":\"%s\",\"page\":%d,\"pages\":%d,\"total\":%d,\"items\":[",
     g_history_capture,InpExpectedLogin,Escape(InpExpectedServer),g_history_at,g_history_to,g_history_kind==0 ? "orders" : "deals",g_history_page,pages,total);
   for(int i=start;i<end;i++) { if(i>start)body+=",";body+=g_history_kind==0 ? g_history_orders[i] : g_history_deals[i]; }
   body+="]}";string response,nonce;
   if(!Http("POST","/fx101/mt5/history",body,response,nonce)) return;
   g_history_page++;
   if(g_history_page>=pages) { g_history_page=0;g_history_kind++; }
   if(g_history_kind>=2)
     {
      WritePrivate(DnbBridgeDirectory()+"\\history-capture.txt",g_history_capture+"|"+(string)g_history_at+"|"+(string)ArraySize(g_history_orders)+"|"+(string)ArraySize(g_history_deals));
      g_history_capture="";
     }
  }
#endif
