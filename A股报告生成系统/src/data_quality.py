"""Data quality checks for report generation inputs."""

from dataclasses import asdict, dataclass, field
from typing import Dict, List


MISSING_TEXT_VALUES = {"", "N/A", "未分类", "相关信息暂未披露", "暂无最新新闻"}


@dataclass
class DataQualityResult:
    """Describe whether a report can be generated and which inputs degraded."""

    status: str
    score: int
    critical_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def can_generate(self) -> bool:
        return not self.critical_errors

    def to_dict(self) -> Dict:
        return asdict(self)


def _is_missing(value) -> bool:
    if value is None:
        return True
    try:
        if value != value:
            return True
    except Exception:
        pass
    return str(value).strip() in MISSING_TEXT_VALUES


def evaluate_data_quality(stock_data: Dict) -> DataQualityResult:
    """Evaluate the minimum evidence needed for a usable report."""
    critical_errors: List[str] = []
    warnings: List[str] = []

    historical = stock_data.get("historical_financial") or {}
    if not historical:
        critical_errors.append("缺少历史财务数据")
    else:
        comparable_periods = sum(
            1
            for period in historical.values()
            if period.get("revenue_yoy") is not None
            or period.get("net_profit_yoy") is not None
        )
        if comparable_periods == 0:
            warnings.append("缺少可进行同报告期同比的财务数据")

    if _is_missing(stock_data.get("stock_name")):
        warnings.append("缺少公司简称")
    if _is_missing(stock_data.get("industry")):
        warnings.append("缺少所属行业")
    if _is_missing(stock_data.get("main_business")):
        warnings.append("缺少主营业务")

    quote_fields = ("current_price", "pe_ratio", "pb_ratio", "market_cap")
    if all(_is_missing(stock_data.get(field)) for field in quote_fields):
        warnings.append("实时行情与估值数据不可用")

    score = max(0, 100 - len(critical_errors) * 60 - len(warnings) * 10)
    if critical_errors:
        status = "failed"
    elif warnings:
        status = "degraded"
    else:
        status = "passed"

    return DataQualityResult(
        status=status,
        score=score,
        critical_errors=critical_errors,
        warnings=warnings,
    )
