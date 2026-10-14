"""Account-specific planning, never execution permission or a recovery target.

Source: GOAT Stride/HERO and payout pages verified 2026-10-14.
Historical anchors and payout eligibility must be independently verified.
"""
from datetime import date
from decimal import Decimal
from mt5_risk import number, positive, Reject

INITIAL = Decimal('2500')

def trailing_floor(verified_peak):
    return min(INITIAL, positive(verified_peak) - INITIAL * Decimal('.05'))

def conservative_trailing_floor(peak):
    # Reserve $12.50 above the official fixed-dollar floor, including at cap.
    return trailing_floor(peak) + INITIAL * Decimal('.005')

def payout_plan(balance, daily_net, *, history_verified, purchase_date=None,
                cycle_elapsed=False, pending=False, largest_win=None, largest_loss=None):
    balance = positive(balance)
    if not isinstance(daily_net, dict): raise Reject('invalid_payout_history')
    days = []
    for key, value in daily_net.items():
        date.fromisoformat(key)
        days.append(number(value))
    total = sum(days, Decimal(0))
    best = max([Decimal(0)] + days)
    gross_cap = INITIAL * Decimal('.06')
    net_profit = max(Decimal(0), balance - INITIAL)
    blockers = []
    if not history_verified: blockers.append('payout_history_unverified')
    if purchase_date is None: blockers.append('purchase_date_unknown')
    else:
        bought = date.fromisoformat(purchase_date)
        if bought >= date(2026,10,8):
            if largest_win is None or largest_loss is None: blockers.append('best_worst_trade_unknown')
            elif number(largest_win) < abs(number(largest_loss)): blockers.append('best_worst_trade')
    qualified = sum(x >= INITIAL * Decimal('.005') for x in days)
    if qualified < 6: blockers.append('profitable_days')
    if total <= 0 or best > total * Decimal('.15'): blockers.append('consistency')
    if not cycle_elapsed: blockers.append('payout_timing')
    if pending: blockers.append('payout_pending')
    if net_profit < gross_cap: blockers.append('target_not_reached')
    # Target pause is conservative even while paperwork/eligibility is unresolved.
    return {'gross_cap_usd': float(gross_cap), 'estimated_received_usd': float(gross_cap*Decimal('.90')*Decimal('.97')),
            'deficit_usd': float(max(Decimal(0),INITIAL-balance)),
            'additional_to_target_usd': float(max(Decimal(0),INITIAL+gross_cap-balance)),
            'qualifying_days': qualified, 'eligibility_blockers': blockers,
            'pause_new_risk': net_profit >= gross_cap or pending,
            'execution_authorised': False}
