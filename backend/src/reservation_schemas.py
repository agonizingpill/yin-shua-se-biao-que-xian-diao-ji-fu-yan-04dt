from pydantic import Field,field_validator
from .production_schemas import Inputs
class EstimateInput(Inputs):
    job_id:int
    planned_sheets:int=Field(ge=1,le=10000000)
    lot_id:int|None=None
class ReservationInput(Inputs):
    job_id:int
    lot_id:int
    planned_sheets:int=Field(ge=1,le=10000000)
    sheets:int|None=Field(default=None,ge=1,le=10000000)
    note:str=Field(default='',max_length=300)
class ReservationConfirm(Inputs):
    sheets:int|None=Field(default=None,ge=1,le=10000000)
class ReservationCancel(Inputs):
    note:str=Field(default='',max_length=300)
class ReservationIssue(Inputs):
    sheets:int=Field(ge=1,le=10000000)
    request_key:str=Field(min_length=2,max_length=64)
    @field_validator('request_key')
    @classmethod
    def key(cls,v):
        if not v.strip():raise ValueError('领用请求号不能为空')
        return v.strip()
class JobCloseInput(Inputs):
    planned_sheets:int=Field(ge=1,le=10000000)
    actual_sheets:int=Field(ge=1,le=10000000)
    note:str=Field(default='',max_length=300)
class LateUsageInput(Inputs):
    actual_sheets:int=Field(ge=1,le=10000000)
    note:str=Field(min_length=5,max_length=300)
    @field_validator('note')
    @classmethod
    def reason(cls,v):
        if len(v.strip())<5:raise ValueError('晚报依据至少5字')
        return v.strip()
