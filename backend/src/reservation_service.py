"""备纸估算与留纸。

估算只用同类纸的已结案开机单：较老的结案单做训练，最近几张留出验误差。
新材料、样本不足或误差过大时不硬算，由主管直接填备纸数。
每张备纸单在建立时把依据（样本、比率、留出误差、可用库存、缺纸数）冻结下来，
之后补报的晚报用量只会进入新的估算，不改写旧单。
"""
import math
import re
from sqlalchemy import select,func
from fastapi import HTTPException
from .models import PrintJob
from .dispatch_models import PaperLot,PaperIssue
from .reservation_models import JobClosure,PaperReservation
from .services import audit,now,pack
from .paper_service import locked

MIN_TRAIN=3          # 训练样本下限，低于此数由主管填
HOLDOUT_MAX=3        # 最近几张结案单留出验误差
MAX_ERROR_PCT=25.0   # 留出平均误差超过则提示复核（不阻断主管判断）

def norm_paper(v):return re.sub(r'\s+','',(v or '').lower())
def gsm_of(v):
    m=re.search(r'(\d+)\s*g',v or '',re.I)
    return int(m.group(1)) if m else None

def effective_actual(c):
    """晚报用量以最近一次晚报为准；结案值本身不改写，旧备纸依据也不回写。"""
    late=c.late_reports or []
    return int(late[-1]['actual_sheets']) if late else int(c.actual_sheets)

def _closures(s,job):
    rows=s.execute(select(JobClosure,PrintJob).join(PrintJob,JobClosure.job_id==PrintJob.id)).all()
    same=[(c,j) for c,j in rows if norm_paper(j.paper)==norm_paper(job.paper)]
    same.sort(key=lambda r:(r[0].closed_at,r[0].id),reverse=True)
    return same

def _availability(s,job,lot_id=None):
    if lot_id is not None:
        lot=s.get(PaperLot,lot_id)
        return int(lot.available_sheets) if lot else 0
    gsm=gsm_of(job.paper)
    query=select(func.coalesce(func.sum(PaperLot.available_sheets),0)).where(PaperLot.state=='active')
    if gsm is not None:query=query.where(PaperLot.gsm==gsm)
    return int(s.scalar(query))

def estimate(s,job_id,lot_id=None):
    job=s.get(PrintJob,job_id)
    if not job:raise HTTPException(404,'工单不存在')
    same=_closures(s,job)
    # 至少留一张近期结案单验误差；训练不足三张时不硬算，交主管填。
    holdout_count=min(HOLDOUT_MAX,len(same)-MIN_TRAIN) if len(same)>MIN_TRAIN else 0
    held,training=same[:holdout_count],same[holdout_count:]
    basis={'job_id':job.id,'job_code':job.code,'paper':job.paper,'sample_count':len(same),
           'train_count':len(training),'holdout_count':len(held),'method':'同类纸结案单实耗/计划印量均值'}
    if len(training)<MIN_TRAIN or not held:
        basis.update(usable=False,suggested_sheets=None,manual_required=True,ratio=None,error_pct=None,
                     holdout=[],available_sheets=_availability(s,job,lot_id),shortfall=None,
                     reason=f'同类纸（{job.paper}）结案样本不足：需至少{MIN_TRAIN}张训练加1张验误差，请主管填写备纸数')
        return basis
    ratio=sum(effective_actual(c)/c.planned_sheets for c,_ in training)/len(training)
    rows=[]
    for c,j in held:
        actual=effective_actual(c);predicted=c.planned_sheets*ratio
        rows.append({'job_code':j.code,'closed_at':c.closed_at,'planned_sheets':c.planned_sheets,
                     'actual_sheets':actual,'predicted_sheets':round(predicted,1),
                     'error_pct':round(abs(predicted-actual)/actual*100,2),'late':bool(c.late_reports)})
    error_pct=round(sum(r['error_pct'] for r in rows)/len(rows),2) if rows else None
    basis.update(usable=True,manual_required=False,ratio=round(ratio,4),error_pct=error_pct,
                 holdout=rows,holdout_note='最近结案单只用于验误差，不参与比率计算',
                 high_error=error_pct is not None and error_pct>MAX_ERROR_PCT,
                 train_ratios=[{'job_code':j.code,'ratio':round(effective_actual(c)/c.planned_sheets,4)} for c,j in training])
    basis['available_sheets']=_availability(s,job,lot_id)
    return basis

def suggest(basis,planned_sheets):
    if not basis.get('usable') or not basis.get('ratio'):return None
    return max(1,math.ceil(planned_sheets*basis['ratio']))

def close_job(s,key,b,u):
    job=locked(s,PrintJob,key)
    if job.status!='production':raise HTTPException(409,'仅已签印量产的工单可以结案')
    if s.scalar(select(JobClosure.id).where(JobClosure.job_id==job.id)):raise HTTPException(409,'该工单已结案')
    if b.actual_sheets<1:raise HTTPException(409,'实耗张数须为正')
    row=JobClosure(job_id=job.id,planned_sheets=b.planned_sheets,actual_sheets=b.actual_sheets,
                   note=b.note.strip(),late_reports=[],closed_by=u.email,closed_at=now())
    s.add(row);job.status='closed';audit(s,u,f'结案开机单 {job.code} 计划{b.planned_sheets} 实耗{b.actual_sheets}');s.commit();return row

def report_late_usage(s,key,b,u):
    """晚报用量：不追改已结案值，只追加一条晚报记录，供之后的新估算使用。"""
    row=locked(s,JobClosure,key)
    if b.actual_sheets==effective_actual(row) and not (row.late_reports or []):raise HTTPException(409,'晚报用量与结案实耗一致，无需更正')
    reports=[*(row.late_reports or []),{'actual_sheets':b.actual_sheets,'note':b.note,'reported_by':u.email,'reported_at':now()}]
    row.late_reports=reports
    audit(s,u,f'晚报用量 结案单{key} 实耗更正为{b.actual_sheets}张');s.commit();return row

def _check_lot(s,job,lot_id):
    lot=locked(s,PaperLot,lot_id)
    gsm=gsm_of(job.paper)
    if gsm is not None and gsm!=lot.gsm:raise HTTPException(409,'纸张克重须匹配工单paper中的g数')
    return lot

def create(s,b,u):
    job=locked(s,PrintJob,b.job_id)
    if job.status in ('hold','closed'):raise HTTPException(409,'停机或已结案工单不办理备纸')
    lot=_check_lot(s,job,b.lot_id)
    est=estimate(s,job.id,lot.id)
    if b.sheets is None:
        sheets=suggest(est,b.planned_sheets)
        if sheets is None:raise HTTPException(409,est.get('reason') or '估算不可用，请主管填写备纸数')
        source='estimate'
    else:
        if u.role!='admin':raise HTTPException(403,'手工备纸数仅由印刷主管填写')
        sheets=b.sheets;source='manual'
    available=int(lot.available_sheets)
    basis={**est,'source':source,'planned_sheets':b.planned_sheets,'requested_sheets':sheets,
           'available_sheets':available,'shortfall':max(0,sheets-available)}
    if source=='estimate':basis['estimated_sheets']=sheets
    row=PaperReservation(job_id=job.id,lot_id=lot.id,sheets=sheets,state='draft',basis=basis,
                         issue_keys={},note=b.note.strip(),created_by=u.email,created_at=now())
    s.add(row);audit(s,u,f'备纸申请 {job.code} {sheets}张（{ "估算" if source=="estimate" else "主管手工"}）');s.commit();return row

def confirm(s,key,u,sheets=None):
    """主管确认留纸。缺纸时主管可只按现有可用数留一部分，差额仍保留在缺纸依据里。"""
    ref=s.get(PaperReservation,key)
    if not ref:raise HTTPException(404,'备纸单不存在')
    job=locked(s,PrintJob,ref.job_id)
    if job.status in ('hold','closed'):raise HTTPException(409,'停机或已结案工单不办理备纸')
    row=locked(s,PaperReservation,key)
    if row.state!='draft':raise HTTPException(409,'仅待确认的备纸单可由主管留纸')
    lot=locked(s,PaperLot,row.lot_id)
    if lot.state!='active':raise HTTPException(409,'纸张批次已隔离，不能留纸')
    available=int(lot.available_sheets)
    take=row.sheets if sheets is None else sheets
    if take<1 or take>row.sheets:raise HTTPException(409,f'确认留纸张数须在1到申请数{row.sheets}之间')
    if available<take:raise HTTPException(409,f'可用库存不足：需留{take}张，可领{available}张')
    lot.available_sheets=available-take;row.sheets=take;row.state='held';row.confirmed_by=u.email;row.confirmed_at=now()
    basis=dict(row.basis or {});basis['confirmed_available_sheets']=available;basis['confirmed_sheets']=take
    basis['confirmed_shortfall']=max(0,int(basis.get('requested_sheets') or take)-take);row.basis=basis
    audit(s,u,f'主管确认留纸 备纸单{row.id} {take}张');s.commit();return row

def _issue_row(s,row,job,sheets,u):
    issue=PaperIssue(job_id=job.id,lot_id=row.lot_id,sheets=sheets,returned_sheets=0,
                     paper_snapshot=job.paper,issued_by=u.email)
    s.add(issue);s.flush();return issue

def issue(s,key,b,u):
    ref=s.get(PaperReservation,key)
    if not ref:raise HTTPException(404,'备纸单不存在')
    job=locked(s,PrintJob,ref.job_id)
    row=locked(s,PaperReservation,key)
    keys=dict(row.issue_keys or {})
    replay=keys.get(b.request_key)
    if replay:return {**pack(row),'issue':replay,'replayed':True}
    if job.status in ('hold','closed'):raise HTTPException(409,'停机或已结案工单不能领用留纸')
    if row.state!='held':raise HTTPException(409,'仅主管已确认留纸、尚有未领部分的备纸单可领用')
    lot=locked(s,PaperLot,row.lot_id)
    if lot.state!='active':raise HTTPException(409,'纸张批次已隔离，不能领用留纸')
    remaining=row.sheets-row.issued_sheets
    if remaining<=0:raise HTTPException(409,'备纸已全部领用，无可再领')
    if b.sheets>remaining:raise HTTPException(409,f'领用不得超过未领部分 {remaining} 张')
    row.issued_sheets+=b.sheets
    if row.issued_sheets==row.sheets:row.state='issued'
    issue=_issue_row(s,row,job,b.sheets,u)
    keys[b.request_key]={'issue_id':issue.id,'sheets':b.sheets,'at':now()};row.issue_keys=keys
    audit(s,u,f'备纸领用转出库 备纸单{row.id} {b.sheets}张（请求号{b.request_key}）');s.commit()
    return {**pack(row),'issue':pack(issue),'replayed':False}

def cancel(s,key,u,note=''):
    ref=s.get(PaperReservation,key)
    if not ref:raise HTTPException(404,'备纸单不存在')
    job=locked(s,PrintJob,ref.job_id);row=locked(s,PaperReservation,key)
    if row.state in ('cancelled','issued'):raise HTTPException(409,'备纸单已结束，不能撤单')
    unissued=row.sheets-row.issued_sheets
    released=0
    if row.state=='held' and unissued>0:
        lot=locked(s,PaperLot,row.lot_id);lot.available_sheets+=unissued;released=unissued
    elif row.state=='held' and unissued<=0:raise HTTPException(409,'备纸已全部领用，无可释放')
    row.released_sheets=released;row.state='cancelled';row.cancelled_by=u.email;row.cancelled_at=now()
    basis=dict(row.basis or {});basis['cancel_released_sheets']=released;basis['cancel_note']=note.strip()[:300];row.basis=basis
    audit(s,u,f'撤备纸单{row.id} 释放未领{released}张');s.commit();return row
