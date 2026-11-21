from fastapi import APIRouter,Depends
from sqlalchemy import select
from .db import db_session
from .auth import current,writers,admin
from .models import PrintJob
from .services import pack
from .reservation_models import JobClosure,PaperReservation
from .reservation_schemas import EstimateInput,ReservationInput,ReservationIssue,JobCloseInput,LateUsageInput,ReservationConfirm,ReservationCancel
from . import reservation_service
router=APIRouter()

def closure_pack(s,row):
    job=s.get(PrintJob,row.job_id)
    late=row.late_reports or []
    return {**pack(row),'job_code':job.code if job else None,'paper':job.paper if job else None,
            'effective_actual_sheets':reservation_service.effective_actual(row),
            'last_late_report':late[-1] if late else None}

@router.get('/job-closures')
def closures(s=Depends(db_session),u=Depends(current)):return [closure_pack(s,x) for x in s.scalars(select(JobClosure).order_by(JobClosure.closed_at.desc(),JobClosure.id.desc()))]
@router.post('/jobs/{key}/close')
def close(key:int,b:JobCloseInput,s=Depends(db_session),u=Depends(admin)):return closure_pack(s,reservation_service.close_job(s,key,b,u))
@router.post('/job-closures/{key}/late-usage')
def late(key:int,b:LateUsageInput,s=Depends(db_session),u=Depends(writers)):return closure_pack(s,reservation_service.report_late_usage(s,key,b,u))

@router.post('/paper-reservations/estimate')
def estimate(b:EstimateInput,s=Depends(db_session),u=Depends(current)):
    basis=reservation_service.estimate(s,b.job_id,b.lot_id)
    basis['suggested_sheets']=reservation_service.suggest(basis,b.planned_sheets)
    basis['planned_sheets']=b.planned_sheets
    basis['shortfall']=None if basis['suggested_sheets'] is None else max(0,basis['suggested_sheets']-basis['available_sheets'])
    return basis
@router.get('/paper-reservations')
def list_reservations(s=Depends(db_session),u=Depends(current)):return [pack(x) for x in s.scalars(select(PaperReservation).order_by(PaperReservation.id.desc()))]
@router.post('/paper-reservations')
def create(b:ReservationInput,s=Depends(db_session),u=Depends(writers)):return pack(reservation_service.create(s,b,u))
@router.post('/paper-reservations/{key}/confirm')
def confirm(key:int,b:ReservationConfirm,s=Depends(db_session),u=Depends(admin)):return pack(reservation_service.confirm(s,key,u,b.sheets))
@router.post('/paper-reservations/{key}/issue')
def issue(key:int,b:ReservationIssue,s=Depends(db_session),u=Depends(writers)):return reservation_service.issue(s,key,b,u)
@router.post('/paper-reservations/{key}/cancel')
def cancel(key:int,b:ReservationCancel,s=Depends(db_session),u=Depends(writers)):return pack(reservation_service.cancel(s,key,u,b.note))
