import os
import html
import datetime
import time
import tempfile
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ==========================================
# 1. 페이지 및 레이아웃 설정
# ==========================================
st.set_page_config(
    page_title="공공 공사 실무 및 감사대비 맞춤형 사전절차 검토 시스템",
    page_icon="⚖️",
    layout="wide"
)

st.markdown("""
    <script>
    document.documentElement.lang = 'ko';
    </script>
    <style>
    .main-header { font-size: 2.1rem; font-weight: 700; color: #0F172A; margin-bottom: 0.2rem; }
    .sub-header { font-size: 0.95rem; color: #475569; margin-bottom: 1.5rem; }
    .review-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    .review-table th { border: 1px solid #CBD5E1; background: #F1F5F9; padding: 8px; text-align: left; color:#0F172A; }
    .review-table td { border: 1px solid #CBD5E1; padding: 8px; vertical-align: top; color:#1E293B; }
    .disclaimer-box {
        background:#FEF3C7; border:1px solid #F59E0B; border-radius:8px;
        padding:12px 16px; font-size:0.85rem; color:#92400E; margin-top:1.5rem;
    }
    
    div.stButton > button {
        white-space: normal !important;
        height: auto !important;
        min-height: 45px;
        word-break: keep-all;
    }
    .stFileUploader label, .stTextInput label {
        font-size: 0.9rem !important;
    }
    
    div[data-testid="stTextInput"] button {
        font-size: 0 !important;
        min-width: 30px !important;
    }
    div[data-testid="stTextInput"] button svg {
        width: 20px;
        height: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. Pydantic 구조화된 출력 스키마
# ==========================================
class AssessmentItem(BaseModel):
    name: str = Field(description="영향평가, 인증, 인허가 명칭")
    is_required: str = Field(description="대상 여부 (필수 / 조건부 필요 / 해당없음 - 기준 미달 시 이유 명시)")
    legal_basis: str = Field(description="근거 법률, 시행령, 시행규칙 조항")
    target_criteria: str = Field(description="정확한 세부 판단 기준 (면적, 금액, 굴착깊이 등 수치 명시)")
    action_plan: str = Field(description="사전 이행 절차 및 제출/승인 기관")

class ProcedureStep(BaseModel):
    category: str = Field(description="분야 (예: 입지/부지, 환경/재해, 건축/설비, 안전/보건, 발주/계약, 기타 리스크)")
    stage: str = Field(description="절차 단계 (예: 기획/설계, 계약/착공전, 시공중)")
    action: str = Field(description="이행해야 할 세부 사전 행정절차 및 현장설치 의무 내용")
    legal_basis: str = Field(description="관련 법령 및 행정규칙/고시 조항")
    check_points: list[str] = Field(description="계약심사 및 일상감사 세부 체크리스트 항목")

class ComprehensiveReviewResponse(BaseModel):
    extracted_summary: str = Field(description="입력 문장에서 추출한 핵심 조건 요약")
    overall_summary: str = Field(description="종합 행정 검토 의견 및 누락되기 쉬운 핵심 법정 의무 사항 강조")
    assessments: list[AssessmentItem] = Field(description="사업 규모와 종류에 맞춰 동적으로 판별된 법정 인허가 검토 결과")
    procedures: list[ProcedureStep] = Field(description="단계별·분야별 세부 사전 행정절차 및 감사 체크리스트 (자율 발굴 리스크 포함)")

MODEL_OPTIONS = {
    "gemini-3.6-flash (최신·권장)": "gemini-3.6-flash",
    "gemini-3.5-flash": "gemini-3.5-flash",
    "gemini-flash-latest (항상 최신 Flash 자동 연결)": "gemini-flash-latest",
}

if "user_prompt_text" not in st.session_state:
    st.session_state["user_prompt_text"] = ""

# ==========================================
# 3. 사이드바
# ==========================================
with st.sidebar:
    st.header("⚙️ 시스템 설정")
    default_api_key = os.environ.get("GOOGLE_API_KEY", "")
    api_key = st.text_input("Google Gemini API Key", value=default_api_key, type="password")
    model_label = st.selectbox("분석 모델 선택", list(MODEL_OPTIONS.keys()), index=0)
    selected_model = MODEL_OPTIONS[model_label]
    st.markdown("---")
    st.markdown("**📌 무결점 감사 스캐너 모드 (법정 전체 항목 탑재)**")
    st.caption("본 시스템의 결과는 AI가 생성한 참고자료이며 법적 효력이 없다. 최종 판단은 법령 원문 및 담당 부서 검토를 거쳐야 한다.")

# ==========================================
# 4. 메인 화면 - PDF 업로드 및 자연어 입력
# ==========================================
st.markdown('<div class="main-header">⚖️ 공공 공사 실무 및 감사대비 맞춤형 사전절차 검토 시스템</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">사업 개요(PDF 스캔본 포함)를 입력하면 공공 공사 전체 법정 기준 풀(Pool)을 수치 기반으로 대조하고, 현장 리스크를 자율 발굴한다.</div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader("📄 사업계획서 또는 과업지시서 PDF 업로드 (스캔본 인식 지원)", type=["pdf"])

user_prompt = st.text_area(
    "추가 사업 개요 및 강조 사항 (PDF 업로드 시 부연설명만 적거나 비워둬도 됨):",
    key="user_prompt_text",
    height=120,
    placeholder="예시: 도심지 내 연면적 12,000㎡ 규모의 공공 복합청사를 추정금액 350억 원에 신축한다. 기존 노후 건물(석면 함유 의심) 철거가 포함된다."
)
submit_btn = st.button("🔍 맞춤형 정밀 행정 검토 실행", use_container_width=True)

# ==========================================
# 5. Gemini API 분석 시스템 지침 (무결점 전체 스캔 로직)
# ==========================================
SYSTEM_INSTRUCTION = """
당신은 대한민국 지자체 건설·토목·건축분야 행정, 계약, 안전관리, 감사(Audit) 실무를 통달한 최고의 전문가다.
입력된 공사 개요(문서 및 텍스트)를 바탕으로 아래의 **'공공 공사 필수 법정 검토 풀(Pool)'**을 무조건 1회 이상 전체 스캔하고, 누락되기 쉬운 현장 리스크를 자율 발굴하라.

[공공 공사 필수 법정 검토 풀(Pool) 대조 원칙]

1. **입지, 부지 및 주변 조사 (토지/문화재):** 
   - 매장유산(문화재) 지표조사(3만㎡ 이상), 농지/산지전용허가, 개발행위허가, 하천/도로점용허가를 스캔하라.
   - 굴착 공사 시 '지하 매설물(지장물) GPR 탐사' 및 도로 점용 시 '교통소통대책' 수립 여부를 챙겨라.

2. **환경, 재해 및 현장 관리 (계층형 수치 검토):** 
   - 환경영향평가법(일반/소규모 대조), 재해영향평가(5천/5만㎡), 지하안전평가(10m/20m) 기준을 대조하라.
   - 비산먼지/특정공사 사전신고 여부를 판별하고, 설계 내역에 **세륜시설(세륜기), 세륜장 슬러지 처리비, 방진막, 축중기(과적차량 방지)** 반영 요건을 반드시 검토하라.

3. **건축 및 특수설비 (※ 건축물 공사일 경우에만 해당):** 
   - **BF인증(장애물없는생활환경), ZEB(제로에너지), 녹색건축인증, 경관/건축심의, 소방동의, 가설건축물 축조신고** 대조.
   - 연면적 1만㎡ 이상 시 **미술작품 설치 의무(문화예술진흥법)** 여부를 반드시 판독하라.

4. **안전 및 보건 품질 (중대재해 예방 - 산안법 및 건진법):** 
   - **석면 사전조사:** 기존 건물/설비 철거 해체 시 무조건 실시 명시.
   - **재해예방기술지도:** 총공사비 1억~120억 미만 시 필수 대조.
   - 설계안전성검토(DFS, 지하 10m 등), 안전보건대장(50억 이상), 품질(시험/관리)계획 수립 여부 검토.
   - 비계, 동바리 등 **'가설구조물 구조안전성 검토(구조계산)'** 의무를 짚어라.

5. **발주, 계약 및 원가 정산 (지방계약법 등):** 
   - 일상감사/계약심사, 관급자재 직접구매(종합40억/전문30억) 판별.
   - **전기/통신/소방 분리발주:** 건축/토목 본공사와 무조건 분리발주함을 명시.
   - 폐기물 3단계 판별(건설폐기물 100톤 분리발주 / 임목폐기물 5톤 일반 분리발주).
   - **[감사 타겟]** 법정 경비(산업안전보건관리비, 환경보전비, 4대 사회보험료 등) 사후정산 조건 명시 여부와 **'하도급지킴이(전자대금시스템)'** 의무 적용을 검토하라.

6. **[자율 발굴] 특기사항 및 숨은 리스크:** 
   - 위 항목 외에 해당 사업 특성(어린이보호구역 겹침, 멸종위기종, 특수 공법 등)을 고려해 현장 실무자가 챙겨야 할 숨은 리스크를 자율적으로 도출하라.

[작성 수칙]
- 위 1~5번 항목 중 기준에 미달하는 항목은 과감하게 "해당 없음 (사유: 면적/금액/굴착깊이 미달)"으로 명확히 기재하여 실무자가 안심할 수 있게 하라.
- 공식 문서 양식에 따라 문장의 끝맺음은 '~다', '~할 것', '필요함' 등으로 작성한다. ('해요/합니다' 절대 금지)
"""

def analyze_comprehensive_project(text: str, file_obj, key: str, model_name: str) -> ComprehensiveReviewResponse | None:
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=300000))
    contents = []
    
    if file_obj is not None:
        with st.spinner("🔄 스캔본 PDF를 AI 서버로 전송 및 시각 판독 중이다..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file_obj.getvalue())
                tmp_path = tmp.name
            
            gemini_file = client.files.upload(file=tmp_path, mime_type="application/pdf")
            
            while True:
                f_info = client.files.get(name=gemini_file.name)
                state_str = str(f_info.state).upper()
                if "ACTIVE" in state_str:
                    break
                elif "FAILED" in state_str:
                    os.remove(tmp_path)
                    raise Exception("AI 서버에서 PDF 파일을 판독하는 데 실패했다.")
                time.sleep(2)
                
            contents.append(gemini_file)
            os.remove(tmp_path)
            
    if text.strip():
        contents.append(f"[사용자 추가 입력 및 지시사항]\n{text}")
    elif not contents:
        raise ValueError("분석할 내용이 없다. 텍스트를 입력하거나 PDF 파일을 업로드해야 한다.")
    else:
        contents.append("[사용자 지시사항]\n첨부된 문서를 정밀하게 판독하여 수치 기준에 부합하는 필수 영역 검토 및 숨은 리스크를 도출하라.")

    base_kwargs = dict(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=ComprehensiveReviewResponse,
    )
    
    with st.spinner("공공 공사 전체 법정 풀(Pool) 스캔 및 리스크 자율 발굴을 수행 중이다..."):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(temperature=0.1, **base_kwargs),
            )
        except Exception:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(**base_kwargs),
            )
            
    return response.parsed

def build_procedures_html(procedures: list[ProcedureStep]) -> str:
    headers = ["분야", "단계", "이행 사전절차 / 현장설치", "관련 법령", "주요 감사 체크리스트"]
    parts = ['<table class="review-table"><thead><tr>']
    parts += [f"<th>{html.escape(h)}</th>" for h in headers]
    parts.append("</tr></thead><tbody>")
    for proc in procedures:
        checks = "<br>".join(f"• {html.escape(c)}" for c in proc.check_points) or "-"
        cells = [html.escape(proc.category), html.escape(proc.stage), html.escape(proc.action), html.escape(proc.legal_basis), checks]
        parts.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)

def _md_cell(text: str) -> str: 
    return str(text).replace("|", "\\|").replace("\n", "<br>")

def build_report_markdown(result, model_name) -> str:
    lines = [
        "# 공공 공사 실무 및 감사대비 맞춤형 사전절차 검토 보고서",
        "", f"- 분석 모델: {model_name}", "",
        "## AI 조건 추출 요약", result.extracted_summary, "",
        "## 종합 행정 검토 의견", result.overall_summary, "",
        "## 1. 법정 필수 검토 항목 (전체 풀 스캔 및 수치 대조)", "",
        "| 검토 항목 | 대상 여부 | 근거 법령 (시행령/규칙) | 판단 및 적용 기준 | 이행 절차 및 협의 부서 |",
        "|---|---|---|---|---|"
    ]
    for item in result.assessments:
        lines.append(f"| {_md_cell(item.name)} | {_md_cell(item.is_required)} | {_md_cell(item.legal_basis)} | {_md_cell(item.target_criteria)} | {_md_cell(item.action_plan)} |")
    lines += ["", "## 2. 분야별 세부 행정절차 및 숨은 리스크 발굴", "", "| 분야 | 단계 | 이행 사전절차 / 현장설치 | 관련 법령 | 주요 감사 체크리스트 |", "|---|---|---|---|---|"]
    for proc in result.procedures:
        checks = "<br>".join(f"• {c}" for c in proc.check_points)
        lines.append(f"| {_md_cell(proc.category)} | {_md_cell(proc.stage)} | {_md_cell(proc.action)} | {_md_cell(proc.legal_basis)} | {_md_cell(checks)} |")
    return "\n".join(lines)

# ==========================================
# 6. 실행 및 결과 출력
# ==========================================
if submit_btn:
    if not user_prompt.strip() and uploaded_file is None:
        st.warning("⚠️ 텍스트로 사업 내용을 입력하거나 PDF 파일을 업로드해야 한다.")
    elif not api_key: 
        st.error("🔑 API Key를 입력해야 한다.")
    else:
        try:
            res = analyze_comprehensive_project(user_prompt, uploaded_file, api_key, selected_model)
            if res:
                st.session_state["last_result"] = res
                st.session_state["last_model"] = selected_model
        except Exception as e:
            st.error(f"분석 중 오류가 발생했다: {str(e)}")

if "last_result" in st.session_state:
    res = st.session_state["last_result"]
    used_model = st.session_state["last_model"]
    
    st.success(f"✅ 맞춤형 정밀 행정 검토가 완료되었다. (모델: {used_model})")
    st.subheader("🔎 AI 조건 추출 요약")
    st.info(res.extracted_summary)
    st.subheader("📋 종합 행정 검토 의견")
    st.write(res.overall_summary)
    
    st.subheader("🌳 1. 법정 필수 검토 항목 (전체 풀 스캔 및 수치 대조)")
    if res.assessments:
        st.table([{"검토 항목": i.name, "대상 여부": i.is_required, "근거 법령": i.legal_basis, "판단 기준": i.target_criteria, "이행 절차": i.action_plan} for i in res.assessments])
    
    st.subheader("📑 2. 분야별 세부 행정절차 및 숨은 리스크 발굴")
    if res.procedures:
        st.markdown(build_procedures_html(res.procedures), unsafe_allow_html=True)
        
    st.download_button(
        "📥 보고서 다운로드 (Markdown)", 
        data=build_report_markdown(res, used_model).encode("utf-8"), 
        file_name=f"공사검토_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md", 
        mime="text/markdown"
    )