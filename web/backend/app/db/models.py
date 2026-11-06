from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from CLPainter.web.backend.app.db.base import Base


class Instrument(Base):
    """图表标的元数据。"""

    __tablename__ = "instrument"
    __table_args__ = (
        UniqueConstraint("market", "asset_class", "code", name="uq_instrument_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    price_precision: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delist_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class WatchlistBoard(Base):
    """用户自选板块。"""

    __tablename__ = "watchlist_board"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    instruments: Mapped[list["Instrument"]] = relationship(
        secondary="watchlist_item",
        order_by="watchlist_item.c.sort_order",
        viewonly=True,
    )


class WatchlistItem(Base):
    """自选板块内的标的关联。"""

    __tablename__ = "watchlist_item"
    __table_args__ = (
        UniqueConstraint("board_id", "instrument_id", name="uq_watchlist_item"),
        Index("ix_watchlist_item_board_order", "board_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    board_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("watchlist_board.id", ondelete="CASCADE"),
        nullable=False,
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("instrument.id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )


class ClStateSnapshot(Base):
    """缠论状态快照宽表。"""

    __tablename__ = "cl_state_snapshot"
    __table_args__ = (
        UniqueConstraint("instrument_id", "frequency", "scope", name="uq_cl_state_snapshot_identity"),
        Index("ix_cl_state_snapshot_filter", "frequency", "scope", "relative_pivot_position"),
        CheckConstraint("relative_pivot_position IN (0, 1, 2, 3)", name="ck_cl_state_snapshot_position"),
        CheckConstraint(
            "relative_previous_pivot_position IN (0, 1, 2, 3)",
            name="ck_cl_state_snapshot_previous_position",
        ),
        CheckConstraint(
            "last_structure_right_type IN (0, 1, 2)",
            name="ck_cl_state_snapshot_right_structure",
        ),
        CheckConstraint(
            "second_point_type IN (0, 1, 2)",
            name="ck_cl_state_snapshot_second_point",
        ),
        CheckConstraint(
            "third_point_type IN (0, 1, 2)",
            name="ck_cl_state_snapshot_third_point",
        ),
        CheckConstraint(
            "quasi_third_point_type IN (0, 1, 2)",
            name="ck_cl_state_snapshot_quasi_third_point",
        ),
        {"comment": "缠论笔/线段状态快照宽表，每个标的、周期、构件一行"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="快照行主键",
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("instrument.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联 instrument.id；标的删除时级联删除",
    )
    frequency: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="K 线周期，如 1day、60min",
    )
    scope: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="状态构件类型：bi=笔，xianduan=线段",
    )
    relative_pivot_position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="相对当前趋势最后一个中枢的位置：0=无中枢，1=中枢内，2=中枢下，3=中枢上；NULL=未计算",
    )
    relative_previous_pivot_position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="相对前一趋势最后一个扩展中枢的位置：0=无扩展中枢，1=中枢内，2=中枢下，3=中枢上；NULL=未计算",
    )
    last_structure_right_type: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="当前 scope 最后一个构件的右侧类型：NULL=无法判断，0=无分型（fake），1=底分型，2=顶分型",
    )
    second_point_type: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="最后一笔的二买/二卖类型：NULL=无法判断，0=都不是，1=二买，2=二卖",
    )
    third_point_type: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="最后一笔的三买/三卖类型：NULL=无法判断，0=都不是，1=三买，2=三卖",
    )
    quasi_third_point_type: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="最后一笔的类三买/类三卖类型：NULL=无法判断，0=都不是，1=类三买，2=类三卖",
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        comment="快照写入时间",
    )
    instrument: Mapped[Instrument] = relationship(foreign_keys=[instrument_id])

    @property
    def relative_pivot_position_name(self) -> str | None:
        return {
            0: "none",
            1: "inside",
            2: "below",
            3: "above",
        }.get(self.relative_pivot_position)

    @property
    def relative_previous_pivot_position_name(self) -> str | None:
        return {
            0: "none",
            1: "inside",
            2: "below",
            3: "above",
        }.get(self.relative_previous_pivot_position)
