"""
多维度筛选器 — 按标准编号、名称、领域、文档状态筛选
"""

from typing import Optional
from database.operations import get_distinct_fields


def build_search_filters(
    standard_number: Optional[str] = None,
    standard_name: Optional[str] = None,
    applicable_field: Optional[str] = None,
    doc_status: Optional[str] = None,
    doc_ids: Optional[list] = None,
) -> dict:
    """构建检索过滤条件"""
    filters = {}

    if standard_number and standard_number.strip():
        filters["standard_number"] = standard_number.strip()
    if standard_name and standard_name.strip():
        filters["standard_name"] = standard_name.strip()
    if applicable_field and applicable_field.strip() and applicable_field != "全部":
        filters["applicable_field"] = applicable_field.strip()
    if doc_status and doc_status.strip() and doc_status != "全部":
        filters["doc_status"] = doc_status.strip()
    if doc_ids:
        filters["doc_ids"] = doc_ids

    return filters if filters else None


def get_filter_options() -> dict:
    """获取前端筛选器的选项数据"""
    fields = get_distinct_fields()

    return {
        "fields": fields if fields else ["通用"],
        "statuses": ["全部", "现行有效", "修订中", "废止"],
    }
