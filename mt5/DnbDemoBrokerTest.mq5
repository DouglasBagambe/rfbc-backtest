#property strict
#property version "1.00"
#property description "dnb isolated MetaQuotes-Demo broker validation. GOAT is forbidden."
#include "include/DnbBroker.mqh"
input bool InpRunDemo=false;
const long DEMO_LOGIN=5057377621;
const string DEMO_SERVER="MetaQuotes-Demo";
bool DnbBrokerIoAuthorised()
  {
   return InpRunDemo && AccountInfoInteger(ACCOUNT_LOGIN)==DEMO_LOGIN && AccountInfoString(ACCOUNT_SERVER)==DEMO_SERVER &&
      AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO && TerminalInfoInteger(TERMINAL_CONNECTED) &&
      TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED);
  }
string JsonNum(double v) { return DoubleToString(v,10); }
void Record(string text)
  {
   int h=FileOpen("DnbDemoTests\\evidence.jsonl",FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(h==INVALID_HANDLE)return;FileSeek(h,0,SEEK_END);FileWriteString(h,text+"\n");FileFlush(h);FileClose(h);
   Print(text);
  }
class LostResponseBroker : public DnbNativeBroker
  {
public:
   int sends;
   LostResponseBroker() { sends=0; }
   virtual bool Send(MqlTradeRequest &r,MqlTradeResult &result)
     {
      sends++;bool accepted=DnbNativeBroker::Send(r,result);
      if(accepted && (result.retcode==TRADE_RETCODE_DONE || result.retcode==TRADE_RETCODE_PLACED || result.retcode==TRADE_RETCODE_DONE_PARTIAL))
        { ZeroMemory(result);result.retcode=TRADE_RETCODE_TIMEOUT;return false; }
      return accepted;
     }
  };
bool done=false;
int OnInit()
  {
   FolderCreate("DnbDemoTests");
   Record(StringFormat("{\"event\":\"binding\",\"login\":%I64d,\"server\":\"%s\",\"balance\":%.2f,\"currency\":\"%s\",\"trade_mode\":%I64d,\"terminal_algo\":%d,\"ea_algo\":%d,\"run_enabled\":%d}",
      AccountInfoInteger(ACCOUNT_LOGIN),AccountInfoString(ACCOUNT_SERVER),AccountInfoDouble(ACCOUNT_BALANCE),AccountInfoString(ACCOUNT_CURRENCY),AccountInfoInteger(ACCOUNT_TRADE_MODE),
      TerminalInfoInteger(TERMINAL_TRADE_ALLOWED),MQLInfoInteger(MQL_TRADE_ALLOWED),InpRunDemo));
   if(AccountInfoInteger(ACCOUNT_LOGIN)!=DEMO_LOGIN || AccountInfoString(ACCOUNT_SERVER)!=DEMO_SERVER) return INIT_FAILED;
   EventSetTimer(5);return INIT_SUCCEEDED;
  }
void OnDeinit(const int reason) { EventKillTimer(); }
void OnTick() {}

void RecoverAndCloseSynthetic()
  {
   string fields[];string text=DnbRead("DnbDemoTests\\restart.case");
   if(StringSplit(text,'|',fields)!=17) { Record("{\"event\":\"restart_error\",\"detail\":\"case_corrupt\"}");return; }
   MqlTradeRequest r={};
   r.action=(ENUM_TRADE_REQUEST_ACTIONS)StringToInteger(fields[1]);r.symbol=fields[2];r.type=(ENUM_ORDER_TYPE)StringToInteger(fields[3]);
   r.order=(ulong)StringToInteger(fields[4]);r.position=(ulong)StringToInteger(fields[5]);r.volume=StringToDouble(fields[6]);r.price=StringToDouble(fields[7]);
   r.sl=StringToDouble(fields[8]);r.tp=StringToDouble(fields[9]);r.stoplimit=StringToDouble(fields[10]);r.type_filling=(ENUM_ORDER_TYPE_FILLING)StringToInteger(fields[11]);
   r.type_time=(ENUM_ORDER_TYPE_TIME)StringToInteger(fields[12]);r.expiration=(datetime)StringToInteger(fields[13]);
   r.magic=(ulong)StringToInteger(fields[14]);r.comment=fields[15];r.deviation=5;
   DnbNativeBroker broker;ulong order=0,deal=0;uint code=0;
   string status=DnbSubmitOnce(broker,"DnbDemoTests",fields[0],fields[16],r,order,deal,code);
   Record(StringFormat("{\"event\":\"terminal_restart_recovery\",\"id\":\"%s\",\"status\":\"%s\",\"order\":\"%I64u\",\"deal\":\"%I64u\",\"entry_resubmitted\":false}",fields[0],status,order,deal));
   if(status!="RECOVERED")return;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong t=PositionGetTicket(i);
      if((ulong)PositionGetInteger(POSITION_MAGIC)!=r.magic || PositionGetString(POSITION_SYMBOL)!=r.symbol)continue;
      MqlTradeRequest close={};double volume=PositionGetDouble(POSITION_VOLUME),sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
      if(!DnbManagement(TRADE_ACTION_DEAL,t,r.magic,volume,sl,tp,volume,0,0,0,0,0,close))return;
      string cid=StringSubstr(DnbSha(fields[0]+":close-synthetic"),0,32);
      string closed=DnbSubmitOnce(broker,"DnbDemoTests",cid,"DEMO-CLEANUP",close,order,deal,code);
      Record(StringFormat("{\"event\":\"synthetic_cleanup\",\"status\":\"%s\",\"retcode\":%u,\"order\":\"%I64u\",\"deal\":\"%I64u\",\"volume\":%.4f}",closed,code,order,deal,volume));
     }
  }

void OnTimer()
  {
   if(done || !DnbBrokerIoAuthorised())return;
   done=true;
   if(FileIsExist("DnbDemoTests\\restart.case")) { RecoverAndCloseSynthetic();return; }
   DnbNativeBroker broker;LostResponseBroker lost;
   string symbol="EURUSD";
   if(!SymbolSelect(symbol,true)) { Record("{\"event\":\"error\",\"detail\":\"symbol_unavailable\"}");return; }
   MqlTick q;if(!SymbolInfoTick(symbol,q))return;
   double tick=SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE),step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP),volume=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
   double d=MathCeil(MathMax(200*tick,3*SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL)*SymbolInfoDouble(symbol,SYMBOL_POINT))/tick)*tick;
   double loss=0;if(!OrderCalcProfit(ORDER_TYPE_BUY,symbol,volume,q.ask,q.ask-d,loss) || -loss>MathMin(AccountInfoDouble(ACCOUNT_BALANCE),AccountInfoDouble(ACCOUNT_EQUITY))*.0025) { Record("{\"event\":\"error\",\"detail\":\"test_risk_exceeds_cap\"}");return; }
   string run=(string)(long)TimeGMT()+":"+(string)GetMicrosecondCount();
   // One market entry intentionally loses its returned acceptance response.
   MqlTradeRequest r={};ulong order=0,deal=0;uint code=0;
   if(!DnbPlacement(symbol,ORDER_TYPE_BUY,volume,q.ask,q.ask-d,q.ask+2*d,0,0,r))return;
   string id=StringSubstr(DnbSha(run+"lost"),0,32);
   string status=DnbSubmitOnce(lost,"DnbDemoTests",id,"DEMO-THESIS",r,order,deal,code);
   Record(StringFormat("{\"event\":\"lost_response\",\"id\":\"%s\",\"status\":\"%s\",\"retcode\":%u,\"send_calls\":%d,\"volume\":%.4f,\"risk_usd\":%.2f}",id,status,code,lost.sends,volume,-loss));
   // The complete immutable request is already on disk before real OrderSend.
   // Restart phase reads this checkpoint and calls recovery only.
   DnbWriteOnce("DnbDemoTests\\restart.case",id+"|"+DnbCanonical(r,"DEMO-THESIS"));
   status=DnbSubmitOnce(broker,"DnbDemoTests",id,"DEMO-THESIS",r,order,deal,code);
   Record(StringFormat("{\"event\":\"identity_recovery\",\"id\":\"%s\",\"status\":\"%s\",\"order\":\"%I64u\",\"deal\":\"%I64u\",\"resubmitted\":false}",id,status,order,deal));
   // Leave only this bounded, stopped position for the explicit restart test.
   // Later phases manage/close it; no other positions are touched.
  }
