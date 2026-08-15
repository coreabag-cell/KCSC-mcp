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

    params = {"Type": doc_type.upper(), "Code": code, "Key": api_key}
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/CodeList", params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return f"KCSC API 오류 (status {e.response.status_code}): {e.response.text[:500]}"
        except httpx.RequestError as e:
            return f"KCSC API 요청 실패: {e}"

    return resp.text


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

    params = {"Type": doc_type.upper(), "Code": code, "Key": api_key}
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/CodeViewer", params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return f"KCSC API 오류 (status {e.response.status_code}): {e.response.text[:500]}"
        except httpx.RequestError as e:
            return f"KCSC API 요청 실패: {e}"

    return resp.text


# Render는 PORT 환경변수로 바인딩할 포트를 지정합니다 (위 FastMCP 생성자에서 반영됨).
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
