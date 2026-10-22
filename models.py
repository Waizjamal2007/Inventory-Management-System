"""Validated inputs; money uses decimal arithmetic and PKR throughout accounting."""
from decimal import Decimal
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Row(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, coerce_numbers_to_str=True)
    id: str = Field(min_length=1, max_length=80)

class Item(Row):
    item: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(ge=0, le=1000000000)
    rmb_price: Decimal = Field(ge=0, le=1000000000)
    exchange_rate: Decimal = Field(gt=0, le=1000000)
    pk_sell: Decimal = Field(ge=0, le=1000000000)
    low_stock: Decimal = Field(default=Decimal(5), ge=0)

class Line(BaseModel):
    model_config = ConfigDict(extra='forbid')
    item_id: str
    quantity: Decimal = Field(gt=0, le=1000000000)
    price: Decimal = Field(ge=0, le=1000000000)
    unit_cost: Decimal | None = Field(default=None, ge=0, le=1000000000000000)

class Bill(Row):
    date: date
    name: str = Field(min_length=1, max_length=200)
    bill_no: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(ge=0, le=1000000000000000)
    lines: list[Line] = Field(default_factory=list, max_length=100)

class Payment(Row):
    date: date
    name: str = Field(min_length=1, max_length=200)
    details: str = Field(default='', max_length=1000)
    amount: Decimal = Field(gt=0, le=1000000000000000)

class Account(Row):
    name: str = Field(min_length=1, max_length=200)
    sheet_no: str = Field(default='', max_length=100)
    opening_balance: Decimal = Field(default=Decimal(0), ge=-1000000000000000, le=1000000000000000)

class Expense(Payment):
    pass

class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    exchange_rate: Decimal = Field(default=Decimal(39), gt=0, le=1000000)
    business_name: str = Field(default='Inventory Management System', min_length=1, max_length=100)

class State(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(default=0, ge=0)
    inventory: list[Item] = Field(default_factory=list, max_length=5000)
    bills: list[Bill] = Field(default_factory=list, max_length=5000)
    payments: list[Payment] = Field(default_factory=list, max_length=5000)
    accounts: list[Account] = Field(default_factory=list, max_length=5000)
    expenses: list[Expense] = Field(default_factory=list, max_length=5000)
    settings: Settings = Field(default_factory=Settings)
    imports: list[dict] = Field(default_factory=list, max_length=5000)

TABLES = {'inventory': Item, 'bills': Bill, 'payments': Payment, 'accounts': Account, 'expenses': Expense}

def normalize(state: State, previous: State | None = None):
    items = {r.id:r for r in state.inventory}
    for table in TABLES:
        rows = getattr(state, table)
        if len({r.id for r in rows}) != len(rows):
            raise ValueError('Duplicate row IDs')
    names = [a.name.casefold() for a in state.accounts]
    if len(names) != len(set(names)):
        raise ValueError('One opening account per customer name is allowed')
    bills = [(b.name.casefold(), b.bill_no.casefold()) for b in state.bills]
    if len(bills) != len(set(bills)):
        raise ValueError('Duplicate bill number for this customer')
    old_lines = {}
    if previous:
        for b in previous.bills:
            for index, line in enumerate(b.lines):
                old_lines[(b.id,index,line.item_id)] = line
    sold = {}
    for b in state.bills:
        if b.lines:
            for index,line in enumerate(b.lines):
                if line.item_id not in items:
                    raise ValueError('Bill references a missing inventory item')
                old = old_lines.get((b.id,index,line.item_id))
                # Cost snapshots are server-owned and remain fixed after the sale.
                line.unit_cost = old.unit_cost if old else items[line.item_id].rmb_price * items[line.item_id].exchange_rate
                sold[line.item_id] = sold.get(line.item_id, Decimal(0)) + line.quantity
            b.amount = sum((l.quantity*l.price for l in b.lines), Decimal(0))
    for item_id, qty in sold.items():
        if qty > items[item_id].quantity:
            raise ValueError(f'Insufficient stock: {items[item_id].item}')
    return state

def reports(s: State):
    d=Decimal
    sold={}
    daily={}
    revenue=d(0); cost=d(0); uncosted=d(0)
    ledger=[]
    for a in s.accounts:
        if a.opening_balance:
            ledger.append(dict(date='0001-01-01',name=a.name,details='Opening balance',debit=max(a.opening_balance,d(0)),credit=max(-a.opening_balance,d(0)),id=a.id))
    for b in s.bills:
        revenue+=b.amount
        day=daily.setdefault(str(b.date),dict(revenue=d(0),payments=d(0),expenses=d(0)))
        day['revenue']+=b.amount
        if not b.lines: uncosted+=b.amount
        for l in b.lines:
            sold[l.item_id]=sold.get(l.item_id,d(0))+l.quantity
            cost+=l.quantity*(l.unit_cost or d(0))
        ledger.append(dict(date=str(b.date),name=b.name,details='Bill '+b.bill_no,debit=b.amount,credit=d(0),id=b.id))
    for p in s.payments:
        daily.setdefault(str(p.date),dict(revenue=d(0),payments=d(0),expenses=d(0)))['payments']+=p.amount
        ledger.append(dict(date=str(p.date),name=p.name,details=p.details,debit=d(0),credit=p.amount,id=p.id))
    for p in s.expenses:
        daily.setdefault(str(p.date),dict(revenue=d(0),payments=d(0),expenses=d(0)))['expenses']+=p.amount
    balances={a.name.casefold():dict(name=a.name,sheet_no=a.sheet_no,balance=d(0)) for a in s.accounts}
    for l in sorted(ledger,key=lambda x:(x['date'],x['id'])):
        a=balances.setdefault(l['name'].casefold(),dict(name=l['name'],sheet_no='',balance=d(0)))
        a['balance']+=l['debit']-l['credit'];l['balance']=a['balance']
    inventory=[]
    for i in s.inventory:
        remaining=i.quantity-sold.get(i.id,d(0)); unit=i.rmb_price*i.exchange_rate
        inventory.append(dict(**i.model_dump(),sold=sold.get(i.id,d(0)),remaining=remaining,total_rmb=i.quantity*i.rmb_price,total_pk_sell=remaining*i.pk_sell,stock_cost=remaining*unit,potential_profit=remaining*(i.pk_sell-unit)))
    expense=sum((e.amount for e in s.expenses),d(0))
    return dict(inventory=inventory,ledger=sorted(ledger,key=lambda l:(l['date'],l['id'])),accounts=list(balances.values()),daily=[dict(date=k,**v) for k,v in sorted(daily.items())],totals=dict(revenue=revenue,payments=sum((p.amount for p in s.payments),d(0)),cost_of_goods=cost,expenses=expense,net_profit=revenue-uncosted-cost-expense,uncosted_sales=uncosted,receivables=sum((max(a['balance'],d(0)) for a in balances.values()),d(0)),customer_credit=sum((max(-a['balance'],d(0)) for a in balances.values()),d(0)),stock_value=sum((i['stock_cost'] for i in inventory),d(0)),potential_sales=sum((i['total_pk_sell'] for i in inventory),d(0)),units=sum((i['remaining'] for i in inventory),d(0))))
