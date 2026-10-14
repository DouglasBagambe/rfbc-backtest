"""Broker-authoritative lifecycle projection, including partial and manual exits."""
from decimal import Decimal
import mt5_risk as risk

def project(order, deals, positions, pending):
    if order is None:raise risk.Reject('order_history_required')
    associated=[d for d in deals if d['order_ticket']==order['ticket']]
    ids={d['position_id'] for d in associated if d['position_id']!='0'}
    ids.add(order['position_id']);ids.discard('0')
    # Exit magic/comment may be manual/broker-generated. Position identity wins.
    lifecycle=[d for d in deals if d['position_id'] in ids]
    entries=[d for d in lifecycle if d['entry'] in (0,2)]
    exits=[d for d in lifecycle if d['entry'] in (1,2,3)]
    filled=sum((risk.number(d['volume']) for d in associated if d['entry'] in (0,2)),Decimal(0))
    remaining=sum((risk.number(p['volume']) for p in positions if p.get('identifier',p['ticket']) in ids),Decimal(0))
    working=next((o for o in pending if o['ticket']==order['ticket']),None)
    reasons=sorted({d['reason'] for d in exits})
    if working:state='PARTIAL_PENDING' if filled else 'PENDING'
    elif remaining:state='PARTIAL_OPEN' if filled<risk.number(order['volume_initial']) else 'OPEN'
    elif filled:state='CLOSED' if exits else 'FILLED_RECONCILIATION_PENDING'
    elif order['state']==2:state='CANCELLED'
    elif order['state']==5:state='REJECTED'
    elif order['state']==6:state='EXPIRED'
    else:state='UNRESOLVED'
    realised=sum((risk.number(d[k]) for d in lifecycle for k in ('profit','commission','swap','fee')),Decimal(0))
    return {'state':state,'order_ticket':order['ticket'],'position_ids':sorted(ids),
            'deal_tickets':sorted((d['ticket'] for d in lifecycle),key=int),'filled_volume':float(filled),'remaining_volume':float(remaining),
            'realised_net_usd':float(realised),'exit_reasons':reasons,
            'manual_or_external_exit':any(d['reason'] in (0,1,2) for d in exits),
            'stop_out':any(d['reason']==6 for d in exits)}
