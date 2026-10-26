import os
import streamlit as st
import requests
import pandas as pd
import io
import re
import xml.etree.ElementTree as ET

def get_secret(name, default=""):
    # Render 등은 환경변수, Streamlit Cloud는 st.secrets에서 읽음
    # (secrets.toml이 없을 때 st.secrets 접근이 예외를 내므로 기본값으로 대체)
    if os.environ.get(name):
        return os.environ[name]
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

# 페이지 설정
st.set_page_config(page_title="브이월드 개별공시지가 일괄 조회기", page_icon="🏰", layout="wide")

st.title("🏰 브이월드 개별공시지가 자동 일괄 조회 앱 (스트림릿 XML 버전)")
st.write("주소 목록을 복사·붙여넣기 하시면, PNU 자동 추출 및 브이월드 개별공시지가 조회가 이루어집니다. 🍰")

col1, col2 = st.columns([2, 1])
with col1:
    vworld_key = st.text_input(
        "🔑 브이월드(V-World) API 인증키",
        value=get_secret("VWORLD_KEY"),  # 키는 코드에 적지 말고 Streamlit Secrets에 등록
        type="password"
    )
with col2:
    std_year = st.text_input(
        "📅 기준연도",
        value="2026",
        placeholder="예: 2026"
    )

st.markdown("### 📋 주소 목록 입력")
st.info("💡 **입력 팁:** 주소와 번지가 포함된 텍스트를 줄바꿈 단위로 입력해 주세요.")

input_text = st.text_area(
    "주소를 줄바꿈 단위로 입력하세요",
    height=200,
    placeholder="경상남도 사천시 용현면 신복리 678-3\n경상남도 사천시 용현면 신복리 678-5"
)

# 브라우저 위장 헤더 (방화벽 차단 우회)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# PNU 생성 및 공시지가 조회 함수 (XML 파싱 방식)
def get_land_price_from_address(address_line, api_key, year):
    # 1~2. 주소 끝의 번지에서 산번지 여부와 본번/부번 추출
    # ("부산", "산청군"처럼 지명에 들어간 "산"을 산번지로 오인하지 않도록 번지 바로 앞의 "산"만 인정)
    match = re.search(r'(?:^|\s)(산\s*)?(\d+)(?:-(\d+))?\s*(?:번지)?\s*$', address_line)
    has_mountain = bool(match and match.group(1))
    lot_division = "2" if has_mountain else "1"
    bonbun = match.group(2).zfill(4) if match else "0000"
    bubun = (match.group(3) or "0").zfill(4) if match else "0000"
        
    # 3. 법정동 코드 획득
    geo_url = "https://api.vworld.kr/req/search"
    geo_params = {
        "service": "search",
        "request": "search",
        "version": "2.0",
        "crs": "EPSG:4326",
        "size": 1,
        "page": 1,
        "query": address_line,
        "type": "address",
        "category": "parcel",
        "format": "json",
        "key": api_key
    }
    
    bjd_code = None
    api_pnu = ""
    geo_error = "검색 결과 없음"
    try:
        resp = requests.get(geo_url, params=geo_params, headers=HEADERS, timeout=10)
        data = resp.json()
        response = data.get("response", {})
        if response.get("status") == "OK":
            items = response["result"]["items"]
            if items:
                api_pnu = items[0].get("id", "")
                if len(api_pnu) >= 10:
                    bjd_code = api_pnu[:10]
        elif response.get("status") == "ERROR":
            err = response.get("error", {})
            geo_error = f"{err.get('code', '')} {err.get('text', '')}".strip()
    except Exception as e:
        geo_error = str(e)

    # 주소 검색에 실패하면 엉뚱한 법정동으로 조회하지 않고 바로 실패 처리
    if not bjd_code:
        return {
            "산번지여부": "산번지 (구분: 2)" if has_mountain else "일반번지 (구분: 1)",
            "생성된PNU": "",
            "공시지가": "지가 조회 실패",
            "상태": f"주소 검색 실패: {geo_error}"
        }

    # 검색 API가 19자리 PNU를 주면 그대로 사용, 아니면 직접 조합
    if len(api_pnu) == 19 and api_pnu.isdigit():
        constructed_pnu = api_pnu
    else:
        constructed_pnu = f"{bjd_code}{lot_division}{bonbun}{bubun}"
    
    # 4. 개별공시지가 속성 API 호출 (스트림릿 도메인 및 XML 형식 적용)
    price_val = "지가 조회 실패"
    status_msg = "성공"
    
    try:
        price_url = "https://api.vworld.kr/ned/data/getIndvdLandPriceAttr"
        price_params = {
            "key": api_key,
            "domain": get_secret("VWORLD_DOMAIN", "https://wrwkpsgunvbdyepgnksjzp.streamlit.app"),  # 키 발급 시 등록한 서비스 URL과 정확히 일치
            "format": "xml",                                  # 엑셀과 동일한 XML 방식
            "stdrYear": year,                                 # 공식 파라미터 stdrYear
            "pnu": constructed_pnu,
            "numOfRows": 1,
            "pageNo": 1
        }
        price_resp = requests.get(price_url, params=price_params, headers=HEADERS, timeout=10)
        
        if price_resp.status_code == 200:
            try:
                root = ET.fromstring(price_resp.text)
                pclnd_elem = root.find(".//pblntfPclnd")
                # 인증키 오류 등은 HTTP 200에 에러 내용을 담아 오므로 따로 확인
                error_code = root.findtext(".//error/code") or root.findtext(".//resultCode")
                error_text = root.findtext(".//error/text") or root.findtext(".//resultMsg")
                if pclnd_elem is not None and pclnd_elem.text:
                    price_val = pclnd_elem.text
                elif error_code and error_code not in ("OK", "INFO-000", "00"):
                    status_msg = f"API 에러: {error_code} {error_text or ''}".strip()
                else:
                    price_val = "해당연도 지가데이터 없음"
                    status_msg = "데이터 없음"
            except Exception as ex:
                status_msg = f"XML 파싱 에러: {str(ex)}"
        else:
            status_msg = f"HTTP 에러: {price_resp.status_code}"
            
    except Exception as e:
        status_msg = f"에러: {str(e)}"
        
    return {
        "산번지여부": "산번지 (구분: 2)" if has_mountain else "일반번지 (구분: 1)",
        "생성된PNU": constructed_pnu,
        "공시지가": price_val,
        "상태": status_msg
    }

if st.button("🚀 PNU 생성 및 공시지가 폭풍 조회 시작!", type="primary"):
    if not vworld_key.strip():
        st.warning("⚠️ 브이월드 API 인증키를 입력해 주세요!")
    elif not input_text.strip():
        st.warning("⚠️ 조회할 주소를 하나 이상 입력해 주세요!")
    else:
        lines = [line.strip() for line in input_text.split("\n") if line.strip()]

        results_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        total_count = len(lines)

        for i, line in enumerate(lines):
            status_text.text(f"⏳ 조회 중... ({i+1}/{total_count}): {line}")
            
            res = get_land_price_from_address(line, vworld_key, std_year)
            
            results_data.append({
                "입력주소": line,
                "기준연도": std_year,
                "지번구분": res["산번지여부"],
                "생성된 19자리 PNU": res["생성된PNU"],
                "공시지가(원/㎡)": res["공시지가"],
                "조회상태": res["상태"]
            })

            progress_bar.progress((i + 1) / total_count)

        status_text.text("✨ 모든 주소 조회 완료!")
        progress_bar.empty()

        df_result = pd.DataFrame(results_data)

        st.markdown("### 📊 조회 결과 미리보기")
        st.dataframe(df_result, use_container_width=True)

        # 엑셀 파일 다운로드 생성
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_result.to_excel(writer, index=False, sheet_name='공시지가조회결과')
        excel_data = output.getvalue()

        st.download_button(
            label="📥 결과 엑셀 파일로 다운로드하기",
            data=excel_data,
            file_name="land_price_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheet.sheet"
        )
