from sqlalchemy import String,ForeignKey,JSON,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
class JobClosure(Base):
    """已结案开机单的用量留档：计划印量与实际耗纸，是新备纸估算的唯一样本来源。"""
    __tablename__='job_closures'
    __table_args__=(CheckConstraint('planned_sheets>0 AND actual_sheets>0'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    job_id:Mapped[int]=mapped_column(ForeignKey('print_jobs.id'),unique=True)
    planned_sheets:Mapped[int]=mapped_column()
    actual_sheets:Mapped[int]=mapped_column()
    note:Mapped[str]=mapped_column(String(300),default='')
    late_reports:Mapped[list]=mapped_column(JSON,default=list)
    closed_by:Mapped[str]=mapped_column(String(100))
    closed_at:Mapped[str]=mapped_column(String(40))
class PaperReservation(Base):
    """临开机备纸单。basis 在建立时冻结，晚报用量之后也不回写旧单。"""
    __tablename__='paper_reservations'
    __table_args__=(CheckConstraint('sheets>0 AND issued_sheets>=0 AND issued_sheets<=sheets AND released_sheets>=0'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    job_id:Mapped[int]=mapped_column(ForeignKey('print_jobs.id'))
    lot_id:Mapped[int]=mapped_column(ForeignKey('paper_lots.id'))
    sheets:Mapped[int]=mapped_column()
    issued_sheets:Mapped[int]=mapped_column(default=0)
    released_sheets:Mapped[int]=mapped_column(default=0)
    state:Mapped[str]=mapped_column(String(24),default='draft')
    basis:Mapped[dict]=mapped_column(JSON)
    issue_keys:Mapped[dict]=mapped_column(JSON,default=dict)
    note:Mapped[str]=mapped_column(String(300),default='')
    created_by:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[str]=mapped_column(String(40))
    confirmed_by:Mapped[str]=mapped_column(String(100),default='')
    confirmed_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    cancelled_by:Mapped[str]=mapped_column(String(100),default='')
    cancelled_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
