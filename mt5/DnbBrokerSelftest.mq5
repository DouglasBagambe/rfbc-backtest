#property strict
#property version "1.00"
#property description "dnb native simulated broker tests. Never submits broker orders."
#include "include/DnbBroker.mqh"
bool DnbBrokerIoAuthorised() { return false; }
class FakeBroker : public DnbBrokerPort
  {
public:
   int sends;
   int scenario;
   ulong accepted_magic;
   string accepted_comment;
   string accepted_symbol;
   FakeBroker() { sends=0;scenario=0;accepted_magic=0; }
   virtual bool Check(MqlTradeRequest &r,MqlTradeCheckResult &c)
     { c.retcode=scenario==4 ? TRADE_RETCODE_INVALID_STOPS : TRADE_RETCODE_DONE;return scenario!=4; }
   virtual bool Send(MqlTradeRequest &r,MqlTradeResult &c)
     {
      sends++;accepted_magic=r.magic;accepted_comment=r.comment;accepted_symbol=r.symbol;
      if(scenario==3) { accepted_magic=0;c.retcode=TRADE_RETCODE_REJECT;return true; }
      c.order=701;c.deal=r.action==TRADE_ACTION_DEAL ? 801 : 0;c.volume=r.volume;
      c.retcode=scenario==1 ? TRADE_RETCODE_TIMEOUT : scenario==2 ? TRADE_RETCODE_DONE_PARTIAL :
                r.action==TRADE_ACTION_PENDING ? TRADE_RETCODE_PLACED : TRADE_RETCODE_DONE;
      string body=(string)accepted_magic+"|"+accepted_comment+"|"+accepted_symbol;
      DnbWriteOnce("Fx101Bridge\\NativeTests\\broker-"+(string)accepted_magic+".state",body);
      return scenario!=1;
     }
   virtual int Search(ulong magic,string comment,string symbol,ulong &order,ulong &deal)
     {
      string body=DnbRead("Fx101Bridge\\NativeTests\\broker-"+(string)magic+".state");
      if(body=="") return 0;
      if(body!=(string)magic+"|"+comment+"|"+symbol) return -1;
      order=701;deal=801;return 1;
     }
  };
int tests=0,failures=0;
void Expect(bool pass,string name)
  {
   tests++;if(!pass) { failures++;Print("DNB TEST FAILED ",name); }
  }
string CaseId(string run,string name) { return StringSubstr(DnbSha(run+name),0,32); }
int OnInit()
  {
   FolderCreate("Fx101Bridge");FolderCreate("Fx101Bridge\\NativeTests");
   string run=(string)(long)TimeGMT()+":"+(string)GetMicrosecondCount();
   ulong order=0,deal=0;uint code=0;FakeBroker broker;
   for(int type=0;type<8;type++)
     {
      MqlTradeRequest r={};r.symbol="EURUSD.x";r.type=(ENUM_ORDER_TYPE)type;r.action=type<2 ? TRADE_ACTION_DEAL : TRADE_ACTION_PENDING;
      r.volume=.01;r.price=1.1;r.sl=type%2==0 ? 1.09 : 1.11;r.tp=type%2==0 ? 1.12 : 1.08;
      string id=CaseId(run,"type"+(string)type);
      string status=DnbSubmitOnce(broker,"Fx101Bridge\\NativeTests",id,"THESIS",r,order,deal,code);
      Expect(status==(type<2 ? "ACCEPTED" : "PLACED"),"order type "+(string)type);
      int before=broker.sends;
      Expect(DnbSubmitOnce(broker,"Fx101Bridge\\NativeTests",id,"THESIS",r,order,deal,code)=="RECOVERED" && broker.sends==before,"duplicate type "+(string)type);
     }
   MqlTradeRequest r={};r.action=TRADE_ACTION_DEAL;r.symbol="XAUUSD.x";r.volume=.01;r.price=2000;r.sl=1990;r.tp=2020;
   string lost=CaseId(run,"accepted-lost-response");broker.scenario=1;
   Expect(DnbSubmitOnce(broker,"Fx101Bridge\\NativeTests",lost,"GOLD",r,order,deal,code)=="UNRESOLVED","accepted then timeout");
   FakeBroker restarted;
   Expect(DnbSubmitOnce(restarted,"Fx101Bridge\\NativeTests",lost,"GOLD",r,order,deal,code)=="RECOVERED" && restarted.sends==0,"restart broker identity recovery no duplicate");
   r.volume=.02;
   Expect(DnbSubmitOnce(restarted,"Fx101Bridge\\NativeTests",lost,"GOLD",r,order,deal,code)=="CORRUPT_OR_CONFLICT" && restarted.sends==0,"conflicting duplicate");
   r.volume=.01;broker.scenario=2;
   Expect(DnbSubmitOnce(broker,"Fx101Bridge\\NativeTests",CaseId(run,"partial"),"GOLD",r,order,deal,code)=="PARTIAL","partial fill");
   broker.scenario=3;string rejected=CaseId(run,"rejected");
   Expect(DnbSubmitOnce(broker,"Fx101Bridge\\NativeTests",rejected,"GOLD",r,order,deal,code)=="BROKER_REJECTED","broker rejection");
   int before=broker.sends;
   Expect(DnbSubmitOnce(broker,"Fx101Bridge\\NativeTests",rejected,"GOLD",r,order,deal,code)=="UNRESOLVED" && broker.sends==before,"rejected command never resubmitted");
   broker.scenario=4;
   Expect(DnbSubmitOnce(broker,"Fx101Bridge\\NativeTests",CaseId(run,"check-rejected"),"GOLD",r,order,deal,code)=="CHECK_REJECTED","native check rejection");
   broker.scenario=0;
   ENUM_TRADE_REQUEST_ACTIONS actions[]={TRADE_ACTION_SLTP,TRADE_ACTION_MODIFY,TRADE_ACTION_REMOVE,TRADE_ACTION_DEAL};
   for(int i=0;i<4;i++)
     {
      r.action=actions[i];r.order=100;r.position=200;
      string id=CaseId(run,"management"+(string)i);
      Expect(DnbSubmitOnce(broker,"Fx101Bridge\\NativeTests",id,"GOLD",r,order,deal,code)=="ACCEPTED","management "+(string)i);
      before=broker.sends;DnbSubmitOnce(broker,"Fx101Bridge\\NativeTests",id,"GOLD",r,order,deal,code);
      Expect(broker.sends==before,"management duplicate "+(string)i);
     }
   string output=StringFormat("{\"native_tests\":%d,\"failures\":%d,\"mocked_broker\":true,\"real_broker_orders\":0,\"lost_response_restart_no_duplicate\":%s}",tests,failures,failures==0 ? "true" : "false");
   DnbWriteOnce("Fx101Bridge\\NativeTests\\result-"+CaseId(run,"result")+".json",output);
   int h=FileOpen("Fx101Bridge\\native-broker-selftest.json",FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(h!=INVALID_HANDLE) { FileWriteString(h,output);FileFlush(h);FileClose(h); }
   Print(output);return failures==0 ? INIT_SUCCEEDED : INIT_FAILED;
  }
void OnTick() {}
