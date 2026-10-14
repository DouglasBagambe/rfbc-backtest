#ifndef DNB_DEMO_MANAGEMENT_MQH
#define DNB_DEMO_MANAGEMENT_MQH
// Protective operations are confined to this demo account and broker-confirmed
// ownership. They never create a position, widen a stop, or touch manual orders.
bool DnbLoadSignedDemoSource(string path,string id,string &f[])
  {
   string text=DnbRead(path);
   if(StringSplit(text,'|',f)!=36 || f[0]!="DNBlocalsource1" || f[2]!=id || f[3]!="5057377621" ||
      f[4]!="MetaQuotes-Demo" || f[5]!="DEMO" || f[17]!="0" || !Hex(f[35],64))return false;
   if(f[26]!="G_DESK" && f[26]!="RFBC")return false;
   return Equal(Hmac(StringSubstr(text,0,StringLen(text)-65),g_journal_key),f[35]);
  }
bool DnbDemoManagementAccount()
  {
   return InpMode==MODE_AUTO && AccountInfoInteger(ACCOUNT_LOGIN)==5057377621 &&
      AccountInfoString(ACCOUNT_SERVER)=="MetaQuotes-Demo" && AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
      AccountInfoString(ACCOUNT_CURRENCY)=="USD" && TerminalInfoInteger(TERMINAL_CONNECTED) &&
      TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED);
  }
bool DnbDemoUnmixedPosition(ulong position_id,ulong owner_magic)
  {
   if(!HistorySelect(0,TimeTradeServer()))return false;
   bool found=false;
   for(int i=0;i<HistoryDealsTotal();i++)
     {
      ulong d=HistoryDealGetTicket(i);if(d==0)return false;
      if((ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID)!=position_id)continue;
      long entry=HistoryDealGetInteger(d,DEAL_ENTRY);
      if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
        {
         // Independent netting additions cannot be guessed into this thesis.
         if((ulong)HistoryDealGetInteger(d,DEAL_MAGIC)!=owner_magic || entry==DEAL_ENTRY_INOUT)return false;
         found=true;
        }
     }
   return found;
  }
class DnbDemoProtectiveBroker : public DnbNativeBroker
  {
private:
   ulong m_ticket,m_owner;
   double m_volume,m_sl,m_tp;
   ENUM_TRADE_REQUEST_ACTIONS m_action;
public:
   void Configure(ENUM_TRADE_REQUEST_ACTIONS action,ulong ticket,ulong owner,double volume,double sl,double tp)
     { m_action=action;m_ticket=ticket;m_owner=owner;m_volume=volume;m_sl=sl;m_tp=tp; }
   virtual bool Send(MqlTradeRequest &r,MqlTradeResult &result)
     {
      if(!DnbDemoManagementAccount() || r.action!=m_action)return false;
      if(m_action==TRADE_ACTION_REMOVE)
        {
         if(r.order!=m_ticket || !OrderSelect(m_ticket) || (ulong)OrderGetInteger(ORDER_MAGIC)!=m_owner ||
            OrderGetDouble(ORDER_VOLUME_CURRENT)!=m_volume || OrderGetDouble(ORDER_SL)!=m_sl || OrderGetDouble(ORDER_TP)!=m_tp ||
            r.symbol!=OrderGetString(ORDER_SYMBOL))return false;
        }
      else if(m_action==TRADE_ACTION_DEAL)
        {
         if(r.position!=m_ticket || !PositionSelectByTicket(m_ticket) || (ulong)PositionGetInteger(POSITION_MAGIC)!=m_owner ||
            PositionGetDouble(POSITION_VOLUME)!=m_volume || PositionGetDouble(POSITION_SL)!=m_sl || PositionGetDouble(POSITION_TP)!=m_tp ||
            r.symbol!=PositionGetString(POSITION_SYMBOL) || r.volume<=0 || r.volume>m_volume)return false;
         bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
         if(r.type!=(buy ? ORDER_TYPE_SELL : ORDER_TYPE_BUY) ||
            !DnbDemoUnmixedPosition((ulong)PositionGetInteger(POSITION_IDENTIFIER),m_owner))return false;
        }
      else return false; // Modification requires a separately authenticated fresh strategy event.
      return OrderSend(r,result);
     }
  };
void DnbProtectDemoSource(string id,string &f[])
  {
   ulong magic=DnbMagic(id);string symbol=DnbBrokerSymbol(f[8]);
   double cancel=StringToDouble(f[16]);MqlTick q;
   if(!SymbolInfoTick(symbol,q) || TimeTradeServer()-q.time>10 || q.time>TimeTradeServer()+1)return;
   bool invalid=(f[15]=="price_below" && q.bid<=cancel) || (f[15]=="price_above" && q.ask>=cancel);
   bool expired=(long)TimeGMT()>=StringToInteger(f[19]);
   DnbDemoProtectiveBroker port;
   for(int i=OrdersTotal()-1;i>=0;i--)
     {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0 || (ulong)OrderGetInteger(ORDER_MAGIC)!=magic || OrderGetString(ORDER_SYMBOL)!=symbol || OrderGetString(ORDER_COMMENT)!=DnbComment(id))continue;
      if(!Killed() && !invalid && !expired)continue;
      double volume=OrderGetDouble(ORDER_VOLUME_CURRENT),sl=OrderGetDouble(ORDER_SL),tp=OrderGetDouble(ORDER_TP);
      MqlTradeRequest r={};
      if(!DnbManagement(TRADE_ACTION_REMOVE,ticket,magic,volume,sl,tp,0,0,0,0,0,0,r))continue;
      string operation=StringSubstr(DnbSha(id+":protective_cancel:"+(string)ticket),0,32);
      port.Configure(TRADE_ACTION_REMOVE,ticket,magic,volume,sl,tp);
      ulong order=0,deal=0;uint code=0;
      string state=DnbSubmitOnce(port,DnbBridgeDirectory(),operation,f[18],r,order,deal,code);
      Print("dnb owned pending protection command=",operation," status=",state," retcode=",code);
      g_history_dirty=true;
     }
   double balance=AccountInfoDouble(ACCOUNT_BALANCE),equity=AccountInfoDouble(ACCOUNT_EQUITY);
   string peak_key=StringFormat("FX101.%I64d.peak",InpExpectedLogin);
   if(!GlobalVariableCheck(peak_key))return;
   double floor=MathMin(2500.0,GlobalVariableGet(peak_key)-125.0)+12.5;
   bool breached=AccountInfoDouble(ACCOUNT_PROFIT)<=-balance*.007 || MathMin(balance,equity)<=floor;
   if((long)TimeGMT()<StringToInteger(f[23]) && equity<=StringToDouble(f[21])*.975)breached=true;
   MqlDateTime utc;TimeToStruct(TimeGMT(),utc);
   long day_start=(long)TimeGMT()-utc.hour*3600-utc.min*60-utc.sec;
   long friday=day_start-((utc.day_of_week+2)%7)*86400+16*3600;
   if((long)TimeGMT()<friday)friday-=7*86400;
   bool friday_close=f[26]=="RFBC" && StringToInteger(f[6])<friday;
   if(!breached && !friday_close)return;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || (ulong)PositionGetInteger(POSITION_MAGIC)!=magic || PositionGetString(POSITION_SYMBOL)!=symbol)continue;
      double volume=PositionGetDouble(POSITION_VOLUME),sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
      ulong pid=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
      // Ordinary strategy exits respect the minimum holding time. Emergency
      // downside protection never waits merely to preserve profit eligibility.
      if(!breached && (long)TimeTradeServer()-PositionGetInteger(POSITION_TIME)<60)continue;
      if(!DnbDemoUnmixedPosition(pid,magic))continue;
      MqlTradeRequest r={};
      if(!DnbManagement(TRADE_ACTION_DEAL,ticket,magic,volume,sl,tp,volume,0,0,0,0,0,r))continue;
      string operation=StringSubstr(DnbSha(id+(breached ? ":risk_guard:" : ":rfbc_friday_close:")+(string)ticket+":"+Num(volume)),0,32);
      port.Configure(TRADE_ACTION_DEAL,ticket,magic,volume,sl,tp);
      ulong order=0,deal=0;uint code=0;
      string state=DnbSubmitOnce(port,DnbBridgeDirectory(),operation,f[18],r,order,deal,code);
      Print("dnb owned position risk guard command=",operation," status=",state," retcode=",code);
      g_history_dirty=true;
     }
  }
void DnbManageStrategyDemo()
  {
   if(!DnbDemoManagementAccount())return;
   string done[];
   for(int group=0;group<2;group++)
     {
      int count=group==0 ? PositionsTotal() : OrdersTotal();
      for(int i=count-1;i>=0;i--)
        {
         ulong ticket=group==0 ? PositionGetTicket(i) : OrderGetTicket(i);
         if(ticket==0)continue;
         ulong magic=(ulong)(group==0 ? PositionGetInteger(POSITION_MAGIC) : OrderGetInteger(ORDER_MAGIC));
         string id=DnbResolveOwner(magic);if(id=="")continue;
         bool seen=false;for(int k=0;k<ArraySize(done);k++)if(done[k]==id)seen=true;
         if(seen)continue;
         string f[];
         if(!DnbLoadSignedDemoSource(DnbBridgeDirectory()+"\\"+id+".command",id,f))continue;
         int n=ArraySize(done);ArrayResize(done,n+1);done[n]=id;
         DnbProtectDemoSource(id,f);
        }
     }
  }
#endif
