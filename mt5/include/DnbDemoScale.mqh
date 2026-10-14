#ifndef DNB_DEMO_SCALE_MQH
#define DNB_DEMO_SCALE_MQH
bool DnbLoadSignedDemoSource(string path,string id,string &f[]);
bool DnbReserveNativeThesis(string &f[])
  {
   string prefix=DnbBridgeDirectory()+"\\thesis."+DnbSha(f[18])+".";
   string path=prefix+f[2]+".member";
   string data=f[2]+"|"+f[18]+"|"+f[28]+"|"+f[30];
   string body=data+"|"+Hmac(data,g_journal_key);
   if(FileIsExist(path))return DnbRead(path)==body;
   string name;long find=FileFindFirst(prefix+"*.member",name);int count=0;
   if(find!=INVALID_HANDLE)
     {
      do
        {
         string parts[];string record=DnbRead(DnbBridgeDirectory()+"\\"+name);
         if(StringSplit(record,'|',parts)!=5 || parts[1]!=f[18] || !Hex(parts[0],32) || !Hex(parts[3],32) ||
            !Equal(Hmac(parts[0]+"|"+parts[1]+"|"+parts[2]+"|"+parts[3],g_journal_key),parts[4]))
            { FileFindClose(find);return false; }
         if(parts[3]==f[30]) { FileFindClose(find);return false; }
         if(++count>=3) { FileFindClose(find);return false; }
        }
      while(FileFindNext(find,name));FileFindClose(find);
     }
   if(count!=StringToInteger(f[28]))return false;
   return DnbWriteOnce(path,body);
  }
bool DnbValidateDemoScale(string &f[],string &reason)
  {
   ArrayResize(g_demo_allowed_tickets,0);
   if(f[28]!="0" && f[28]!="1" && f[28]!="2") { reason="scale_in_limit";return false; }
   int number=(int)StringToInteger(f[28]);
   if(number==0)
     {
      if(f[29]!="-" || f[33]!="-" || f[34]!="-") { reason="scale_protocol_invalid";return false; }
      return true;
     }
   if(number<1 || number>2 || !Hex(f[30],32)) { reason="scale_in_limit";return false; }
   long confirmation=StringToInteger(f[31]),now=(long)TimeGMT();
   if(confirmation>now || now-confirmation>30) { reason="stale_scale_confirmation";return false; }
   string ids[],stops[],targets[];
   int count=StringSplit(f[29],',',ids);
   if(count<1 || count>number || StringSplit(f[33],',',stops)!=count || StringSplit(f[34],',',targets)!=count)
      { reason="scale_membership_invalid";return false; }
   string symbol=DnbBrokerSymbol(f[8]);bool buy=StringFind(f[9],"BUY")==0;
   MqlTick q;if(!SymbolInfoTick(symbol,q))return false;
   double current=buy ? q.bid : q.ask,new_entry=StringToDouble(f[10]),total_volume=0;
   double initial_risk=StringToDouble(f[32]);
   if(initial_risk<=0) { reason="initial_risk_missing";return false; }
   if(!HistorySelect(0,TimeTradeServer()))return false;
   ulong pids[];
   for(int i=0;i<count;i++)
     {
      if(!Hex(ids[i],32) || ids[i]==f[2]) { reason="duplicate_scale_command";return false; }
      for(int j=0;j<i;j++)if(ids[j]==ids[i]) { reason="duplicate_scale_command";return false; }
      string prior[];
      if(!DnbLoadSignedDemoSource(DnbBridgeDirectory()+"\\"+ids[i]+".command",ids[i],prior) ||
         prior[18]!=f[18] || prior[8]!=f[8] || prior[26]!=f[26] || (StringFind(prior[9],"BUY")==0)!=buy ||
         confirmation<=StringToInteger(prior[6]) || f[30]==prior[30] || StringToDouble(f[13])>StringToDouble(prior[13]) ||
         initial_risk>StringToDouble(prior[32])) { reason="thesis_binding";return false; }
      DnbNativeBroker broker;ulong order=0,deal=0;
      if(broker.Search(DnbMagic(ids[i]),DnbComment(ids[i]),symbol,order,deal)!=1 || order==0) { reason="thesis_history_unresolved";return false; }
      // Search selects complete history. Aggregate actual entry fills, not prices/comments alone.
      double volume=0,weighted=0,cost=0;ulong pid=0;
      for(int j=0;j<HistoryDealsTotal();j++)
        {
         ulong d=HistoryDealGetTicket(j);
         if((ulong)HistoryDealGetInteger(d,DEAL_ORDER)!=order || HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_IN)continue;
         ulong identity=(ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID);
         if(pid!=0 && pid!=identity) { reason="thesis_position_unresolved";return false; }pid=identity;
         double v=HistoryDealGetDouble(d,DEAL_VOLUME);volume+=v;weighted+=v*HistoryDealGetDouble(d,DEAL_PRICE);
         cost+=HistoryDealGetDouble(d,DEAL_COMMISSION)+HistoryDealGetDouble(d,DEAL_FEE)+MathMin(0,HistoryDealGetDouble(d,DEAL_SWAP));
        }
      if(volume<=0 || pid==0) { reason="thesis_fill_missing";return false; }
      double entry=weighted/volume;
      if(!(buy ? current>entry && new_entry>entry : current<entry && new_entry<entry)) { reason="no_averaging_down";return false; }
      ulong ticket=0;double profit=0;
      for(int j=0;j<PositionsTotal();j++)
        {
         ulong t=PositionGetTicket(j);
         if((ulong)PositionGetInteger(POSITION_IDENTIFIER)!=pid)continue;
         ticket=t;
         if(PositionGetString(POSITION_SYMBOL)!=symbol || (PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY)!=buy ||
            PositionGetDouble(POSITION_SL)!=StringToDouble(stops[i]) || PositionGetDouble(POSITION_TP)!=StringToDouble(targets[i]))
            { reason="manual_intervention_race";return false; }
         double remaining=AccountInfoInteger(ACCOUNT_MARGIN_MODE)==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING ? PositionGetDouble(POSITION_VOLUME) : volume;
         if(!OrderCalcProfit(buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,symbol,remaining,entry,current,profit) ||
            profit+cost+MathMin(0,PositionGetDouble(POSITION_SWAP))<=0 ||
            PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP)<=0) { reason="no_adding_to_losing_leg";return false; }
         if(AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING &&
            (StringToDouble(f[11])!=PositionGetDouble(POSITION_SL) || StringToDouble(f[12])!=PositionGetDouble(POSITION_TP)))
            { reason="netting_leg_protection_change";return false; }
        }
      if(ticket==0) { reason="thesis_position_missing";return false; }
      int n=ArraySize(g_demo_allowed_tickets);bool seen=false;for(int j=0;j<n;j++)if(g_demo_allowed_tickets[j]==ticket)seen=true;
      if(!seen) { ArrayResize(g_demo_allowed_tickets,n+1);g_demo_allowed_tickets[n]=ticket; }
      n=ArraySize(pids);ArrayResize(pids,n+1);pids[n]=pid;total_volume+=volume;
     }
   if(AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     {
      if(ArraySize(g_demo_allowed_tickets)!=1 || !PositionSelectByTicket(g_demo_allowed_tickets[0]) || PositionGetDouble(POSITION_VOLUME)!=total_volume)
         { reason="netting_leg_volume_mismatch";return false; }
      for(int j=0;j<HistoryDealsTotal();j++)
        {
         ulong d=HistoryDealGetTicket(j);
         if((ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID)!=pids[0])continue;
         if(HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_IN) { reason="netting_partial_exit_unresolved";return false; }
         bool owned=false;for(int k=0;k<count;k++)if((ulong)HistoryDealGetInteger(d,DEAL_MAGIC)==DnbMagic(ids[k]))owned=true;
         if(!owned) { reason="manual_or_unmapped_same_symbol";return false; }
        }
     }
   for(int j=0;j<PositionsTotal();j++)
     {
      ulong t=PositionGetTicket(j);if(PositionGetString(POSITION_SYMBOL)!=symbol)continue;
      bool owned=false;for(int k=0;k<ArraySize(g_demo_allowed_tickets);k++)if(g_demo_allowed_tickets[k]==t)owned=true;
      if(!owned) { reason="manual_or_unmapped_same_symbol";return false; }
     }
   double entry=StringToDouble(f[10]),sl=StringToDouble(f[11]),tp=StringToDouble(f[12]);
   if(MathAbs(tp-entry)/MathAbs(entry-sl)<1.5) { reason="scale_in_reward_risk";return false; }
   return true;
  }
#endif
