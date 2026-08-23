import streamlit as st
from dotenv import load_dotenv

from agent import build_agent
from security import get_user_context
from rag import build_or_load_retriever
from data_layer import DataStore
from actions import execute_escalation

load_dotenv()

st.set_page_config(
    page_title="ParcelPilot AI Support",
    page_icon="🚚",
    layout="wide"
)


@st.cache_resource
def load_system():

    data = DataStore(
        "data/ParcelPilot_Assessment_Data.xlsx"
    )

    retriever = build_or_load_retriever(
        "documents",
        "storage"
    )

    agent = build_agent(
        retriever,
        data
    )

    return data, retriever, agent


data, retriever, agent = load_system()


if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_action" not in st.session_state:
    st.session_state.pending_action = None

if "tool_log" not in st.session_state:
    st.session_state.tool_log = []


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.title("🚚 ParcelPilot")

    st.caption(
        "AI Support & Operations Agent"
    )

    st.divider()

    role = st.selectbox(
        "User Role",
        [
            "customer",
            "support_agent",
            "operations"
        ]
    )

    account = st.text_input(
        "Customer Account",
        value="Northstar Logistics"
    )

    user = get_user_context(
        role,
        account
    )

    st.divider()

    st.subheader("👤 User Context")

    st.write(
        f"**Role:** {user['role']}"
    )

    st.write(
        f"**Account:** {user['account_scope']}"
    )

    st.divider()

    st.subheader("🔎 System Information")

    st.write(
        f"Documents indexed: **{retriever.document_count}**"
    )

    st.write(
        f"Excel sheets: **{len(data.sheets)}**"
    )

    st.write(
        f"Dataset snapshot: **{data.dataset_time}**"
    )

    st.divider()

    st.subheader("🛠 Tool Activity")

    if st.session_state.tool_log:

        for item in st.session_state.tool_log[-10:]:
            st.caption(item)

    else:

        st.caption(
            "Tools used by the agent will appear here."
        )

    st.divider()

    st.subheader("💡 Demo Questions")

    demo_questions = [

        "Can Northstar cancel ORD-1001 without a cancellation fee? Explain why.",

        "A pickup is three hours late because of carrier fault. Should I get a service credit?",

        "Find high-severity tickets that are close to or beyond SLA.",

        "What are the current P1 response targets for Northstar?",

        "What is the current cancellation policy?"
    ]

    for question in demo_questions:

        if st.button(
            question,
            use_container_width=True
        ):

            st.session_state.demo_question = question

    st.divider()

    if st.button(
        "🗑 Clear Chat",
        use_container_width=True
    ):

        st.session_state.messages = []
        st.session_state.pending_action = None
        st.session_state.tool_log = []

        st.rerun()


# =========================================================
# MAIN
# =========================================================

st.title(
    "🚚 ParcelPilot AI Support"
)

st.caption(
    "Grounded AI support using ParcelPilot policies, "
    "customer agreements and operational data."
)


chat_tab, operations_tab = st.tabs(
    [
        "💬 Support Chat",
        "📊 Operations Intelligence"
    ]
)


# =========================================================
# SUPPORT CHAT
# =========================================================

with chat_tab:

    st.subheader(
        "Ask ParcelPilot Support"
    )

    st.info(
        "The AI uses document retrieval and structured "
        "operational data to investigate your question."
    )

    # Display history

    for message in st.session_state.messages:

        with st.chat_message(
            message["role"]
        ):

            st.markdown(
                message["content"]
            )

    question = st.chat_input(
        "Ask a ParcelPilot support question..."
    )

    if "demo_question" in st.session_state:

        question = st.session_state.demo_question

        del st.session_state.demo_question

    if question:

        st.session_state.messages.append(
            {
                "role": "user",
                "content": question
            }
        )

        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):

            with st.spinner(
                "🔍 Investigating ParcelPilot data..."
            ):

                try:

                    result = agent.invoke(

                        question,

                        user_context=user,

                        on_tool=lambda tool_name:
                            st.session_state.tool_log.append(
                                f"🛠 Used tool: {tool_name}"
                            )
                    )

                    answer = result.get(
                        "answer",
                        "I could not generate an answer."
                    )

                    st.markdown(answer)

                    sources = result.get(
                        "sources",
                        []
                    )

                    if sources:

                        with st.expander(
                            "📚 Sources / Evidence"
                        ):

                            for source in sources:

                                st.write(
                                    f"**{source.get('source', 'Unknown')}**"
                                )

                                st.caption(
                                    f"Type: {source.get('type', 'unknown')} | "
                                    f"Status: {source.get('status', 'unknown')}"
                                )

                    if result.get("pending_action"):

                        st.session_state.pending_action = (
                            result["pending_action"]
                        )

                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": answer
                        }
                    )

                except Exception as error:

                    st.error(
                        "Agent error occurred."
                    )

                    st.exception(error)


# =========================================================
# CONFIRMATION
# =========================================================

if st.session_state.pending_action:

    action = st.session_state.pending_action

    st.warning(
        f"""
### ⚠️ Confirmation Required

**Action:** `{action.get('type', 'Unknown')}`

**Ticket:** `{action.get('ticket_id', 'Unknown')}`

**Priority:** `{action.get('priority', 'Unknown')}`

**Reason:**

{action.get('reason', 'No reason provided.')}

The action will NOT be executed until you confirm.
"""
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "✅ Confirm & Execute",
            type="primary",
            use_container_width=True
        ):

            try:

                result = execute_escalation(
                    action,
                    user
                )

                st.success(result)

                st.session_state.pending_action = None

                st.session_state.tool_log.append(
                    "✅ Escalation executed"
                )

                st.rerun()

            except Exception as error:

                st.error(
                    f"Action failed: {error}"
                )

    with col2:

        if st.button(
            "❌ Cancel Action",
            use_container_width=True
        ):

            st.session_state.pending_action = None

            st.info(
                "Action cancelled."
            )

            st.rerun()


# =========================================================
# OPERATIONS INTELLIGENCE
# =========================================================

with operations_tab:

    st.subheader(
        "📊 Operations Intelligence"
    )

    st.caption(
        "Internal support and operations view."
    )

    if role == "customer":

        st.error(
            "🔒 Access denied. Operations Intelligence "
            "is available only to authorised ParcelPilot employees."
        )

    else:

        try:

            dashboard = data.issue_detection()

            # SLA

            st.markdown(
                "### 🚨 SLA Risk"
            )

            sla_data = dashboard.get(
                "sla_risk"
            )

            if sla_data is not None and len(sla_data) > 0:

                st.dataframe(
                    sla_data,
                    use_container_width=True
                )

            else:

                st.success(
                    "No immediate SLA-risk tickets detected."
                )

            # Recurring

            st.markdown(
                "### 🔁 Recurring Issues"
            )

            recurring_data = dashboard.get(
                "recurring"
            )

            if recurring_data is not None and len(recurring_data) > 0:

                st.dataframe(
                    recurring_data,
                    use_container_width=True
                )

            else:

                st.info(
                    "No recurring issue patterns detected."
                )

            # Multi customer

            st.markdown(
                "### 🌐 Multi-Customer Issues"
            )

            multi_customer_data = dashboard.get(
                "multi_customer"
            )

            if (
                multi_customer_data is not None
                and len(multi_customer_data) > 0
            ):

                st.dataframe(
                    multi_customer_data,
                    use_container_width=True
                )

            else:

                st.info(
                    "No multi-customer issue signals detected."
                )

            # Data

            st.divider()

            st.markdown(
                "### 📚 Available Operational Data"
            )

            for sheet_name, dataframe in data.tables.items():

                st.write(
                    f"**{sheet_name}** — "
                    f"{len(dataframe)} rows × "
                    f"{len(dataframe.columns)} columns"
                )

        except Exception as error:

            st.error(
                "Could not load Operations Intelligence."
            )

            st.exception(error)