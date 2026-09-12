from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from .tezhengxulie import TeZhengXuLieCategory, TeZhengXuLieType

if TYPE_CHECKING:
    from .xianduan import XianDuanBase


@dataclass
class XianduanTeZhengXuLie:
    """线段特征序列"""

    type: TeZhengXuLieType = field(default=TeZhengXuLieType.DING)
    category: TeZhengXuLieCategory = field(default=TeZhengXuLieCategory.First)
    xian_duan_list: List["XianDuanBase"] = field(default_factory=list, repr=False)
    xian_duan_idx_list: List[int] = field(default_factory=list)

    idx: Optional[int] = None

    def __post_init__(self):
        if len(self.xian_duan_list) != 3:
            raise ValueError(f"特征序列必须包含三条线段: {len(self.xian_duan_list)=}")
        if len(self.xian_duan_idx_list) != 3:
            raise ValueError(f"特征序列索引必须包含三项: {len(self.xian_duan_idx_list)=}")

    @property
    def left_xian_duan(self) -> "XianDuanBase":
        return self.xian_duan_list[0]

    @property
    def mid_xian_duan(self) -> "XianDuanBase":
        return self.xian_duan_list[1]

    @property
    def right_xian_duan(self) -> "XianDuanBase":
        return self.xian_duan_list[2]

    @property
    def mid_idx(self) -> int:
        return self.mid_xian_duan.start_idx

    def is_first_category(self) -> bool:
        return self.category == TeZhengXuLieCategory.First

    def is_second_category(self) -> bool:
        return self.category == TeZhengXuLieCategory.Second

    @property
    def left_xian_duan_idx(self) -> int:
        return self.xian_duan_idx_list[0]

    @property
    def mid_xian_duan_idx(self) -> int:
        return self.xian_duan_idx_list[1]

    @property
    def right_xian_duan_idx(self) -> int:
        return self.xian_duan_idx_list[2]

    def is_top(self) -> bool:
        return self.type == TeZhengXuLieType.DING

    def is_bottom(self) -> bool:
        return self.type == TeZhengXuLieType.DI

    @property
    def start_idx(self) -> int:
        return self.mid_xian_duan.start_idx

    @property
    def start_time(self) -> str:
        return self.mid_xian_duan.start_time

    @property
    def start_price(self) -> float:
        return self.mid_xian_duan.start_price

    @property
    def high_price(self) -> float:
        return max(self.mid_xian_duan.start_price, self.mid_xian_duan.end_price)

    @property
    def low_price(self) -> float:
        return min(self.mid_xian_duan.start_price, self.mid_xian_duan.end_price)


def _find_confirmation(
        xian_duan_list: List["XianDuanBase"],
        mid_idx: int,
        is_bottom: bool,
) -> Optional[int]:
    total = len(xian_duan_list)
    mid_xian_duan = xian_duan_list[mid_idx]
    if is_bottom:
        merged_low = mid_xian_duan.start_price
        merged_high = mid_xian_duan.end_price
    else:
        merged_high = mid_xian_duan.start_price
        merged_low = mid_xian_duan.end_price

    right_idx = mid_idx + 2
    while right_idx < total:
        start_price = xian_duan_list[right_idx].start_price
        end_price = xian_duan_list[right_idx].end_price
        if is_bottom:
            separated = start_price < merged_low
            confirmed = start_price > merged_low and end_price > merged_high
        else:
            separated = start_price > merged_high
            confirmed = start_price < merged_high and end_price < merged_low

        if separated:
            return None
        if confirmed:
            return right_idx

        contained = (
                            start_price >= merged_low and end_price <= merged_high
                    ) or (
                            start_price <= merged_low and end_price >= merged_high
                    )
        if not contained:
            raise ValueError(
                f"意外的线段: {mid_idx=} {right_idx=} "
                f"{merged_low=} {merged_high=} {start_price=} {end_price=}"
            )

        if is_bottom:
            merged_high = min(merged_high, end_price)
            merged_low = min(merged_low, start_price)
        else:
            merged_high = max(merged_high, start_price)
            merged_low = max(merged_low, end_price)

        right_idx += 2

    return None


def _validate_xian_duan_list(xian_duan_list: List["XianDuanBase"]) -> None:
    for idx, xian_duan in enumerate(xian_duan_list):
        if not xian_duan.is_up() and not xian_duan.is_down():
            raise ValueError(f"线段方向无效: {idx=}")
    for left_idx, (left_xian_duan, right_xian_duan) in enumerate(
            zip(xian_duan_list, xian_duan_list[1:])
    ):
        if left_xian_duan.is_up() == right_xian_duan.is_up():
            raise ValueError(f"线段方向不交替: {left_idx=}")


def _is_more_extreme(
        old_item: XianduanTeZhengXuLie,
        new_item: XianduanTeZhengXuLie,
) -> bool:
    if old_item.is_top():
        return new_item.high_price > old_item.high_price
    return new_item.low_price < old_item.low_price


def generate_xianduan_tezheng_xu_lie(
        xian_duan_list: List["XianDuanBase"],
) -> List[XianduanTeZhengXuLie]:
    """以线段为构件生成特征序列。"""
    if len(xian_duan_list) < 3:
        return []
    _validate_xian_duan_list(xian_duan_list)
    result: List[XianduanTeZhengXuLie] = []
    total = len(xian_duan_list)
    for mid_idx in range(2, total - 2):
        left_xian_duan = xian_duan_list[mid_idx - 2]
        mid_xian_duan = xian_duan_list[mid_idx]
        is_bottom = mid_xian_duan.is_up()

        if is_bottom:
            if mid_xian_duan.start_price >= left_xian_duan.start_price:
                continue
        else:
            if mid_xian_duan.start_price <= left_xian_duan.start_price:
                continue

        right_idx = _find_confirmation(xian_duan_list, mid_idx, is_bottom)
        if right_idx is None:
            continue

        if is_bottom:
            is_second_category = (
                    mid_xian_duan.end_price < left_xian_duan.start_price
            )
            sequence_type = TeZhengXuLieType.DI
        else:
            is_second_category = (
                    mid_xian_duan.end_price > left_xian_duan.start_price
            )
            sequence_type = TeZhengXuLieType.DING

        result.append(
            XianduanTeZhengXuLie(
                type=sequence_type,
                category=(
                    TeZhengXuLieCategory.Second
                    if is_second_category
                    else TeZhengXuLieCategory.First
                ),
                xian_duan_list=[
                    left_xian_duan,
                    mid_xian_duan,
                    xian_duan_list[right_idx],
                ],
                xian_duan_idx_list=[mid_idx - 2, mid_idx, right_idx],
            )
        )

    filtered_result: List[XianduanTeZhengXuLie] = []
    for item in result:
        if filtered_result and filtered_result[-1].is_top() == item.is_top():
            if _is_more_extreme(filtered_result[-1], item):
                filtered_result[-1] = item
        else:
            filtered_result.append(item)
    for sequence_idx, item in enumerate(filtered_result):
        item.idx = sequence_idx
    return filtered_result
