import os
import html
import datetime
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ==========================================
# 1. 페이지 및 레이아웃 설정
# ==========================================
st.set_page_config(
    page_title="공공 공사 전 공종·세부 법령 종합 행정 사전절차 검토 시스템",
    page_icon="⚖️",
    layout="wide"
)

st.markdown("""
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
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. Pydantic 구조화된 출력 스키마
# ==========================================
class AssessmentItem(BaseModel):
    name: str = Field(description="영향평가, 인증, 인허가, 법정계획 검토 항목 명칭")
    is_required: str = Field(description="대상 여부 (필수 / 조건부 필요 / 해당없음 / 검토필요)")
    legal_basis: str = Field(description="근거 법률, 시행령, 시행규칙 조항")
    target_criteria: str = Field(description="정확한 세부 판단 기준 (면적, 금액, 굴착깊이 등)")
    action_plan: str = Field(description="사전 이행 절차 및 제출/승인 기관")

class ProcedureStep(BaseModel):
    category: str = Field(description="분야 (예: 하도급·노무비, 장비대금, 안전·품질, 환경·인증, 계약·감사)")
    stage: str = Field(description="절차 단계 (예: 기본기획, 설계/원가계상, 계약/착공전, 시공중, 준공)")
    action: str = Field(description="이행해야 할 세부 사전 행정절차 및 현장설치 의무 내용")
    legal_basis: str = Field(description="관련 법령 및 행정규칙/고시 조항")
    check_points: list[str] = Field(description="감사 및 실무 검토 세부 체크리스트 항목")

class ComprehensiveReviewResponse(BaseModel):
    extracted_summary: str = Field(description="입력 문장에서 추출한 핵심 조건 요약 (공종, 금액, 면적, 특수조건 등)")
    overall_summary: str = Field(description="종합 행정 검토 의견 및 누락되기 쉬운 핵심 법정 의무 사항 강조")
    assessments: list[AssessmentItem] = Field(description="법정 영향평가, 친환경 인증, 품질/안전 세부 항목 검토 결과")
    procedures: list[ProcedureStep] = Field(description="단계별·분야별 세부 사전 행정절차 및 감사 체크리스트")

# ==========================================
# 모델 목록 / 예시문 상수 / 세션 상태 초기화
# ==========================================
MODEL_OPTIONS = {
    "gemini-3.6-flash (최신·권장)": "gemini-3.6-flash",
    "gemini-3.5-flash": "gemini-3.5-flash",
    "gemini-flash-latest (항상 최신 Flash 자동 연결)": "gemini-flash-latest",
    "gemini-2.5-flash (2026-10-16 종료 예정)": "gemini-2.5-flash",
}

EXAMPLE_1 = "기존 노후 건물을 철거하고, 사업부지 8,000㎡에 추정공사비 15억 원 규모로 공공건축물을 신축합니다. 철거 석면조사, ZEB 인증, 품질/안전관리(CSI), 기술지도, 전자카드제, 직접시공의무, 하도급 및 기계대여대금 보증 등 전반적인 사전절차를 검토해 주세요."
EXAMPLE_2 = "도로 점용을 포함하여 총사업비 45억 원 규모의 도로 개설 공사를 시행하고자 합니다. 교통통제 신고, 세륜/축중기, 장비대금 지급보증, 노무비 구분관리, 전자카드제 등 감사 지적에 대비한 행정절차를 알려주세요."

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
    if selected_model == "gemini-2.5-flash":
        st.warning("⚠️ 이 모델은 2026-10-16 종료 예정입니다. 최신 모델 사용을 권장합니다.")

    st.markdown("---")
    st.markdown("""
    **📌 종합 감사대비 핵심 추가 검토 항목**
    - **하도급/노무비:** 직접시공의무(건산법), 전자대금지급(하도급지킴이)
    - **장비/기계:** 건설기계 대여대금 지급보증
    - **인증/감리:** ZEB(제로에너지), 녹색건축 인증, 건설사업관리 용역
    - **철거/교통:** 철거 전 석면조사, 도로공사 교통통제 신고
    - **기존 반영:** 품질/안전계획서, 전자카드제, 기술지도(발주자계약), 환경/비산먼지
    """)
    st.markdown("---")
    st.caption("본 시스템의 결과는 AI가 생성한 참고자료이며 법적 효력이 없습니다. 최종 판단은 법령 원문 및 담당 부서 검토를 거쳐야 합니다.")

# ==========================================
# 4. 메인 화면 - 자연어 입력
# ==========================================
st.markdown('<div class="main-header">⚖️ 공공 공사 실무 및 감사대비 사전절차 종합 검토 시스템</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">설계/원가계상부터 계약, 착공 시 놓치기 쉬운 모든 법정 의무(안전, 환경, 인증, 하도급, 장비/노무비)를 자동 발굴하여 검토합니다.</div>', unsafe_allow_html=True)

st.write("**💡 테스트용 예시문 선택:**")
col_ex1, col_ex2 = st.columns(2)
if col_ex1.button("📌 예시 1: 철거 포함 15억 규모 건축물 신축 (석면/인증/하도급 종합)"):
    st.session_state["user_prompt_text"] = EXAMPLE_1
if col_ex2.button("📌 예시 2: 45억 규모 도로개설 (교통신고/장비대금/노무비 종합)"):
    st.session_state["user_prompt_text"] = EXAMPLE_2

user_prompt = st.text_area(
    "사업 개요 및 검토 요청 사항을 자연어로 입력하세요:",
    key="user_prompt_text",
    height=130,
    placeholder="예시: 30억 원 규모 부지조성 공사 추진 시 적용되는 직접시공비율, 장비대여대금 보증, 노무비 관리, 환경설비(세륜기), 안전관리 및 전자카드제 관련 절차를 전부 알려줘."
)

submit_btn = st.button("🔍 실무 및 감사대비 정밀 검토 실행", use_container_width=True)

# ==========================================
# 5. Gemini API 분석 시스템 지침
# ==========================================
SYSTEM_INSTRUCTION = """
당신은 대한민국 지자체 건설·토목·건축분야 행정, 계약, 안전관리, 감사(Audit) 실무를 통달한 최고의 전문가입니다.
단순 인허가뿐만 아니라 지자체 공사 감사에서 가장 많이 지적되는 '하도급 관리, 장비대금, 친환경 인증, 철거 전 사전조사' 항목까지 스스로 발굴하여 완벽하게 검토해야 합니다.

[작성 원칙: 공식 문서 문체 적용]
보고서 작성 시 모든 문장의 끝맺음은 공식 문서 양식에 따라 반드시 '~다' (예: 시행해야 한다, 의무가 있다) 또는 명사형(예: 제출 의무, 검토 필요)으로 작성할 것. '해요', '합니다' 체는 사용하지 마십시오.

[필수 전수 검토 카테고리 (절대 누락 금지)]

1. **도급·하도급, 노무비 및 건설기계 관리 (건산법 등):**
   - **직접시공의무:** 건산법 시행령 제30조의2 (70억 원 미만 공사 원도급자 직접시공 비율 산정).
   - **건설기계 대여대금 지급보증:** 건산법 제68조의3 (장비대금 체불 방지를 위한 보증서 발급 및 비용 반영).
   - **노무비 구분관리 및 직접지급:** 지방자치단체 입찰 및 계약 집행기준에 따른 하도급지킴이 사용 및 노무비 전용계좌 관리.

2. **철거, 해체 및 교통통제 (기존 구조물/도로 점용 시):**
   - **석면조사 의무:** 산업안전보건법 제119조 (기존 건축물/설비 철거 및 해체 전 석면조사 실시 및 노동부 제출).
   - **도로공사 신고:** 도로교통법 시행규칙 제43조 (도로 점용 시 관할 경찰서 교통통제 및 안전계획 신고).

3. **친환경 건축물 인증 및 감리 (건축공사 시):**
   - **ZEB, 녹색건축, 에너지효율등급:** 녹색건축물 조성 지원법 시행령 (연면적 500㎡ 이상 공공건축물 대상 의무화).
   - **장애물 없는 생활환경(BF) 인증:** 장애인등편의법 (예비/본인증).
   - **건설사업관리(CM) 및 감리:** 건진법 제39조 (200억 이상 또는 특정 공종 건설사업관리 발주).

4. **품질 및 안전·보건 관리 체계:**
   - **건진법:** 품질관리계획/품질시험계획, 시험실 및 인력 배치, 안전관리계획서(CSI), DFS 설계안전성 검토.
   - **산안법:** 재해예방기술지도(발주자 직접계약 1억~120억 미만), 발주자 안전보건대장(50억 이상), 유해위험방지계획서.
   
5. **현장 환경/근로자 관리 및 각종 인허가:**
   - **근로자:** 건설근로자법 (공공 1억 이상 전자카드제 의무).
   - **환경/시설:** 비산먼지/특정공사 소음 신고, 세륜기/측면살수시설, 도로 파손 방지용 축중기 설치.
   - **법정평가:** 소규모 환경영향평가, 재해영향평가, 지하안전평가, 매장유산 지표조사.

[작성 수칙]
- 모든 검토 항목에서 **법률명 + 시행령/시행규칙/고시 명칭 및 관련 조항**을 정확히 기입한다.
- 검토 대상이 아닌 항목이라도 "해당 없음(이유)"을 명시하여 검토했음을 증명한다.
"""

_SAMPLING_ERROR_HINTS = (
    "temperature", "top_p", "top_k", "sampling", "not supported", "unknown field", "invalid argument"
)

def analyze_comprehensive_project(text: str, key: str, model_name: str) -> ComprehensiveReviewResponse | None:
    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=300000)
    )
    contents = f"[사용자 입력 내용]\n{text}"
    base_kwargs = dict(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=ComprehensiveReviewResponse,
    )

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(temperature=0.1, **base_kwargs),
        )
    except Exception as e:
        if any(hint in str(e).lower() for hint in _SAMPLING_ERROR_HINTS):
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(**base_kwargs),
            )
        else:
            raise

    return response.parsed

# ==========================================
# 표시 및 보고서 유틸
# ==========================================
def build_procedures_html(procedures: list[ProcedureStep]) -> str:
    headers = ["구분", "단계", "이행 사전절차 / 현장설치의무", "관련 법령 (시행령/시행규칙)", "주요 감사 및 실무 체크리스트"]
    parts = ['<table class="review-table"><thead><tr>']
    parts += [f"<th>{html.escape(h)}</th>" for h in headers]
    parts.append("</tr></thead><tbody>")
    for proc in procedures:
        checks = "<br>".join(f"• {html.escape(c)}" for c in proc.check_points) or "-"
        cells = [
            html.escape(proc.category),
            html.escape(proc.stage),
            html.escape(proc.action),
            html.escape(proc.legal_basis),
            checks,
        ]
        parts.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)

def _md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", "<br>")

def build_report_markdown(result: ComprehensiveReviewResponse, model_name: str) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 공공 공사 실무 및 감사대비 사전절차 종합 검토 보고서",
        "",
        f"- 생성일시: {now}",
        f"- 분석 모델: {model_name}",
        "",
        "## AI 조건 추출 요약",
        result.extracted_summary,
        "",
        "## 종합 행정 검토 의견",
        result.overall_summary,
        "",
        "## 1. 법정 검토 항목 (영향평가, 인증, 하도급, 안전, 품질)",
        "",
        "| 검토 항목 | 대상 여부 | 근거 법령 (시행령/규칙/고시) | 판단 및 적용 기준 | 이행 절차 및 협의/설치 부서 |",
        "|---|---|---|---|---|",
    ]
    for item in result.assessments:
        lines.append(
            f"| {_md_cell(item.name)} | {_md_cell(item.is_required)} | {_md_cell(item.legal_basis)} "
            f"| {_md_cell(item.target_criteria)} | {_md_cell(item.action_plan)} |"
        )

    lines += [
        "",
        "## 2. 분야별 세부 행정절차 및 실무/감사 체크리스트",
        "",
        "| 구분 | 단계 | 이행 사전절차 / 현장설치의무 | 관련 법령 (시행령/규칙) | 주요 감사 체크리스트 |",
        "|---|---|---|---|---|",
    ]
    for proc in result.procedures:
        checks = "<br>".join(f"• {c}" for c in proc.check_points)
        lines.append(
            f"| {_md_cell(proc.category)} | {_md_cell(proc.stage)} | {_md_cell(proc.action)} "
            f"| {_md_cell(proc.legal_basis)} | {_md_cell(checks)} |"
        )

    lines += [
        "",
        "---",
        "> ⚠️ 본 보고서는 AI가 생성한 참고자료로 법적 효력이 없습니다. "
        "제시된 조항 및 수치 기준은 반드시 관계 법령 원문과 담당 부서 검토를 통해 확인하시기 바랍니다.",
    ]
    return "\n".join(lines)

# ==========================================
# 6. 실행 및 결과 출력
# ==========================================
if submit_btn:
    current_text = st.session_state.get("user_prompt_text", "").strip()
    if not current_text:
        st.warning("⚠️ 검토할 사업 내용을 입력해주세요.")
    elif not api_key:
        st.error("🔑 사이드바에 Google Gemini API Key를 입력해주세요.")
    else:
        with st.spinner("감사 빈출 항목(하도급, 장비대금, 노무비, 인증 등)까지 포함하여 전수 분석 중입니다..."):
            try:
                result = analyze_comprehensive_project(current_text, api_key, selected_model)
                if result is None:
                    st.error("AI가 구조화된 응답을 생성하지 못했습니다. 입력 문장을 조금 더 구체적으로 작성하거나 다시 시도해주세요.")
                else:
                    st.session_state["last_result"] = result
                    st.session_state["last_model"] = selected_model
            except Exception as e:
                st.error(f"분석 중 오류가 발생했습니다: {str(e)}")

if "last_result" in st.session_state:
    result = st.session_state["last_result"]
    used_model = st.session_state.get("last_model", selected_model)

    st.success(f"✅ 종합 감사대비 정밀 행정 검토가 완료되었습니다. (모델: {used_model})")

    st.subheader("🔎 AI 조건 추출 요약")
    st.info(result.extracted_summary)

    st.subheader("📋 종합 행정 검토 의견")
    st.write(result.overall_summary)

    st.subheader("🌳 1. 법정 검토 항목 (영향평가, 인증, 하도급, 안전, 품질)")
    if result.assessments:
        assess_data = [{
            "검토 항목": item.name,
            "대상 여부": item.is_required,
            "근거 법령": item.legal_basis,
            "판단 및 적용 기준": item.target_criteria,
            "이행 절차": item.action_plan,
        } for item in result.assessments]
        st.table(assess_data)
    else:
        st.caption("해당 항목에 대한 분석 결과가 없습니다.")

    st.subheader("📑 2. 분야별 세부 행정절차 및 실무/감사 체크리스트")
    if result.procedures:
        st.markdown(build_procedures_html(result.procedures), unsafe_allow_html=True)
    else:
        st.caption("해당 항목에 대한 분석 결과가 없습니다.")

    st.markdown("""
        <div class="disclaimer-box">
        ⚠️ <b>안내</b> — 본 결과는 AI가 생성한 참고자료로 <b>법적 효력이 없습니다.</b>
        제시된 기준은 실제 법령 개정에 따라 다를 수 있으므로, 최종 확정 전 반드시 관계 법령 원문을 확인하시기 바랍니다.
        </div>
    """, unsafe_allow_html=True)

    report_md = build_report_markdown(result, used_model)
    st.download_button(
        label="📥 검토 결과 보고서 다운로드 (Markdown)",
        data=report_md.encode("utf-8"),
        file_name=f"공사행정검토_감사대비_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md",
        mime="text/markdown",
        use_container_width=True,
    )