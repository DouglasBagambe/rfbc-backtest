#ifndef DNB_STRATEGY_DEMO_MQH
#define DNB_STRATEGY_DEMO_MQH
bool DnbReadDemoStatus(string response,string nonce)
  {
   string f[];
   if(StringSplit(response,'|',f)!=11 || f[0]!="DNBdemoState1" || f[1]!=nonce || f[3]!="5057377621" ||
      f[4]!="MetaQuotes-Demo" || f[5]!="DEMO" || (f[6]!="0" && f[6]!="1") || !Hex(f[10],64))return false;
   if(!Equal(Hmac(StringSubstr(response,0,StringLen(response)-65),g_key),f[10]))return false;
   long stamp=StringToInteger(f[2]);
   if(stamp>(long)TimeGMT()+1 || (long)TimeGMT()-stamp>15)return false;
   g_demo_status_at=stamp;g_demo_server_killed=f[6]=="1";
   double peak=StringToDouble(f[8]);
   if(peak>0)
     {
      string key=StringFormat("FX101.%I64d.peak",InpExpectedLogin);
      double observed=GlobalVariableCheck(key) ? GlobalVariableGet(key) : 0;
      if(peak>observed) { GlobalVariableSet(key,peak);GlobalVariablesFlush(); }
     }
   return true;
  }
bool DnbStoreOwner(string id)
  {
   string data=id+"|"+(string)DnbMagic(id),body=data+"|"+Hmac(data,g_journal_key);
   string path=DnbBridgeDirectory()+"\\owner."+(string)DnbMagic(id)+".map";
   if(FileIsExist(path))return DnbRead(path)==body;
   return DnbWriteOnce(path,body);
  }
string DnbResolveOwner(ulong magic)
  {
   string f[];string body=DnbRead(DnbBridgeDirectory()+"\\owner."+(string)magic+".map");
   if(StringSplit(body,'|',f)!=3 || !Hex(f[0],32) || f[1]!=(string)magic || DnbMagic(f[0])!=magic ||
      !Equal(Hmac(f[0]+"|"+f[1],g_journal_key),f[2]))return "";
   return f[0];
  }
// Included only in the explicitly bound demo strategy build. No synthetic probe
// can enter this parser; recovery is allowed without a fresh submission lease.
bool DnbLoadDemoRequest(string path,string id,string thesis,MqlTradeRequest &r)
  {
   string f[];string text=DnbRead(path);
   if(StringSplit(text,'|',f)!=22 || f[0]!="DNB2" || f[1]!=id || f[2]!=(string)InpExpectedLogin ||
      f[3]!=InpExpectedServer || !Hex(f[4],64)) return false;
   ZeroMemory(r);
   r.action=(ENUM_TRADE_REQUEST_ACTIONS)StringToInteger(f[5]);r.symbol=f[6];r.type=(ENUM_ORDER_TYPE)StringToInteger(f[7]);
   r.order=(ulong)StringToInteger(f[8]);r.position=(ulong)StringToInteger(f[9]);r.volume=StringToDouble(f[10]);r.price=StringToDouble(f[11]);
   r.sl=StringToDouble(f[12]);r.tp=StringToDouble(f[13]);r.stoplimit=StringToDouble(f[14]);
   r.type_filling=(ENUM_ORDER_TYPE_FILLING)StringToInteger(f[15]);r.type_time=(ENUM_ORDER_TYPE_TIME)StringToInteger(f[16]);
   r.expiration=(datetime)StringToInteger(f[17]);r.magic=(ulong)StringToInteger(f[18]);r.comment=f[19];r.deviation=(ulong)StringToInteger(f[21]);
   return f[20]==thesis && r.magic==DnbMagic(id) && r.comment==DnbComment(id) && r.deviation==5 &&
      Equal(DnbSha(DnbCanonical(r,thesis)),f[4]);
  }
bool DnbStoreDemoRequest(string path,string id,string thesis,MqlTradeRequest &r)
  {
   r.magic=DnbMagic(id);r.comment=DnbComment(id);
   string canonical=DnbCanonical(r,thesis);
   string text="DNB2|"+id+"|"+(string)InpExpectedLogin+"|"+InpExpectedServer+"|"+DnbSha(canonical)+"|"+canonical;
   return DnbWriteOnce(path,text);
  }
void DnbDemoReceipt(string id,string status,ulong order,ulong deal,double volume,double usd,string detail)
  {
   string packet=StringFormat("{\"command_id\":\"%s\",\"login\":%I64d,\"server\":\"%s\",\"status\":\"%s\",\"order_ticket\":\"%I64u\",\"deal_ticket\":\"%I64u\",\"volume\":%s,\"risk_usd\":%s,\"detail\":\"%s\"}",
      id,InpExpectedLogin,Escape(InpExpectedServer),status,order,deal,Num(volume),Num(usd),detail);
   string path=DnbBridgeDirectory()+"\\"+id+".ack";
   if(ReadPrivate(path)!=packet) FileDelete(DnbBridgeDirectory()+"\\"+id+".sent");
   if(!WritePrivate(path,packet)) { Print("dnb demo receipt persistence failed; submission remains reserved");return; }
   Ack(id,packet);
  }
void DnbPollStrategyDemo()
  {
   if(InpMode!=MODE_AUTO || !g_snapshot_ok || Killed())return;
   string response,nonce;
   if(!Http("GET","/fx101/mt5/command","",response,nonce) || response=="NONE")return;
   string f[];int count=StringSplit(response,'|',f);
   if(count!=36 || f[0]!="DNBdemo1" || !Equal(f[1],nonce) || !Hex(f[2],32) || !Hex(f[35],64) ||
      f[3]!=(string)InpExpectedLogin || f[4]!=InpExpectedServer || f[5]!="DEMO" || f[17]!="0")return;
   if(f[26]!="G_DESK" && f[26]!="RFBC")return;
   if(!Equal(Hmac(StringSubstr(response,0,StringLen(response)-65),g_key),f[35]))return;
   string source_path=DnbBridgeDirectory()+"\\"+f[2]+".command";
   string local_data="DNBlocalsource1";
   for(int i=1;i<35;i++)local_data+="|"+f[i];
   string local_source=local_data+"|"+Hmac(local_data,g_journal_key);
   if(!FileIsExist(source_path) && !DnbWriteOnce(source_path,local_source))return;
   if(!DnbStoreOwner(f[2]))return;
   string request_path=DnbBridgeDirectory()+"\\"+f[2]+".request";
   string intent_path=DnbBridgeDirectory()+"\\"+f[2]+".intent";
   DnbNativeBroker broker;MqlTradeRequest r={};ulong order=0,deal=0;uint code=0;
   g_demo_send_deadline=0;g_demo_request_volume=0;
   // A committed remote intent means broker I/O may already have happened,
   // including when the local disk is missing. Search only: never resubmit.
   if(f[24]!="QUEUED" || FileIsExist(intent_path))
     {
      int found=broker.Search(DnbMagic(f[2]),DnbComment(f[2]),DnbBrokerSymbol(f[8]),order,deal);
      double volume=0,risk_usd=0;
      if(DnbLoadDemoRequest(request_path,f[2],f[18],r)) volume=r.volume;
      StrictNumber(f[25],risk_usd);
      DnbDemoReceipt(f[2],found==1 ? "RECOVERED" : "UNRESOLVED",order,deal,volume,risk_usd,
         found==1 ? "broker_identity_recovered" : "broker_identity_unresolved");
      return;
     }
   double volume=0,usd=0;string reason="";
   if(!Plan(f,volume,usd,reason)) { DnbDemoReceipt(f[2],"REJECTED",0,0,0,0,reason);return; }
   if(FileIsExist(request_path))
     {
      if(!DnbLoadDemoRequest(request_path,f[2],f[18],r))
        { DnbDemoReceipt(f[2],"UNRESOLVED",0,0,0,0,"request_journal_corrupt");return; }
      if(r.volume>volume || r.sl!=StringToDouble(f[11]) || r.tp!=StringToDouble(f[12]) || r.symbol!=DnbBrokerSymbol(f[8]) || OrderName(r.type)!=f[9])
        { DnbDemoReceipt(f[2],"REJECTED",0,0,0,0,"request_revalidation_failed");return; }
     }
   else
     {
      int type=-1;for(int i=0;i<8;i++)if(OrderName(i)==f[9])type=i;
      if(type<0)return;
      double entry=StringToDouble(f[10]);
      if(type<2) { MqlTick q;if(!DnbSymbolTick(f[8],q))return;entry=type==0 ? q.ask : q.bid; }
      datetime expiry=type<2 ? 0 : (datetime)(StringToInteger(f[19])+(long)TimeTradeServer()-(long)TimeGMT());
      if(!DnbPlacement(DnbBrokerSymbol(f[8]),(ENUM_ORDER_TYPE)type,volume,entry,StringToDouble(f[11]),StringToDouble(f[12]),StringToDouble(f[14]),expiry,r))
        { DnbDemoReceipt(f[2],"REJECTED",0,0,0,0,"request_construction_failed");return; }
      if(!DnbStoreDemoRequest(request_path,f[2],f[18],r))return;
     }
   usd=usd*r.volume/volume;
   string canonical=DnbCanonical(r,f[18]);
   string body=StringFormat("{\"command_id\":\"%s\",\"login\":%I64d,\"server\":\"%s\",\"fingerprint\":\"%s\",\"symbol\":\"%s\",\"order_type\":\"%s\",\"volume\":%s,\"entry\":%s,\"sl\":%s,\"tp\":%s}",
      f[2],InpExpectedLogin,Escape(InpExpectedServer),DnbSha(canonical),f[8],f[9],Num(r.volume),Num(r.price),Num(r.sl),Num(r.tp));
   if(!Http("POST","/fx101/mt5/demo/strategy-intent",body,response,nonce))return;
   if(!DnbReserveNativeThesis(f)) { Print("dnb native thesis reservation unavailable; broker submission blocked");return; }
   // Remote intent is committed; local write-ahead intent precedes OrderSend.
   ArrayCopy(g_demo_fields,f);g_demo_send_deadline=StringToInteger(f[7]);g_demo_request_volume=r.volume;
   string result=DnbSubmitOnce(broker,DnbBridgeDirectory(),f[2],f[18],r,order,deal,code);
   g_demo_send_deadline=0;
   string state="UNRESOLVED",detail="submission_unresolved";
   if(result=="ACCEPTED" || result=="PLACED" || result=="PARTIAL" || result=="RECOVERED") { state=result;detail="broker_receipt_recorded"; }
   else if(result=="CHECK_REJECTED" || result=="BROKER_REJECTED") { state="REJECTED";detail="broker_rejected"; }
   DnbDemoReceipt(f[2],state,order,deal,r.volume,usd,detail);
   g_history_dirty=true;
  }
#endif
