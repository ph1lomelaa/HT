from datetime import date,time
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict,model_validator
from pligrim_bot.core.parsers.people_parser import is_valid_name

class Room(BaseModel):
    kind:Literal['SGL','DBL','TWIN','TRPL','QUAD']
    people:list[str]=Field(min_length=1,max_length=12)
    adults:int=Field(ge=0,le=4)
    @model_validator(mode='after')
    def validate_room(self):
        if any(not is_valid_name(n) or len(n)>120 for n in self.people):raise ValueError('Проверьте имена паломников')
        if self.adults>len(self.people):raise ValueError('Число взрослых больше числа паломников')
        self.people=[n.strip() for n in self.people]
        return self

class People(BaseModel):
    rooms:list[Room]=Field(min_length=1,max_length=60)

class Voucher(BaseModel):
    model_config=ConfigDict(extra='ignore',str_strip_whitespace=True)
    city1:str=Field(min_length=1,max_length=80)
    hotel1:str=Field(min_length=1,max_length=300)
    dates1:str=Field(min_length=1,max_length=80)
    checkin1:str='16:00'
    city2:str|None=Field(default=None,max_length=80)
    hotel2:str|None=Field(default=None,max_length=300)
    dates2:str|None=Field(default=None,max_length=80)
    checkin2:str='16:00'
    service:str=Field(default='Виза и страховка',max_length=300)
    transfer:str=Field(default='Автобус',max_length=300)
    meal:str=Field(default='Завтрак и ужин',max_length=300)
    guide:str=Field(default='Групповой гид',max_length=300)
    excursions:str=Field(default='Мекка, Медина',max_length=300)
    tech_guide:str=Field(default='+966 56 328 0325',max_length=120)
    people:People
    @model_validator(mode='after')
    def validate_times(self):
        for value in (self.checkin1,self.checkin2):
            try:time.fromisoformat(value)
            except ValueError:raise ValueError('Некорректное время заселения') from None
        if self.city2 and (not self.hotel2 or not self.dates2):raise ValueError('Заполните отель и даты второго города')
        return self

class FlightSegment(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True)
    airline:str=Field(min_length=1,max_length=80)
    number:str=Field(min_length=1,max_length=30)
    origin:str=Field(min_length=1,max_length=80)
    destination:str=Field(min_length=1,max_length=80)
    departure_date:date
    arrival_date:date
    departure_time:time
    arrival_time:time
    @model_validator(mode='after')
    def chronological(self):
        # Times are local to each airport; do not compare clock values across time zones.
        if self.arrival_date<self.departure_date:
            raise ValueError('Прибытие не может быть раньше вылета')
        return self

class Flight(BaseModel):
    outbound:FlightSegment
    inbound:FlightSegment|None=None

class GenerateRequest(BaseModel):
    title:str=Field(default='Индивидуальный ваучер',min_length=1,max_length=200)
    voucher:Voucher
    background:int=Field(default=0,ge=0,le=2)
    flight:Flight|None=None
    deliver_to_chat:bool=True
    request_id:str=Field(min_length=16,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')
