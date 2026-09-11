from dataclasses import dataclass, field
from typing import List, Optional

from .xianduan import XianDuanBase
from .zhongshu import ZhongShuForward, ZhongShuType


def _xianduan_high_price(xian_duan: XianDuanBase) -> float:
    return max(xian_duan.start_price, xian_duan.end_price)


def _xianduan_low_price(xian_duan: XianDuanBase) -> float:
    return min(xian_duan.start_price, xian_duan.end_price)


@dataclass
class XianDuanZhongShu:
    """由线段作为构件构成的中枢"""

    type: ZhongShuType = field(default=ZhongShuType.UNFINISHED)
    forward: ZhongShuForward = field(default=ZhongShuForward.MIDDLE)
    start_xianduan_idx: int = field(init=True, default=0)
    end_xianduan_idx: int = field(init=True, default=0)
    xian_duan_list: List[XianDuanBase] = field(init=True, default_factory=list, repr=False)
    start_idx: int = field(init=False, default=0)
    end_idx: int = field(init=False, default=0)
    start_time: str = field(init=False, default='')
    end_time: str = field(init=False, default='')
    start_price: float = field(init=False, default=0.0)
    end_price: float = field(init=False, default=0.0)
    high_price: float = field(init=False, default=0.0)
    low_price: float = field(init=False, default=0.0)

    def __post_init__(self):
        if not self.xian_duan_list:
            raise ValueError("线段中枢的xian_duan_list不能为空")
        xianduan_count = len(self.xian_duan_list)
        if not 0 <= self.start_xianduan_idx < xianduan_count:
            raise ValueError(
                f"线段中枢起始索引越界: start_xianduan_idx={self.start_xianduan_idx}, "
                f"xian_duan_list长度={xianduan_count}"
            )
        if not 0 <= self.end_xianduan_idx < xianduan_count:
            raise ValueError(
                f"线段中枢结束索引越界: end_xianduan_idx={self.end_xianduan_idx}, "
                f"xian_duan_list长度={xianduan_count}"
            )
        if self.start_xianduan_idx > self.end_xianduan_idx:
            raise ValueError(
                f"线段中枢区间无效: {self.start_xianduan_idx=} > {self.end_xianduan_idx=}"
            )

        first_xian_duan = self.xian_duan_list[self.start_xianduan_idx]
        last_xian_duan = self.xian_duan_list[self.end_xianduan_idx]
        if first_xian_duan.xianduan_type is None or last_xian_duan.xianduan_type is None:
            raise ValueError("线段中枢包含方向未知的线段")

        self.start_idx = first_xian_duan.start_idx
        self.end_idx = last_xian_duan.end_idx
        self.start_time = first_xian_duan.start_time
        self.end_time = last_xian_duan.end_time
        self.start_price = first_xian_duan.start_price
        self.end_price = last_xian_duan.end_price

        # 和笔中枢一致：第一段与第三段的价格重叠区间就是中枢区间。
        third_xian_duan = self.xian_duan_list[self.end_xianduan_idx]
        self.high_price = min(
            _xianduan_high_price(first_xian_duan),
            _xianduan_high_price(third_xian_duan),
        )
        self.low_price = max(
            _xianduan_low_price(first_xian_duan),
            _xianduan_low_price(third_xian_duan),
        )
        if self.high_price < self.low_price:
            raise ValueError(
                f"线段中枢上下沿无效: low_price={self.low_price} > high_price={self.high_price}"
            )

        # 构件方向交替时，中枢方向由进入段方向决定；这里的命名与笔中枢保持一致。
        if first_xian_duan.is_up():
            self.forward = ZhongShuForward.DOWN
        else:
            self.forward = ZhongShuForward.UP

    @property
    def is_finished(self) -> bool:
        return self.type == ZhongShuType.FINISHED

    def set_finished(self):
        self.type = ZhongShuType.FINISHED

    def is_up(self) -> bool:
        return self.forward == ZhongShuForward.UP

    def is_down(self) -> bool:
        return self.forward == ZhongShuForward.DOWN

    def valid_finished(self) -> bool:
        first_xian_duan = self.xian_duan_list[self.start_xianduan_idx]
        last_xian_duan = self.xian_duan_list[self.end_xianduan_idx]
        return first_xian_duan.is_up() == last_xian_duan.is_up()

    def is_in_zhongshu(self, high_price: float, low_price: float) -> bool:
        return self.low_price <= high_price and self.high_price >= low_price

    def extend(self, new_xian_duan: XianDuanBase) -> bool:
        """向后延伸线段中枢边界；重复传入当前末端线段时不修改状态。"""
        if new_xian_duan.idx < self.end_xianduan_idx:
            raise ValueError(
                f"线段中枢只能向后延伸: end_xianduan_idx={self.end_xianduan_idx}, "
                f"new_xian_duan.idx={new_xian_duan.idx}"
            )
        if new_xian_duan.idx == self.end_xianduan_idx:
            return False

        self.end_xianduan_idx = new_xian_duan.idx
        self.end_idx = new_xian_duan.end_idx
        self.end_time = new_xian_duan.end_time
        self.end_price = new_xian_duan.end_price
        return True

    def zhongshu_length(self) -> int:
        return self.end_xianduan_idx - self.start_xianduan_idx + 1

    def to_dict(self) -> dict:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "direction": "up" if self.is_up() else "down",
        }


def generate_zhongshu_from_xianduan(
    xian_duan_list: List[XianDuanBase],
    xianduan_idx_start: Optional[int] = None,
    xianduan_idx_end: Optional[int] = None,
) -> List[XianDuanZhongShu]:
    """以线段为构件生成中枢，判定方式与 generate_zhongshu_from_bi 一致。"""
    if not xian_duan_list:
        return []
    if xianduan_idx_start is not None and xianduan_idx_start < 0:
        raise ValueError(f"xianduan_idx_start不能为负数: {xianduan_idx_start}")
    if xianduan_idx_end is not None and xianduan_idx_end < 0:
        raise ValueError(f"xianduan_idx_end不能为负数: {xianduan_idx_end}")
    if xianduan_idx_end is not None and xianduan_idx_end >= len(xian_duan_list):
        raise ValueError(
            f"xianduan_idx_end越界: xianduan_idx_end={xianduan_idx_end}, "
            f"xian_duan_list长度={len(xian_duan_list)}"
        )
    if (
        xianduan_idx_start is not None
        and xianduan_idx_end is not None
        and xianduan_idx_start > xianduan_idx_end
    ):
        raise ValueError(
            f"线段区间无效: {xianduan_idx_start=} > {xianduan_idx_end=}"
        )

    zhongshu_list: List[XianDuanZhongShu] = []
    last_zhongshu: Optional[XianDuanZhongShu] = None

    for idx in range(4, len(xian_duan_list)):
        if len(zhongshu_list) > 0:
            last_zhongshu = zhongshu_list[-1]

        entry_xian_duan = xian_duan_list[idx - 4]
        first_xian_duan = xian_duan_list[idx - 3]
        third_xian_duan = xian_duan_list[idx - 1]
        exit_xian_duan = xian_duan_list[idx]

        if xianduan_idx_start is not None and idx - 3 < xianduan_idx_start:
            continue
        if xianduan_idx_end is not None and idx - 1 > xianduan_idx_end:
            break

        zhongshu_high_price = min(
            _xianduan_high_price(first_xian_duan),
            _xianduan_high_price(third_xian_duan),
        )
        zhongshu_low_price = max(
            _xianduan_low_price(first_xian_duan),
            _xianduan_low_price(third_xian_duan),
        )

        if last_zhongshu is None or (
            last_zhongshu.is_finished
            and entry_xian_duan.start_time >= last_zhongshu.end_time
        ):
            if (
                _xianduan_high_price(exit_xian_duan) >= zhongshu_low_price
                and _xianduan_low_price(exit_xian_duan) <= zhongshu_high_price
            ):
                zhongshu = XianDuanZhongShu(
                    start_xianduan_idx=idx - 3,
                    end_xianduan_idx=idx - 1,
                    xian_duan_list=xian_duan_list,
                )

                if (
                    zhongshu.is_up()
                    and entry_xian_duan.is_up()
                    and _xianduan_low_price(entry_xian_duan) < zhongshu.low_price
                ) or (
                    zhongshu.is_down()
                    and entry_xian_duan.is_down()
                    and _xianduan_high_price(entry_xian_duan) > zhongshu.high_price
                ):
                    zhongshu_list.append(zhongshu)
                continue

        if last_zhongshu is None or last_zhongshu.is_finished:
            continue

        if not last_zhongshu.is_in_zhongshu(
            _xianduan_high_price(exit_xian_duan),
            _xianduan_low_price(exit_xian_duan),
        ):
            last_zhongshu.extend(xian_duan_list[idx - 2])
            last_zhongshu.set_finished()

    if last_zhongshu is not None and not last_zhongshu.is_finished:
        last_xian_duan = xian_duan_list[-1]
        if xianduan_idx_end is not None:
            last_xian_duan = xian_duan_list[xianduan_idx_end]
        last_zhongshu.extend(last_xian_duan)
        last_zhongshu.set_finished()

    return zhongshu_list
