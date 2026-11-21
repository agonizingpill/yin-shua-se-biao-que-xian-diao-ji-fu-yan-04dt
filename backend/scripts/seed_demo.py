import random
from sqlalchemy import select,func
from src.db import Base,engine,Session
from src.models import User,PrintJob,ProofSheet,Adjustment,ReferenceSheet
from src.auth import hash_password
from src.production_models import PlateSet,PressSample,PressHold
from src.dispatch_models import PaperLot,PressMachine
from src.reservation_models import JobClosure

def seed():
    Base.metadata.create_all(engine)
    with Session()as s:
        for role in ('admin','pressman','viewer'):
            email=role+'@qianye.demo'
            if not s.scalar(select(User).where(User.email==email)):s.add(User(email=email,role=role,password_hash=hash_password('Press2026!')))
        for code,title,paper in [('PJ-26091','画册封套','157g 哑粉'),('PJ-26092','展览折页','128g 铜版')]:
            if not s.scalar(select(PrintJob).where(PrintJob.code==code)):s.add(PrintJob(code=code,title=title,paper=paper,target_density=1.4,status='setup'))
        s.flush();jobs=s.scalars(select(PrintJob).order_by(PrintJob.id)).all()
        for code,j,vals in [('PS-FIRST',0,[1.02,1.04,1.0,1.05,28]),('PS-RECHECK',0,[1.4,1.39,1.41,1.4,14]),('PS-FAIL',0,[1.01,1.0,1.03,1.05,29]),('PS-OTHER',1,[1.4,1.4,1.4,1.4,14]),('PS-OTHER-BAD',1,[1.7,1.1,1.55,1.4,15])]:
            if not s.scalar(select(ProofSheet).where(ProofSheet.code==code)):s.add(ProofSheet(code=code,job_id=jobs[j].id,density_c=vals[0],density_m=vals[1],density_y=vals[2],density_k=vals[3],dot_gain=vals[4]))
        for job in jobs:
            if not s.scalar(select(PlateSet).where(PlateSet.job_id==job.id,PlateSet.version=='V1')):s.add(PlateSet(job_id=job.id,version='V1',source_note='客户定稿PDF转四色印版，首版待上机测量'))
        rng=random.Random(42)
        for i in range(150):
            label=['合格','乳化','偏色'][i//50];means={'合格':[1.4,1.4,1.4,1.4,14],'乳化':[1.02,1.04,1.0,1.05,28],'偏色':[1.7,1.1,1.55,1.4,15]}[label]
            vals=[round(rng.gauss(mean,.028 if j<4 else 1),4)for j,mean in enumerate(means)];code=f'REF-{i+1:03}'
            if not s.scalar(select(ReferenceSheet).where(ReferenceSheet.code==code)):s.add(ReferenceSheet(code=code,density_c=vals[0],density_m=vals[1],density_y=vals[2],density_k=vals[3],dot_gain=vals[4],label=label))
        for code,gsm,qty in [('PAPER-157-A',157,20000),('PAPER-128-A',128,8000)]:
            if not s.scalar(select(PaperLot).where(PaperLot.code==code)):s.add(PaperLot(code=code,gsm=gsm,available_sheets=qty))
        if not s.scalar(select(PressMachine).where(PressMachine.code=='PRESS-04')):s.add(PressMachine(code='PRESS-04'))
        s.flush()
        demo=[('PJ-CL-157-01','157g 哑粉',1000,1028,'2026-09-02'),('PJ-CL-157-02','157g 哑粉',1500,1542,'2026-09-09'),('PJ-CL-157-03','157g 哑粉',2000,2074,'2026-09-16'),('PJ-CL-157-04','157g 哑粉',1200,1245,'2026-09-23'),('PJ-CL-157-05','157g 哑粉',1800,1841,'2026-09-30'),('PJ-CL-157-06','157g 哑粉',1600,1666,'2026-10-07'),('PJ-CL-128-01','128g 铜版',1000,1044,'2026-09-12'),('PJ-CL-128-02','128g 铜版',1400,1437,'2026-09-26')]
        for code,paper,planned,actual,day in demo:
            j=s.scalar(select(PrintJob).where(PrintJob.code==code))
            if not j:
                j=PrintJob(code=code,title='结案留档 '+code[-2:],paper=paper,target_density=1.4,status='closed');s.add(j);s.flush()
            if not s.scalar(select(JobClosure).where(JobClosure.job_id==j.id)):s.add(JobClosure(job_id=j.id,planned_sheets=planned,actual_sheets=actual,note='历史结案留档，含调机废纸',closed_by='admin@qianye.demo',closed_at=day+'T09:00:00+00:00'))
        s.commit();print({t.__tablename__:s.scalar(select(func.count()).select_from(t))for t in (User,PrintJob,ProofSheet,Adjustment,ReferenceSheet,JobClosure)})
if __name__=='__main__':seed()
