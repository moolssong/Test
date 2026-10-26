# ==========================================================================
# 브이월드 개별공시지가 일괄 조회 앱 (Streamlit)
#  - 주소 목록을 붙여넣으면 PNU(19자리 필지고유번호)를 만들고
#    브이월드 API로 개별공시지가를 조회해 표와 엑셀 파일로 보여줌
#  - 실행: 터미널에서  streamlit run 공시지가조회.py
#
#  ★★ 매년 업데이트할 것 ★★
#   1) 기준연도: 아래 "📅 기준연도" 입력칸의 value="2026"을 새 연도로 변경
#   2) API 키  : 아래 "🔑 API 인증키" 입력칸의 기본 키를 새 키로 변경 (만료/재발급 시)
#
#  ※ 참고: Streamlit Cloud(미국 서버)에서는 브이월드가 해외 접속을 막아
#          조회가 실패함 → 한국에 있는 PC에서 실행해야 정상 작동
# ==========================================================================

import os                               # 환경변수 읽기용
import streamlit as st                  # 웹 화면(앱) 만드는 도구
import requests                         # 인터넷 요청(API 호출) 보내는 도구
import pandas as pd                     # 표(데이터프레임) 다루는 도구
import io                               # 엑셀 파일을 메모리에서 만들 때 사용
import re                               # 글자 패턴 찾기(정규식) - 번지 추출용
import xml.etree.ElementTree as ET      # XML 응답 해석하는 도구


def get_secret(name, default=""):
    # 비밀값(키 등)을 읽어오는 함수
    # 읽는 순서: ① 환경변수(Render 등) → ② Streamlit Secrets → ③ 코드에 적힌 기본값(default)
    if os.environ.get(name):
        return os.environ[name]
    try:
        return st.secrets.get(name, default)
    except Exception:
        # secrets.toml 파일이 없으면 에러가 나므로 기본값으로 대체
        return default


# ----- 화면 상단: 페이지 제목과 안내 문구 -----
st.set_page_config(page_title="브이월드 개별공시지가 일괄 조회기", page_icon="🏰", layout="wide")

st.title("🏰 브이월드 개별공시지가 자동 일괄 조회 앱 (스트림릿 XML 버전)")
st.write("주소 목록을 복사·붙여넣기 하시면, PNU 자동 추출 및 브이월드 개별공시지가 조회가 이루어집니다. 🍰")

# ----- 입력칸: 인증키(왼쪽 넓게)와 기준연도(오른쪽 좁게) -----
col1, col2 = st.columns([2, 1])  # 화면을 2:1 비율로 나눔
with col1:
    vworld_key = st.text_input(
        "🔑 브이월드(V-World) API 인증키",
        # ★ [매년 업데이트] API 키: 키가 만료되거나 재발급받으면 따옴표 안의 값을 새 키로 바꾸세요
        #   - 키 확인/연장: 브이월드(vworld.kr) 로그인 → 마이페이지 → 인증키 관리
        #   - Streamlit Secrets에 VWORLD_KEY가 있으면 그 값이 우선 적용됨
        value=get_secret("VWORLD_KEY", "E6CE8D99-9102-4628-B14F-6FA339CACC6E"),
        type="password"  # 화면에 ●●●로 가려서 표시
    )
with col2:
    std_year = st.text_input(
        "📅 기준연도",
        # ★ [매년 업데이트] 기준연도: "2026"을 새 연도로 바꾸세요 (예: "2027")
        #   - 개별공시지가는 매년 5월 말쯤 발표되므로 발표 이후에 바꾸는 게 좋아요
        #   - 화면에서 직접 고쳐서 조회해도 됨 (이 값은 처음 보이는 기본값)
        value="2026",
        placeholder="예: 2026"
    )

# ----- 입력칸: 주소 목록 -----
st.markdown("### 📋 주소 목록 입력")
st.info("💡 **입력 팁:** 주소와 번지가 포함된 텍스트를 줄바꿈 단위로 입력해 주세요.")

input_text = st.text_area(
    "주소를 줄바꿈 단위로 입력하세요",
    height=200,
    placeholder="경상남도 사천시 용현면 신복리 678-3\n경상남도 사천시 용현면 신복리 678-5"
)

# 요청할 때 "나는 크롬 브라우저야"라고 자기소개하는 정보
# (브이월드가 브라우저가 아닌 프로그램의 요청을 막는 경우가 있어서 붙임)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def get_land_price_from_address(address_line, api_key, year):
    # 주소 한 줄을 받아서 → PNU를 만들고 → 공시지가를 조회해서 결과를 돌려주는 함수
    #
    # PNU 19자리 구성:  법정동코드(10) + 산구분(1) + 본번(4) + 부번(4)
    #   예) 4824033000 | 1 | 0678 | 0003  → 678-3번지(일반)

    # ----- 1. 산번지 여부 파악 -----
    # 주소에 "산"이 있으면 산번지(2), 없으면 일반번지(1)
    # ※ "부산", "산청군"처럼 지명에 "산"이 들어가도 산번지로 판단되니 주의
    has_mountain = "산" in address_line
    lot_division = "2" if has_mountain else "1"

    # ----- 2. 번지 추출 -----
    # 주소에서 처음 나오는 숫자(와 -) 덩어리를 번지로 봄. 예) "678-3"
    match = re.search(r'산?\s*([0-9\-]+)', address_line)
    raw_bunji = match.group(1) if match else "0"

    if "-" in raw_bunji:
        # "678-3" → 본번 "0678", 부번 "0003" (zfill(4) = 앞을 0으로 채워 4자리로)
        parts = raw_bunji.split("-")
        bonbun = parts[0].zfill(4)
        bubun = parts[1].zfill(4)
    else:
        # "678" → 본번 "0678", 부번 "0000"
        bonbun = raw_bunji.zfill(4)
        bubun = "0000"

    # ----- 3. 법정동 코드(PNU 앞 10자리) 얻기: 브이월드 주소 검색 API -----
    geo_url = "https://api.vworld.kr/req/search"
    geo_params = {
        "service": "search",
        "request": "search",
        "version": "2.0",
        "crs": "EPSG:4326",      # 좌표계 (위도/경도)
        "size": 1,               # 검색 결과 1건만
        "page": 1,
        "query": address_line,   # 검색할 주소
        "type": "address",       # 주소로 검색
        "category": "parcel",    # 지번 주소
        "format": "json",        # 응답 형식
        "key": api_key           # 인증키
    }

    # 검색에 실패했을 때 쓰는 기본 법정동 코드 (경상남도 사천시 용현면)
    # ※ 검색이 실패하면 주소와 상관없이 이 값이 들어가므로, 다른 지역은 PNU가 틀릴 수 있음
    bjd_code = "4824033000"
    geo_error = ""  # 주소 검색 실패 이유 (조회상태 칸에 표시)
    try:
        resp = requests.get(geo_url, params=geo_params, headers=HEADERS, timeout=5)  # 최대 5초 대기
        data = resp.json()                       # 응답(JSON)을 파이썬 데이터로 변환
        response = data.get("response", {})
        if response.get("status") == "OK":
            items = response["result"]["items"]
            if items:
                # 검색 결과의 id가 PNU → 앞 10자리를 법정동 코드로 사용
                api_pnu = items[0].get("id", "")
                if len(api_pnu) >= 10:
                    bjd_code = api_pnu[:10]
            else:
                geo_error = "주소 검색 결과 없음"
        else:
            # 브이월드가 에러를 보낸 경우 (키 오류 등): 에러 코드와 내용을 기록
            err = response.get("error", {})
            geo_error = f"주소 검색 실패: {err.get('code', '')} {err.get('text', '')}".strip()
    except Exception as e:
        # 연결 실패, 응답 해석 실패 등
        geo_error = f"주소 검색 실패: {str(e)}"

    # 최종 19자리 PNU 조합 (법정동코드 + 산구분 + 본번 + 부번)
    constructed_pnu = f"{bjd_code}{lot_division}{bonbun}{bubun}"

    # ----- 4. 개별공시지가 조회: 브이월드 개별공시지가 API -----
    price_val = "지가 조회 실패"  # 기본값 (성공하면 숫자로 바뀜)
    status_msg = "성공"

    try:
        price_url = "https://api.vworld.kr/ned/data/getIndvdLandPriceAttr"
        price_params = {
            "key": api_key,                    # 인증키
            # 키 발급 시 등록한 서비스 URL과 글자 하나까지 똑같아야 함
            # (Streamlit Secrets에 VWORLD_DOMAIN이 있으면 그 값이 우선 적용됨)
            "domain": get_secret("VWORLD_DOMAIN", "https://wrwkpsgunvbdyepgnksjzp.streamlit.app"),
            "format": "xml",                   # 응답 형식 (엑셀과 동일한 XML)
            "stdrYear": year,                  # 기준연도
            "pnu": constructed_pnu,            # 조회할 필지 PNU
            "numOfRows": 1,                    # 결과 1건만
            "pageNo": 1
        }
        price_resp = requests.get(price_url, params=price_params, headers=HEADERS, timeout=10)  # 최대 10초 대기

        if price_resp.status_code == 200:
            # HTTP 200 = 서버가 정상 응답
            try:
                root = ET.fromstring(price_resp.text)       # XML 글자를 해석
                pclnd_elem = root.find(".//pblntfPclnd")    # 공시지가 태그 찾기
                # 인증키 오류 등은 HTTP 200에 에러 내용을 담아 오므로 따로 확인
                error_code = root.findtext(".//error/code") or root.findtext(".//resultCode")
                error_text = root.findtext(".//error/text") or root.findtext(".//resultMsg")
                if pclnd_elem is not None and pclnd_elem.text:
                    # [성공] 공시지가 값 저장
                    price_val = pclnd_elem.text
                elif error_code and error_code not in ("OK", "INFO-000", "00"):
                    # [실패] 브이월드가 에러를 보냄 (키 오류 등)
                    status_msg = f"API 에러: {error_code} {error_text or ''}".strip()
                else:
                    # [실패] 정상 응답인데 해당 연도 데이터가 없음
                    price_val = "해당연도 지가데이터 없음"
                    status_msg = "데이터 없음"
            except Exception as ex:
                # 응답이 XML 형식이 아님 (차단 페이지 등)
                status_msg = f"XML 파싱 에러: {str(ex)}"
        else:
            # HTTP 200이 아님 (403 = 거부, 500 = 서버 오류 등)
            status_msg = f"HTTP 에러: {price_resp.status_code}"

    except Exception as e:
        # 연결 실패 (해외 서버 차단, 인터넷 끊김, 시간 초과 등)
        status_msg = f"에러: {str(e)}"

    # 결과를 묶어서 돌려줌 (주소 검색이 실패했으면 그 이유도 조회상태에 덧붙임)
    return {
        "산번지여부": "산번지 (구분: 2)" if has_mountain else "일반번지 (구분: 1)",
        "생성된PNU": constructed_pnu,
        "공시지가": price_val,
        "상태": f"{status_msg} ({geo_error})" if geo_error else status_msg
    }


# ----- 조회 버튼을 눌렀을 때 실행되는 부분 -----
if st.button("🚀 PNU 생성 및 공시지가 폭풍 조회 시작!", type="primary"):
    # 입력값 확인: 키나 주소가 비어 있으면 경고만 띄우고 멈춤
    if not vworld_key.strip():
        st.warning("⚠️ 브이월드 API 인증키를 입력해 주세요!")
    elif not input_text.strip():
        st.warning("⚠️ 조회할 주소를 하나 이상 입력해 주세요!")
    else:
        # 입력한 주소를 줄 단위로 나누고, 빈 줄은 제외
        lines = [line.strip() for line in input_text.split("\n") if line.strip()]

        results_data = []                 # 결과를 모아둘 목록
        progress_bar = st.progress(0)     # 진행률 막대
        status_text = st.empty()          # "조회 중..." 문구 표시 자리

        total_count = len(lines)

        # 주소를 한 줄씩 차례로 조회
        for i, line in enumerate(lines):
            status_text.text(f"⏳ 조회 중... ({i+1}/{total_count}): {line}")

            res = get_land_price_from_address(line, vworld_key, std_year)

            # 결과 표의 한 행으로 저장 (왼쪽이 표의 열 이름)
            results_data.append({
                "입력주소": line,
                "기준연도": std_year,
                "지번구분": res["산번지여부"],
                "생성된 19자리 PNU": res["생성된PNU"],
                "공시지가(원/㎡)": res["공시지가"],
                "조회상태": res["상태"]
            })

            progress_bar.progress((i + 1) / total_count)  # 진행률 갱신

        status_text.text("✨ 모든 주소 조회 완료!")
        progress_bar.empty()  # 진행률 막대 숨기기

        # 결과 목록을 표(데이터프레임)로 변환
        df_result = pd.DataFrame(results_data)

        # 화면에 결과 표 보여주기
        st.markdown("### 📊 조회 결과 미리보기")
        st.dataframe(df_result, use_container_width=True)

        # 결과 표를 엑셀 파일로 만들기 (파일로 저장하지 않고 메모리에서 바로 생성)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_result.to_excel(writer, index=False, sheet_name='공시지가조회결과')
        excel_data = output.getvalue()

        # 엑셀 다운로드 버튼
        st.download_button(
            label="📥 결과 엑셀 파일로 다운로드하기",
            data=excel_data,
            file_name="land_price_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheet.sheet"
        )
