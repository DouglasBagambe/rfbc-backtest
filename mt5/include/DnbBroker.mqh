#ifndef DNB_BROKER_MQH
#define DNB_BROKER_MQH
// Native operations and recovery. The host must implement the live-authorisation gate.
bool DnbBrokerIoAuthorised();
string DnbSha(string text)
  {
   uchar data[],key[],digest[];
   int n=StringToCharArray(text,data,0,WHOLE_ARRAY,CP_UTF8); ArrayResize(data,n-1);
   if(CryptEncode(CRYPT_HASH_SHA256,data,key,digest)!=32) return "";
   string out=""; for(int i=0;i<32;i++) out+=StringFormat("%02x",(uint)digest[i]);
   return out;
  }
bool DnbId(string id)
  {
   if(StringLen(id)!=32) return false;
   for(int i=0;i<32;i++) if(StringFind("0123456789abcdef",StringSubstr(id,i,1))<0) return false;
   return true;
  }
ulong DnbMagic(string id)
  {
   string hash=DnbSha("dnb:"+id); ulong value=0;
   for(int i=0;i<15;i++) value=value*16+(ulong)StringFind("0123456789abcdef",StringSubstr(hash,i,1));
   return value;
  }
string DnbComment(string id) { return "dnb:"+StringSubstr(id,0,24); }
string DnbRead(string path)
  {
   int h=FileOpen(path,FILE_READ|FILE_TXT|FILE_ANSI,0,CP_UTF8); if(h==INVALID_HANDLE) return "";
   string s=FileReadString(h); FileClose(h); return s;
  }
bool DnbWriteOnce(string path,string body)
  {
   if(FileIsExist(path)) return false;
   string tmp=path+".tmp";
   int h=FileOpen(tmp,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8); if(h==INVALID_HANDLE) return false;
   uint wrote=FileWriteString(h,body); FileFlush(h); FileClose(h);
   if(wrote!=(uint)StringLen(body) || DnbRead(tmp)!=body) return false;
   // No overwrite: a second chart/process cannot replace an existing intent.
   if(!FileMove(tmp,0,path,0)) return false;
   return DnbRead(path)==body;
  }
string DnbCanonical(MqlTradeRequest &r,string thesis)
  {
   return StringFormat("%d|%s|%d|%I64u|%I64u|%.10f|%.10f|%.10f|%.10f|%.10f|%d|%d|%I64d|%I64u|%s|%s",
     (int)r.action,r.symbol,(int)r.type,r.order,r.position,r.volume,r.price,r.sl,r.tp,r.stoplimit,
     (int)r.type_filling,(int)r.type_time,(long)r.expiration,r.magic,r.comment,thesis);
  }
class DnbBrokerPort
  {
public:
   virtual bool Check(MqlTradeRequest &r,MqlTradeCheckResult &result)=0;
   virtual bool Send(MqlTradeRequest &r,MqlTradeResult &result)=0;
   // -1 = unavailable/ambiguous; 0 = no evidence; 1 = exact broker identity found.
   virtual int Search(ulong magic,string comment,string symbol,ulong &order,ulong &deal)=0;
  };
class DnbNativeBroker : public DnbBrokerPort
  {
public:
   virtual bool Check(MqlTradeRequest &r,MqlTradeCheckResult &result) { return OrderCheck(r,result); }
   virtual bool Send(MqlTradeRequest &r,MqlTradeResult &result)
     {
      if(!DnbBrokerIoAuthorised()) return false;
      return OrderSend(r,result);
     }
   virtual int Search(ulong magic,string comment,string symbol,ulong &order,ulong &deal)
     {
      order=0; deal=0;
      if(!TerminalInfoInteger(TERMINAL_CONNECTED) || !HistorySelect(0,TimeTradeServer())) return -1;
      // Require both magic and exact retained comment; rewritten comments fail closed.
      for(int i=0;i<OrdersTotal();i++)
        {
         ulong t=OrderGetTicket(i); if(t==0) return -1;
         if((ulong)OrderGetInteger(ORDER_MAGIC)==magic)
           {
            if(OrderGetString(ORDER_COMMENT)!=comment || OrderGetString(ORDER_SYMBOL)!=symbol) return -1;
            if(order!=0 && order!=t) return -1; order=t;
           }
        }
      for(int i=0;i<HistoryOrdersTotal();i++)
        {
         ulong t=HistoryOrderGetTicket(i); if(t==0) return -1;
         if((ulong)HistoryOrderGetInteger(t,ORDER_MAGIC)==magic)
           {
            if(HistoryOrderGetString(t,ORDER_COMMENT)!=comment || HistoryOrderGetString(t,ORDER_SYMBOL)!=symbol) return -1;
            if(order!=0 && order!=t) return -1; order=t;
           }
        }
      for(int i=0;i<HistoryDealsTotal();i++)
        {
         ulong t=HistoryDealGetTicket(i); if(t==0) return -1;
         if((ulong)HistoryDealGetInteger(t,DEAL_MAGIC)==magic)
           {
            if(HistoryDealGetString(t,DEAL_COMMENT)!=comment || HistoryDealGetString(t,DEAL_SYMBOL)!=symbol) return -1;
            ulong parent=(ulong)HistoryDealGetInteger(t,DEAL_ORDER);
            if(order!=0 && order!=parent) return -1; order=parent; deal=t;
           }
        }
      return order!=0 || deal!=0 ? 1 : 0;
     }
  };
// All paths, including management, cross this one write-ahead journal boundary.
// Intent existence prohibits resubmission even if history currently has no match.
string DnbSubmitOnce(DnbBrokerPort &broker,string directory,string id,string thesis,
                     MqlTradeRequest &request,ulong &order,ulong &deal,uint &retcode)
  {
   order=0;deal=0;retcode=0;
   if(!DnbId(id) || StringLen(thesis)>64 || StringFind(thesis,"|")>=0) return "INVALID_ID";
   FolderCreate(directory);
   int lock=FileOpen(directory+"\\account.lock",FILE_WRITE|FILE_BIN);
   if(lock==INVALID_HANDLE) return "BUSY";
   request.magic=DnbMagic(id); request.comment=DnbComment(id);
   string fingerprint=DnbSha(DnbCanonical(request,thesis));
   string path=directory+"\\"+id+".intent";
   string intent="DNB1|"+id+"|"+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"|"+AccountInfoString(ACCOUNT_SERVER)+"|"+fingerprint+"|"+DnbCanonical(request,thesis);
   if(FileIsExist(path))
     {
      string prior=DnbRead(path);
      if(prior!=intent) { FileClose(lock);return "CORRUPT_OR_CONFLICT"; }
      int found=broker.Search(request.magic,request.comment,request.symbol,order,deal);
      FileClose(lock);
      return found==1 ? "RECOVERED" : "UNRESOLVED"; // Never call Send again.
     }
   // Refuse a broker identity collision before creating a new command intent.
   int found=broker.Search(request.magic,request.comment,request.symbol,order,deal);
   if(found!=0) { FileClose(lock);return found==1 ? "ORPHAN_BROKER_IDENTITY" : "HISTORY_UNAVAILABLE"; }
   MqlTradeCheckResult check={};
   if(!broker.Check(request,check) || (check.retcode!=0 && check.retcode!=TRADE_RETCODE_DONE))
     { retcode=check.retcode;FileClose(lock);return "CHECK_REJECTED"; }
   if(!DnbWriteOnce(path,intent)) { FileClose(lock);return "INTENT_WRITE_FAILED"; }
   MqlTradeResult result={};
   bool sent=broker.Send(request,result);
   order=result.order;deal=result.deal;retcode=result.retcode;
   string outcome=StringFormat("%d|%u|%I64u|%I64u|%.10f",sent ? 1 : 0,retcode,order,deal,result.volume);
   if(!DnbWriteOnce(directory+"\\"+id+".result",outcome)) { FileClose(lock);return "UNRESOLVED"; }
   FileClose(lock);
   if(!sent || retcode==TRADE_RETCODE_TIMEOUT || retcode==TRADE_RETCODE_CONNECTION) return "UNRESOLVED";
   if(retcode==TRADE_RETCODE_DONE_PARTIAL) return "PARTIAL";
   if(retcode==TRADE_RETCODE_PLACED) return "PLACED";
   if(retcode==TRADE_RETCODE_DONE) return "ACCEPTED";
   return "BROKER_REJECTED";
  }
bool DnbFillMode(string symbol,bool pending,ENUM_ORDER_TYPE_FILLING &filling)
  {
   if(pending) { filling=ORDER_FILLING_RETURN;return true; }
   long flags=SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE);
   if((flags&SYMBOL_FILLING_FOK)!=0) { filling=ORDER_FILLING_FOK;return true; }
   if((flags&SYMBOL_FILLING_IOC)!=0) { filling=ORDER_FILLING_IOC;return true; }
   if(SymbolInfoInteger(symbol,SYMBOL_TRADE_EXEMODE)!=SYMBOL_TRADE_EXECUTION_MARKET)
     { filling=ORDER_FILLING_RETURN;return true; }
   return false;
  }
bool DnbPlacement(string symbol,ENUM_ORDER_TYPE type,double volume,double entry,double sl,double tp,
                  double stoplimit,datetime expiry,MqlTradeRequest &r)
  {
   ZeroMemory(r);
   if(type<ORDER_TYPE_BUY || type>ORDER_TYPE_SELL_STOP_LIMIT || !SymbolSelect(symbol,true)) return false;
   double min=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN),max=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX),step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   if(step<=0 || volume<min || volume>max || MathAbs(volume/step-MathRound(volume/step))>1e-8) return false;
   bool buy=type==ORDER_TYPE_BUY || type==ORDER_TYPE_BUY_LIMIT || type==ORDER_TYPE_BUY_STOP || type==ORDER_TYPE_BUY_STOP_LIMIT;
   if(!(buy ? sl<entry && entry<tp : tp<entry && entry<sl) || sl<=0 || tp<=0) return false;
   r.action=type<=ORDER_TYPE_SELL ? TRADE_ACTION_DEAL : TRADE_ACTION_PENDING;
   r.symbol=symbol;r.type=type;r.volume=volume;r.price=entry;r.sl=sl;r.tp=tp;r.stoplimit=stoplimit;r.deviation=5;
   r.type_time=expiry>0 ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;r.expiration=expiry;
   return DnbFillMode(symbol,r.action==TRADE_ACTION_PENDING,r.type_filling);
  }
bool DnbManagement(ENUM_TRADE_REQUEST_ACTIONS action,ulong ticket,ulong expected_magic,double expected_volume,
                   double expected_sl,double expected_tp,double volume,double price,double sl,double tp,
                   double stoplimit,datetime expiry,MqlTradeRequest &r)
  {
   ZeroMemory(r);r.action=action;
   if(action==TRADE_ACTION_SLTP || action==TRADE_ACTION_DEAL)
     {
      if(!PositionSelectByTicket(ticket) || (ulong)PositionGetInteger(POSITION_MAGIC)!=expected_magic ||
         PositionGetDouble(POSITION_VOLUME)!=expected_volume || PositionGetDouble(POSITION_SL)!=expected_sl || PositionGetDouble(POSITION_TP)!=expected_tp) return false;
      r.position=ticket;r.symbol=PositionGetString(POSITION_SYMBOL);r.sl=sl;r.tp=tp;
      if(action==TRADE_ACTION_DEAL)
        {
         if(volume<=0 || volume>expected_volume) return false;
         r.type=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
         MqlTick q;if(!SymbolInfoTick(r.symbol,q)) return false;r.price=r.type==ORDER_TYPE_BUY ? q.ask : q.bid;
         r.volume=volume;r.sl=0;r.tp=0;r.deviation=5;
         if(!DnbFillMode(r.symbol,false,r.type_filling)) return false;
        }
      // Stop widening must be explicitly risk-validated by the caller; default forbids it.
      else if(sl<=0 || (PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? sl<expected_sl : sl>expected_sl)) return false;
     }
   else if(action==TRADE_ACTION_REMOVE || action==TRADE_ACTION_MODIFY)
     {
      if(!OrderSelect(ticket) || (ulong)OrderGetInteger(ORDER_MAGIC)!=expected_magic ||
         OrderGetDouble(ORDER_VOLUME_CURRENT)!=expected_volume || OrderGetDouble(ORDER_SL)!=expected_sl || OrderGetDouble(ORDER_TP)!=expected_tp) return false;
      r.order=ticket;r.symbol=OrderGetString(ORDER_SYMBOL);
      if(action==TRADE_ACTION_MODIFY)
        { r.price=price;r.sl=sl;r.tp=tp;r.stoplimit=stoplimit;r.type_time=expiry>0 ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;r.expiration=expiry; }
     }
   else return false;
   return true;
  }
#endif
