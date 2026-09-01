from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Union
from enum import Enum
import numpy as np

from .bi import BiBase


class ZhongShuType(int, Enum):
    """笔的类型"""
    UNFINISHED = 1  # 未完成
    FINISHED = 2  # 完成


class ZhongShuForward(int, Enum):
    """笔的类型"""
    MIDDLE = 0  # 没方向
    UP = 1  # 向上中枢
    DOWN = 2  # 向下中暑


@dataclass
class ZhongShuBase:
    "“”中枢“”"
    type: ZhongShuType = field(default=ZhongShuType.UNFINISHED)
    forward: ZhongShuForward = field(default=ZhongShuForward.MIDDLE)
    start_bi_idx: int = field(init=True, default=0)  # 中枢起始位置的笔索引
    end_bi_idx: int = field(init=True, default=0)  # 中枢结束位置的笔索引
    bi_list: List[BiBase] = field(init=True, default_factory=list, repr=False)
    start_idx: int = field(init=False, default=0)  # 中枢起始位置的K 线索引
    end_idx: int = field(init=False, default=0)  # 中枢结束位置的K 线索引
    start_time: str = field(init=False, default='')  # 起始时间
    end_time: str = field(init=False, default='')  # 结束时间
    high_price: float = field(init=False, default=0.0)  # 中暑上沿
    low_price: float = field(init=False, default=0.0)  # 中枢下沿

    def __post_init__(self):
        self.start_idx = self.bi_list[self.start_bi_idx].start_idx
        self.end_idx = self.bi_list[self.end_bi_idx].end_idx
        self.start_time = self.bi_list[self.start_bi_idx].start_time
        self.end_time = self.bi_list[self.end_bi_idx].end_time

        if self.bi_list[self.start_bi_idx].is_up():
            self.forward = ZhongShuForward.DOWN
            self.high_price = self.bi_list[self.end_bi_idx].high_price
            self.low_price = self.bi_list[self.start_bi_idx].low_price
        else:
            self.forward = ZhongShuForward.UP
            self.high_price = self.bi_list[self.start_bi_idx].high_price
            self.low_price = self.bi_list[self.end_bi_idx].low_price

    @property
    def is_finished(self):
        return self.type == ZhongShuType.FINISHED

    def set_finished(self):
        self.type = ZhongShuType.FINISHED

    def is_up(self):
        """是否为向上中枢"""
        return self.forward == ZhongShuForward.UP

    def is_down(self):
        """是否为向下中枢"""
        return self.forward == ZhongShuForward.DOWN

    def valid_finished(self):
        return self.bi_list[self.start_bi_idx].is_up() == self.bi_list[self.end_bi_idx].is_up()

    def extend(self, new_bi: BiBase):
        if self.end_bi_idx != new_bi.idx:
            self.end_bi_idx = new_bi.idx
            self.end_idx = new_bi.end_idx
            self.end_time = new_bi.end_time

    def bi_length(self) -> int:
        return self.end_bi_idx - self.start_bi_idx


def generate_zhongshu_from_bi(bi_list: List[BiBase]) -> List[ZhongShuBase]:
    zhongshu_list: List[ZhongShuBase] = []
    last_zhongshu: Optional[ZhongShuBase] = None

    for idx, bi in enumerate(bi_list):

        if idx < 4:
            continue

        if len(zhongshu_list) > 0:
            last_zhongshu = zhongshu_list[-1]

        # 中枢进入段
        tmp_zhongshu_entry_bi = bi_list[idx - 4]
        tmp_zhongshu_first_bi = bi_list[idx - 3]
        tmp_zhongshu_third_bi = bi_list[idx - 1]
        if last_zhongshu is None or (
                last_zhongshu.is_finished and tmp_zhongshu_entry_bi.start_time >= last_zhongshu.end_time):
            if (
                    tmp_zhongshu_first_bi.is_down() and tmp_zhongshu_third_bi.is_down() and tmp_zhongshu_first_bi.high_price >= tmp_zhongshu_third_bi.low_price
            ) or (
                    tmp_zhongshu_first_bi.is_up() and tmp_zhongshu_third_bi.is_up() and tmp_zhongshu_first_bi.low_price <= tmp_zhongshu_third_bi.high_price):

                zhongshu = ZhongShuBase(start_bi_idx=tmp_zhongshu_first_bi.idx, end_bi_idx=tmp_zhongshu_third_bi.idx,
                                        bi_list=bi_list)

                if (
                        zhongshu.is_up() and tmp_zhongshu_entry_bi.is_up() and tmp_zhongshu_entry_bi.low_price < zhongshu.low_price) or (
                        zhongshu.is_down() and tmp_zhongshu_entry_bi.is_down() and tmp_zhongshu_entry_bi.high_price > zhongshu.high_price):
                    zhongshu_list.append(zhongshu)
                continue

        # 前一个中枢未完成时
        if last_zhongshu is None:
            continue
        if last_zhongshu.is_finished:
            continue
        if last_zhongshu.low_price  <= bi.high_price  and last_zhongshu.high_price  >= bi.low_price :
            continue
        else:

            last_zhongshu.extend(bi_list[idx - 2])
            last_zhongshu.set_finished()
            print(last_zhongshu)
            zhongshu_list[-1] = last_zhongshu

    print(f"{len(zhongshu_list)=}")
    return zhongshu_list
