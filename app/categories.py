"""계정분류 정의 (엑셀 '계정분류' 컬럼과 동일한 체계)."""

REVENUE = "Ⅰ. 매출액"
COGS = "Ⅱ. 매출원가"
GROSS = "Ⅲ. 매출총이익(Ⅰ - Ⅱ)"
SGA = "Ⅳ. 판매비와 관리비"
OP = "Ⅴ. 영업손익(Ⅲ - Ⅳ)"
NET = "Ⅷ. 당기순손익(Ⅴ+Ⅵ-Ⅶ)"

SGA_ITEMS = [
    "① 인건비",
    "② 복리후생비",
    "③ 지급/용역수수료",
    "④ 광고선전비",
    "⑤ 임차/관리비",
    "⑥ 감가상각비",
    "⑦ 물류/운반비",
    "⑧ 연구개발비",
    "⑨ 기타판관비",
]

ASSETS = "자산총계"
LIAB = "부채총계"
EQUITY = "자본총계"
RETAINED = "이익잉여금"
INVENTORY = "재고자산"
NWC_PLUS = "순운전자본+"
NWC_MINUS = "순운전자본-"
ROU = "사용권자산"
LEASE = "리스부채"
CF_OP = "영업활동현금흐름"
CF_INV = "투자활동현금흐름"
CF_FIN = "재무활동현금흐름"
CF_NET = "현금의 증감"

IS_ITEMS = [REVENUE, COGS, GROSS, SGA, OP, NET]
BS_ITEMS = [ASSETS, LIAB, EQUITY, RETAINED, INVENTORY, NWC_PLUS, NWC_MINUS, ROU, LEASE]
CF_ITEMS = [CF_OP, CF_INV, CF_FIN, CF_NET]
ALL = IS_ITEMS + SGA_ITEMS + BS_ITEMS + CF_ITEMS

# 표시 순서 (기업분석 표)
STATEMENT_ORDER = [REVENUE, COGS, GROSS, SGA] + SGA_ITEMS + [OP, NET]

_NORMALIZE = {c.replace(" ", ""): c for c in ALL}


def normalize(name):
    """공백/NBSP 차이를 흡수해 표준 계정분류명으로 변환. 알 수 없으면 None."""
    if name is None:
        return None
    key = str(name).replace("\xa0", " ").replace(" ", "").strip()
    return _NORMALIZE.get(key)
