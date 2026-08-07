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

# 모바일 UI 깨짐 방지 및 언어 강제 고정 CSS
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
    
    /* 📱 모바일 환경 버튼 및 입력창 최적화 */
    div.stButton > button {
        white-space: normal !important;
        height: auto !important;
        min-height: 45px;
        word-break: keep-all;
    }
    .stFileUploader label, .stTextInput label {
        font-size: 0.9rem !important;
    }
    
    /* 📱 모바일 환경 API 키(비밀번호) 눈동자 아이콘 글자 깨짐 방지 */
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
    category: str = Field(description="분야 (예: 하도급·계약, 관급자재·신기술, 안전·품질, 폐기물(건설/임목), 현장·가설물)")
    stage: str = Field(description="절차 단계 (예: 설계/원가계상, 계약/착공전, 시공중)")
    action: str = Field(description="이행해야 할 세부 사전 행정절차 및 현장설치 의무 내용")
    legal_basis: str = Field(description="관련 법령 및 행정규칙/고시 조항")
    check_points: list[str] = Field(description="계약심사 및 일상감사 세부 체크리스트 항목")

class ComprehensiveReviewResponse(BaseModel):
    extracted_summary: str = Field(description="입력 문장에서 추출한 핵심 조건 요약")
    overall_summary: str = Field(description="종합 행정 검토 의견 및 누락되기 쉬운 핵심 법정 의무 사항 강조")
    assessments: list[AssessmentItem] = Field(description="사업 규모와 종류에 맞춰 동적으로 판별된 법정 인허가 검토 결과")
    procedures: list[ProcedureStep] = Field(description="단계별·분야별 세부 사전 행정절차 및 감사 체크리스트")

# ==========================================
# 모델 목록 / 세션 상태 초기화
# ==========================================
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
    st.markdown("**📌 스마트 동적 검토 모드 적용 중**")
    st.caption("본 시스템의 결과는 AI가 생성한 참고자료이며 법적 효력이 없다. 최종 판단은 법령 원문 및 담당 부서 검토를 거쳐야 한다.")

# ==========================================
# 4. 메인 화면 - PDF 업로드 및 자연어 입력
# ==========================================
st.markdown('<div class="main-header">⚖️ 공공 공사 실무 및 감사대비 맞춤형 사전절차 검토 시스템</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">설계설명서/과업지시서 PDF(스캔본 포함)를 업로드하거나 내용을 직접 입력하면, AI가 법적 기준을 초과하는 필수 항목을 정밀 판독한다.</div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader("📄 사업계획서 또는 과업지시서 PDF 업로드 (스캔본 인식 지원)", type=["pdf"])

user_prompt = st.text_area(
    "추가 사업 개요 및 강조 사항 (PDF 업로드 시 부연설명만 적거나 비워둬도 됨):",
    key="user_prompt_text",
    height=120,
    placeholder="예시: 도심지 내 유휴부지 2,500㎡에 추정금액 2억 8천만 원을 투입하여 임시 공용주차장을 조성한다. (문서를 첨부한 경우, 문서에 없는 내용만 추가로 입력할 것)"
)
submit_btn = st.button("🔍 맞춤형 정밀 행정 검토 실행", use_container_width=True)

# ==========================================
# 5. Gemini API 분석 시스템 지침
# ==========================================
SYSTEM_INSTRUCTION = """
당신은 대한민국 지자체 건설·토목·건축분야 행정, 계약, 안전관리, 감사(Audit) 실무를 통달한 최고의 전문가다.
사용자의 입력(문서 및 텍스트)을 바탕으로 법적 기준치를 '수치적으로 계산 및 판단'하여, 조건에 부합하는 항목만 동적으로 도출하라.

[동적 판단 및 수치 검토 원칙]
1. **폐기물 3단계 정밀 판별 (건설폐기물 및 임목폐기물):**
   - **건설폐기물:** 100톤 이상이면 '건설폐기물 분리발주 의무', 5톤~100톤 미만이면 '건설폐기물 처리계획 사전신고' 대상으로 판별한다.
   - **임목폐기물 (벌목, 제초, 수목 제거 등):** 5톤 이상 발생 예상 시, 폐기물관리법 제17조에 따라 '사업장일반폐기물(임목폐기물) 분리발주' 대상으로 명확히 지적한다.
2. **계약 방식, 신기술 및 관급자재 (지방계약법 및 판로지원법):**
   - 금액 분석을 통해 일상감사/계약심사 대상 여부(보통 종합 3억, 전문 2억 이상 등) 및 입찰 방식을 명시한다.
   - 공사 내용에 특허나 특정 공법이 예상될 경우 '신기술·특허공법 선정위원회' 사전 심의를 반드시 검토 항목에 넣는다.
   - 추정금액(종합 40억, 전문 30억 등)을 초과할 경우 '중소기업 관급자재 직접구매 대상 품목' 사전 검토 의무를 부여한다.
3. **가설물 및 공종별 특화 필터링:**
   - 현장사무소가 예상되는 공사 시 '가설건축물 축조신고(건축법)' 대상을 검토한다.
   - 복합 공종(예: 토목+통신/전기)일 경우, 금액과 무관하게 '정보통신공사업법/전기공사업법 분리발주' 의무를 지적한다.
4. **규모 미달 시 '해당 없음' 명시 (환경/지하안전 등):**
   - 환경영향평가법, 지하안전법 등은 면적과 굴착 깊이가 기준치 미달일 경우, 반드시 "해당 없음 (사유: 기준 미달)"으로 표기하여 억지 나열을 엄격히 방지한다.

[작성 수칙]
- 공식 문서 양식에 따라 문장의 끝맺음은 '~다', '~할 것', '필요함' 등으로 작성한다. ('해요/합니다' 절대 금지)
- 관련 법령은 시행령, 시행규칙 조항까지 구체적으로 적시한다.
"""

def analyze_comprehensive_project(text: str, file_obj, key: str, model_name: str) -> ComprehensiveReviewResponse | None:
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=300000))
    contents = []
    
    # 1) PDF 파일이 업로드된 경우 Gemini 서버로 전송 및 상태 대기
    if file_obj is not None:
        with st.spinner("🔄 스캔본 PDF를 AI 서버로 전송 및 시각 판독 중이다. 용량에 따라 수십 초가 소요될 수 있다..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file_obj.getvalue())
                tmp_path = tmp.name
            
            gemini_file = client.files.upload(file=tmp_path, mime_type="application/pdf")
            
            # AI 서버에서 파일 처리가 완료(ACTIVE)될 때까지 대기
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
            
    # 2) 텍스트 입력이 있는 경우 추가
    if text.strip():
        contents.append(f"[사용자 추가 입력 및 지시사항]\n{text}")
    elif not contents:
        raise ValueError("분석할 내용이 없다. 텍스트를 입력하거나 PDF 파일을 업로드해야 한다.")
    else:
        contents.append("[사용자 지시사항]\n첨부된 문서를 정밀하게 판독하여 사전에 필요한 행정절차와 검토 항목을 도출하라.")

    base_kwargs = dict(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=ComprehensiveReviewResponse,
    )
    
    with st.spinner("법령 대조 및 맞춤형 정밀 행정 검토를 수행 중이다. 잠시 대기할 것..."):
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
    headers = ["구분", "단계", "이행 사전절차 / 현장설치", "관련 법령", "주요 감사 체크리스트"]
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
        "## 1. 법정 검토 항목 (규모 및 공종별 맞춤 판별)", "",
        "| 검토 항목 | 대상 여부 | 근거 법령 (시행령/규칙) | 판단 및 적용 기준 | 이행 절차 및 협의 부서 |",
        "|---|---|---|---|---|"
    ]
    for item in result.assessments:
        lines.append(f"| {_md_cell(item.name)} | {_md_cell(item.is_required)} | {_md_cell(item.legal_basis)} | {_md_cell(item.target_criteria)} | {_md_cell(item.action_plan)} |")
    lines += ["", "## 2. 분야별 세부 행정절차 및 실무/감사 체크리스트", "", "| 구분 | 단계 | 이행 사전절차 / 현장설치 | 관련 법령 | 주요 감사 체크리스트 |", "|---|---|---|---|---|"]
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
    
    st.subheader("🌳 1. 법정 검토 항목 (규모 및 공종별 맞춤 판별)")
    if res.assessments:
        st.table([{"검토 항목": i.name, "대상 여부": i.is_required, "근거 법령": i.legal_basis, "판단 기준": i.target_criteria, "이행 절차": i.action_plan} for i in res.assessments])
    
    st.subheader("📑 2. 분야별 세부 행정절차 및 실무/감사 체크리스트")
    if res.procedures:
        st.markdown(build_procedures_html(res.procedures), unsafe_allow_html=True)
        
    st.download_button(
        "📥 보고서 다운로드 (Markdown)", 
        data=build_report_markdown(res, used_model).encode("utf-8"), 
        file_name=f"공사검토_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md", 
        mime="text/markdown"
    )