# kcsc-mcp — 국가건설기준(KDS/KCS) OpenAPI → MCP 래퍼 서버

국가건설기준센터(KCSC, https://www.kcsc.re.kr) 의 건설기준코드 OpenAPI를
Claude 커스텀 커넥터에서 바로 조회할 수 있도록 감싼 원격 MCP 서버입니다.

## 제공 도구 (Tools)

| 도구 | 설명 |
|---|---|
| `list_construction_codes` | KDS/KCS 코드 목록·메타정보(개정연도 등) 조회 |
| `get_construction_code_detail` | 특정 코드의 본문(조문) 전체 내용 조회 |

## 1단계 — KCSC 인증키 발급

1. https://www.kcsc.re.kr 접속
2. 정보제공 → API 서비스 → 인증키 발급신청
3. 승인 후 발급되는 키를 복사해둡니다 (예: `bdf239cd309cc876293ff3` 형식)

## 2단계 — Render에 배포

1. 이 폴더(`server.py`, `requirements.txt`)를 새 GitHub 레포로 푸시
   (기존 `kapt-contract-mcp`처럼 GitHub 연동 방식을 그대로 쓰시면 됩니다)
2. Render 대시보드 → New → Web Service → 방금 만든 레포 선택
3. 설정값:
   - **Language**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python server.py`
4. **환경변수는 필요 없습니다** — 이 서버는 인증키를 URL에서 받으므로
   Environment Variables에 아무것도 등록하지 않아도 됩니다.
5. Deploy 후 정상 기동되면 서버 주소는
   `https://<서비스이름>.onrender.com/mcp` 형태가 됩니다.

## 3단계 — Claude에 커스텀 커넥터로 등록 [인증 방식 변경]

이 서버는 **여러 명이 하나의 서버를 같이 쓸 수 있도록**, 인증키를 서버가
아니라 각자의 등록 URL에 넣는 방식으로 되어 있습니다.

1. Claude.ai → Settings → Connectors → **+ Add custom connector**
2. Name: `국가건설기준(KCSC)` 등 원하는 이름
3. URL: `https://<서비스이름>.onrender.com/mcp?api_key=본인이_발급받은_KCSC_인증키`
   (1단계에서 발급받은 본인의 인증키를 그대로 붙여넣으시면 됩니다)
4. **Advanced settings의 OAuth Client ID/Secret은 비워두세요**
5. Add 클릭 → 연결 확인

**다른 소장님과 같이 쓰시는 경우**: 서버의 base URL
(`https://<서비스이름>.onrender.com/mcp`)만 공유하시면 됩니다. 각자
자기 인증키를 붙여서 등록하면, 호출은 각자의 키로 처리됩니다. 단,
`?api_key=본인키`가 붙은 **전체 URL 자체는 개인 키가 노출되는 것과
같으므로** 공유하지 마세요.

## 로컬 테스트 방법

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt
PORT=8123 ./venv/bin/python server.py
```

다른 터미널에서 (api_key는 URL 쿼리파라미터로):
```bash
curl -N -X POST "http://127.0.0.1:8123/mcp/?api_key=발급받은키" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```
`serverInfo.name: "kcsc-construction-code"` 가 포함된 응답이 오면 정상입니다.

## 참고 — API 파라미터 정보 [정정: 이전 버전의 쿼리파라미터 방식은 오류였습니다]

이전 버전은 `Type`/`Code`/`Key`를 전부 대문자 쿼리파라미터로 보냈으나,
이는 KCSC 공식 문서의 실제 요청 형식과 다릅니다. 실제 형식은 `Type`/`Code`가
**URL 경로(path)**에 들어가고, 인증키는 소문자 `key` 쿼리파라미터입니다:

```
GET https://kcsc.re.kr/OpenApi/CodeViewer/{Type}/{Code}?key=발급받은키
GET https://kcsc.re.kr/OpenApi/CodeList/{Type}/{Code}?key=발급받은키
```

예: `https://kcsc.re.kr/OpenApi/CodeViewer/KCS/114010?key=본인의_KCSC_인증키`

- `Type`: `KDS` 또는 `KCS` (경로 세그먼트)
- `Code`: 조회할 코드 번호, 예: `142010` (경로 세그먼트)
- `key`: 발급받은 인증키 (쿼리파라미터, **소문자**)

이전 방식(전부 대문자 쿼리파라미터)으로 호출하면 `CodeList`는 필수 파라미터
`key` 누락으로 HTTP 400을, `CodeViewer`는 경로가 매칭되지 않아 빈 응답을
반환했습니다 — "커넥터가 연결이 안 된다"는 증상의 실제 원인이었습니다.
`server.py`는 이제 경로 기반 형식으로 수정되었습니다.

## 주의사항 [요확인]

- KCSC OpenAPI의 요청 한도(rate limit) 및 상업적 이용 조건은 발급 페이지의
  이용약관을 직접 확인하시기 바랍니다.
- `list_construction_codes`(`CodeList`)도 `CodeViewer`와 동일한 경로 기반
  형식(`/CodeList/{Type}/{Code}`)을 따른다고 가정하고 수정했습니다. 대분류만
  넣었을 때(`code="14"` 등) 실제로 하위 목록이 반환되는지는 KCSC 공식 문서에
  명시적 예시가 없어 실제 호출로 재확인이 필요합니다 (인증키 승인이 필요해
  이 저장소 환경에서는 kcsc.re.kr에 직접 접속해 검증할 수 없었습니다).
