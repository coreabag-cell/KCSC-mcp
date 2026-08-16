"""
KCSC (국가건설기준센터) OpenAPI -> MCP 래퍼 서버 (다중 사용자 지원 버전)

국가건설기준센터(https://www.kcsc.re.kr)가 제공하는 건설기준코드(KDS/KCS) OpenAPI를
Model Context Protocol(MCP) 도구로 감싸서 Claude 커스텀 커넥터에서 사용할 수 있게 합니다.

배포: Render (Web Service, Python)
전송 방식: Streamable HTTP (원격 MCP 서버 표준)

인증 방식 [중요 — 이전 버전과 다름]
------------------------------------
이 서버는 인증키를 환경변수에 저장하지 않습니다. 대신 Claude 커스텀 커넥터에
등록하는 URL 자체에 각자의 인증키를 쿼리파라미터로 붙입니다:

    https://<서비스이름>.onrender.com/mcp?api_key=본인이_발급받은_KCSC_인증키

이렇게 하면 여러 명(다른 관리사무소장님 등)이 서버 하나를 같이 쓰면서도,
각자 자기 인증키로 호출됩니다. 서버의 base URL(?api_key= 없는 부분)만
공개해도 안전합니다 — api_key가 없으면 아무 것도 조회할 수 없습니다.

필요 사전 준비:
1. https://www.kcsc.re.kr 접속 -> 정보제공 > API 서비스 > 인증키 발급신청
2. 발급받은 키를 커넥터 등록 URL의 ?api_key= 뒤에 붙여서 사용
"""

import os
import httpx
from mcp.server.fastmcp import FastMCP, Context

BASE_URL = "https://kcsc.re.kr/OpenApi"
PORT = int(os.environ.get("PORT", 8000))
VALID_DOC_TYPES = {"KDS", "KCS"}

mcp = FastMCP(
    name="kcsc-construction-code",
    stateless_http=True,  # Render 등 서버리스/오토스케일 환경에 적합
    host="0.0.0.0",
    port=PORT,
)


def _get_api_key(ctx: Context) -> str | None:
    """현재 요청 URL의 ?api_key= 쿼리파라미터에서 인증키를 읽어옵니다."""
    req = ctx.request_context.request
    if req is None:
        return None
    return req.query_params.get("api_key")


def _missing_key_message() -> str:
    return (
        "이 요청에 api_key가 없습니다. Claude 커스텀 커넥터 등록 시 URL을 "
        "'https://<서비스이름>.onrender.com/mcp?api_key=본인의_KCSC_인증키' 형태로 "
        "입력했는지 확인해주세요. 인증키는 https://www.kcsc.re.kr 에서 발급받을 수 있습니다."
    )


async def _call_kcsc_api(endpoint: str, doc_type: str, code: str, api_key: str) -> str:
    """KCSC OpenAPI를 호출합니다.

    실제 엔드포인트는 Type/Code를 쿼리파라미터가 아니라 URL 경로에 받고
    (예: /OpenApi/CodeViewer/KCS/114010), 인증키는 소문자 'key' 쿼리파라미터로
    받습니다 (kcsc.re.kr 공식 API 문서의 예시 URL 기준). 과거 버전은 Type/Code/Key를
    모두 대문자 쿼리파라미터로 보내서 CodeList는 400(필수 파라미터 'key' 누락),
    CodeViewer는 라우팅이 맞지 않아 빈 응답을 받았습니다.
    """
    doc_type_upper = doc_type.upper()
    if doc_type_upper not in VALID_DOC_TYPES:
        return f"doc_type은 'KDS' 또는 'KCS'만 가능합니다 (입력값: '{doc_type}')."
    if not code or not code.strip():
        return "code 파라미터가 비어 있습니다. 조회할 코드 번호를 입력해주세요."

    url = f"{BASE_URL}/{endpoint}/{doc_type_upper}/{code.strip()}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(url, params={"key": api_key})
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return (
                f"KCSC API 오류 (status {e.response.status_code}, "
                f"url={url}): {e.response.text[:500]}"
            )
        except httpx.RequestError as e:
            return f"KCSC API 요청 실패 ({url}): {e}"

    if not resp.text.strip():
        return (
            f"KCSC API가 빈 응답을 반환했습니다 (Type={doc_type_upper}, Code={code}). "
            "다음을 확인해보세요: "
            "1) kcsc.re.kr 마이페이지에서 인증키가 '승인완료' 상태인지, "
            "2) 코드 번호가 실제 존재하는 코드인지 (오탈자·자릿수 확인), "
            "3) 대분류만 아는 경우 정확한 세부 코드(fullCode)를 먼저 확인했는지."
        )
    return resp.text


@mcp.tool()
async def list_construction_codes(doc_type: str, code: str, ctx: Context) -> str:
    """국가건설기준(KDS/KCS) 코드 목록 및 메타정보를 조회합니다.

    특정 코드 하위의 목록(예: 대분류 코드를 넣으면 그 아래 세부 코드들)을 확인하거나,
    특정 코드가 실제 존재하는지, 최신 개정연도(version)가 언제인지 확인할 때 사용합니다.

    Args:
        doc_type: 문서 타입. "KDS"(설계기준) 또는 "KCS"(표준시방서) 중 하나.
        code: 조회할 코드 번호. 예: "101000" (대분류), "142010" (콘크리트공사 세부코드 등)
              전체 대분류 목록을 보려면 상위 자릿수만 입력합니다.
    """
    api_key = _get_api_key(ctx)
    if not api_key:
        return _missing_key_message()

    return await _call_kcsc_api("CodeList", doc_type, code, api_key)


@mcp.tool()
async def get_construction_code_detail(doc_type: str, code: str, ctx: Context) -> str:
    """특정 국가건설기준(KDS/KCS) 코드의 본문 전체 내용을 조회합니다.

    코드 번호를 정확히 알고 있을 때, 해당 기준/시방서의 실제 조문 내용을 가져옵니다.
    코드 번호를 모른다면 먼저 list_construction_codes로 검색한 뒤 이 도구를 사용하세요.

    Args:
        doc_type: 문서 타입. "KDS"(설계기준) 또는 "KCS"(표준시방서) 중 하나.
        code: 조회할 정확한 코드 번호 (fullCode). 예: "142010"
    """
    api_key = _get_api_key(ctx)
    if not api_key:
        return _missing_key_message()

    return await _call_kcsc_api("CodeViewer", doc_type, code, api_key)


# Render는 PORT 환경변수로 바인딩할 포트를 지정합니다 (위 FastMCP 생성자에서 반영됨).
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
