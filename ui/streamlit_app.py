"""
Streamlit UI for the banking Text-to-SQL API.

Calls the FastAPI service over HTTP (API_BASE_URL) rather than importing
app.pipeline directly — architecture doc §6.2 models Streamlit as a
client of the API (ST --> EP), and importing the pipeline here would
duplicate the model-loading problem (each takes several seconds) inside
a second process.

Run: streamlit run ui/streamlit_app.py
(the FastAPI service must already be running — see app/main.py)

See enterprise-text-to-sql-architecture.md §6.2.
"""

import os
import sys

import requests
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import API_BASE_URL, EXECUTE_ENABLED  # noqa: E402

st.set_page_config(page_title="Banking Text-to-SQL", page_icon="🏦", layout="wide")

st.title("🏦 Banking Text-to-SQL")
st.caption(f"API: {API_BASE_URL}")

if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "feedback_sent" not in st.session_state:
    st.session_state.feedback_sent = False


def call_query(question, execute):
    response = requests.post(
        f"{API_BASE_URL}/api/v1/query",
        json={"question": question, "execute": execute},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def call_feedback(query_id, is_correct, corrected_sql, comment, promote):
    response = requests.post(
        f"{API_BASE_URL}/api/v1/feedback",
        json={
            "query_id": query_id,
            "is_correct": is_correct,
            "corrected_sql": corrected_sql or None,
            "comment": comment or None,
            "promote": promote,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


question = st.text_input("Ask a question about the banking data", placeholder="e.g. show me overdue EMI payments")

execute_requested = False
if EXECUTE_ENABLED:
    execute_requested = st.checkbox("Also execute the query and show results", value=False)
else:
    st.caption("Execution is disabled server-side (EXECUTE_ENABLED=false).")

if st.button("Ask", type="primary") and question.strip():
    with st.spinner("Retrieving context, generating SQL, validating..."):
        try:
            st.session_state.last_result = call_query(question.strip(), execute_requested)
            st.session_state.feedback_sent = False
        except requests.RequestException as exc:
            st.error(f"Request failed: {exc}")
            st.session_state.last_result = None

result = st.session_state.last_result

if result:
    st.divider()

    col_sql, col_meta = st.columns([2, 1])

    with col_sql:
        st.subheader("Generated SQL")
        if result["sql"]:
            st.code(result["sql"], language="sql")
        else:
            st.info("No SQL generated.")

        if result["valid"]:
            st.success("Validation passed.")
        else:
            st.error("Validation failed.")

        # Errors block validation; warnings are advisory and don't fail
        # the query (guardrails deliberately distinguishes the two).
        for error in result["errors"]:
            st.error(error)
        for warning in result["warnings"]:
            st.warning(warning)

        if result["retried_for_validation"]:
            st.caption("⚠️ The first attempt failed validation; this SQL is from the automatic repair retry.")

    with col_meta:
        st.subheader("Confidence")
        # Retrieval confidence and the LLM's self-reported confidence
        # legitimately differ (the reranker under-scores aggregation
        # questions) -- shown separately, not reconciled.
        if result["retrieval_confidence"]:
            st.metric(
                "Retrieval confidence",
                result["retrieval_confidence"]["label"],
                f"{result['retrieval_confidence']['score']:.2f}",
            )
        st.metric("LLM self-reported confidence", result["llm_confidence"] or "—")

        if result["cost"]:
            st.caption(f"Est. cost: {result['cost']['total_cost']} · Est. rows: {result['cost']['plan_rows']}")

        st.subheader("Tables")
        for table in result["selected_tables"]:
            badge = "🎯 matched" if table["origin"] == "matched" else "↳ expansion"
            st.text(f"{table['table_name']} ({badge})")

        if result["join_paths"]:
            with st.expander(f"Join paths ({len(result['join_paths'])})"):
                for jp in result["join_paths"]:
                    hops = " → ".join(
                        f"{hop['from_table']}.{hop['from_column']}={hop['to_table']}.{hop['to_column']}"
                        for hop in jp["path"]
                    )
                    st.text(f"{jp['from']} → {jp['to']}: {hops}")

    if result["results"] is not None:
        st.subheader("Results")
        st.dataframe(
            [dict(zip(result["columns"], row)) for row in result["results"]],
            use_container_width=True,
        )

    st.divider()
    st.subheader("Feedback")

    if st.session_state.feedback_sent:
        st.success("Feedback submitted. Thanks!")
    else:
        fb_col1, fb_col2 = st.columns(2)
        corrected_sql = st.text_area("Correction (optional)", placeholder="Paste corrected SQL if the query was wrong")
        comment = st.text_input("Comment (optional)")
        promote = st.checkbox("Promote to the few-shot example bank (meta.query_patterns)", value=False)

        with fb_col1:
            if st.button("👍 Correct"):
                call_feedback(result["query_id"], True, corrected_sql, comment, promote)
                st.session_state.feedback_sent = True
                st.rerun()
        with fb_col2:
            if st.button("👎 Incorrect"):
                call_feedback(result["query_id"], False, corrected_sql, comment, promote)
                st.session_state.feedback_sent = True
                st.rerun()
