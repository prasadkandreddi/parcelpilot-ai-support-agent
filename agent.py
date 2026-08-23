import json

from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage
)

from langchain_core.tools import tool

from actions import prepare_escalation

from prompts import SYSTEM_PROMPT


# =========================================================
# CLEAN GEMINI RESPONSE
# =========================================================

def clean_response_content(content):
    """
    Gemini may return content as:

    [
        {
            "type": "text",
            "text": "..."
        }
    ]

    Convert that into normal readable text.
    """

    if content is None:
        return ""

    # Normal string response
    if isinstance(content, str):
        return content.strip()

    # Gemini content blocks
    if isinstance(content, list):

        text_parts = []

        for item in content:

            # Example:
            # {"type": "text", "text": "hello"}

            if isinstance(item, dict):

                if item.get("type") == "text":

                    text = item.get(
                        "text",
                        ""
                    )

                    if text:
                        text_parts.append(
                            text
                        )

            elif isinstance(item, str):

                text_parts.append(item)

        return "\n\n".join(
            text_parts
        ).strip()

    return str(content).strip()


# =========================================================
# CLEAN SOURCE LIST
# =========================================================

def clean_sources(sources):

    unique_sources = []

    seen = set()

    for source in sources:

        if not isinstance(source, dict):
            continue

        name = source.get(
            "source",
            "Unknown source"
        )

        page = source.get(
            "page",
            ""
        )

        key = (
            str(name),
            str(page)
        )

        if key not in seen:

            seen.add(key)

            unique_sources.append(
                source
            )

    return unique_sources


# =========================================================
# BUILD AGENT
# =========================================================

def build_agent(
    retriever,
    data
):

    # -----------------------------------------------------
    # GEMINI
    # -----------------------------------------------------

    llm = ChatGoogleGenerativeAI(

        model="gemini-2.5-flash",

        temperature=0

    )


    # =====================================================
    # CREATE TOOLS
    # =====================================================

    def make_tools(
        user_context,
        on_tool=None
    ):

        # -------------------------------------------------
        # TOOL LOGGER
        # -------------------------------------------------

        def log(tool_name):

            if on_tool:

                on_tool(
                    tool_name
                )


        # =================================================
        # TOOL 1
        # DOCUMENT SEARCH
        # =================================================

        @tool
        def document_search(
            query: str
        ) -> str:

            """
            Search ParcelPilot policies,
            customer agreements, SOPs,
            product documentation and known issues.
            """

            log(
                "document_search"
            )

            try:

                result = retriever.search(

                    query,

                    user_context

                )

                return result

            except Exception as error:

                return json.dumps({

                    "error":
                        f"Document search failed: {error}",

                    "context":
                        "",

                    "sources":
                        []

                })


        # =================================================
        # TOOL 2
        # STRUCTURED DATA
        # =================================================

        @tool
        def structured_data_lookup(
            request: str
        ) -> str:

            """
            Search ParcelPilot accounts,
            orders and tickets.

            Customer access is restricted to
            the user's own account.
            """

            log(
                "structured_data_lookup"
            )

            try:

                result = data.lookup(

                    request,

                    user_context

                )

                return result

            except Exception as error:

                return (
                    "Structured data lookup failed: "
                    f"{error}"
                )


        # =================================================
        # TOOL 3
        # CALCULATOR
        # =================================================

        @tool
        def calculate(
            expression_or_request: str
        ) -> str:

            """
            Perform deterministic calculations.
            """

            log(
                "calculate"
            )

            try:

                result = data.calculate(

                    expression_or_request,

                    user_context

                )

                return str(result)

            except Exception as error:

                return (
                    "Calculation failed: "
                    f"{error}"
                )


        # =================================================
        # TOOL 4
        # ESCALATION
        # =================================================

        @tool
        def create_escalation(
            ticket_id: str,
            reason: str,
            priority: str = "high"
        ) -> str:

            """
            Prepare a support escalation.

            IMPORTANT:
            This tool ONLY prepares the escalation.

            It does NOT execute the action.

            The user must explicitly confirm
            the action in the Streamlit UI.
            """

            log(
                "create_escalation"
            )

            try:

                return prepare_escalation(

                    ticket_id,

                    reason,

                    priority,

                    user_context

                )

            except Exception as error:

                return json.dumps({

                    "status":
                        "error",

                    "message":
                        f"Could not prepare escalation: {error}"

                })


        return [

            document_search,

            structured_data_lookup,

            calculate,

            create_escalation

        ]


    # =====================================================
    # AGENT INVOKE
    # =====================================================

    def invoke(
        question,
        user_context,
        on_tool=None
    ):

        tools = make_tools(

            user_context,

            on_tool

        )

        # Give Gemini access to tools

        llm_with_tools = llm.bind_tools(
            tools
        )


        # -------------------------------------------------
        # SYSTEM PROMPT
        # -------------------------------------------------

        system_message = SYSTEM_PROMPT.format(

            role=
                user_context["role"],

            account_scope=
                user_context["account_scope"],

            dataset_time=
                data.dataset_time

        )


        messages = [

            SystemMessage(
                content=system_message
            ),

            HumanMessage(
                content=question
            )

        ]


        sources = []

        pending_action = None


        # =================================================
        # TOOL LOOP
        # =================================================

        for iteration in range(8):

            try:

                response = llm_with_tools.invoke(
                    messages
                )

            except Exception as error:

                return {

                    "answer":
                        "I encountered an error while "
                        "processing your request. "
                        "Please try again.",

                    "sources":
                        sources,

                    "pending_action":
                        pending_action,

                    "error":
                        str(error)

                }


            # Add Gemini response

            messages.append(
                response
            )


            # =================================================
            # FINAL ANSWER
            # =================================================

            if not response.tool_calls:

                answer = clean_response_content(
                    response.content
                )


                if not answer:

                    answer = (
                        "I could not generate a reliable "
                        "answer from the available information."
                    )


                return {

                    "answer":
                        answer,

                    "sources":
                        clean_sources(
                            sources
                        ),

                    "pending_action":
                        pending_action

                }


            # =================================================
            # TOOL EXECUTION
            # =================================================

            available_tools = {

                tool_obj.name:
                    tool_obj

                for tool_obj in tools

            }


            for tool_call in response.tool_calls:

                tool_name = tool_call.get(
                    "name"
                )

                tool_arguments = tool_call.get(
                    "args",
                    {}
                )


                # -------------------------------------------------
                # UNKNOWN TOOL
                # -------------------------------------------------

                if tool_name not in available_tools:

                    result = (
                        f"Unknown tool requested: "
                        f"{tool_name}"
                    )

                    messages.append(

                        ToolMessage(

                            content=result,

                            tool_call_id=
                                tool_call["id"]

                        )

                    )

                    continue


                selected_tool = (
                    available_tools[
                        tool_name
                    ]
                )


                # -------------------------------------------------
                # RUN TOOL
                # -------------------------------------------------

                try:

                    result = selected_tool.invoke(
                        tool_arguments
                    )

                except Exception as error:

                    result = (
                        f"Tool {tool_name} failed: "
                        f"{error}"
                    )


                # Convert result to string

                if not isinstance(
                    result,
                    str
                ):

                    result = str(
                        result
                    )


                # =================================================
                # DOCUMENT SOURCES
                # =================================================

                if tool_name == "document_search":

                    try:

                        parsed = json.loads(
                            result
                        )


                        found_sources = (
                            parsed.get(
                                "sources",
                                []
                            )
                        )


                        if isinstance(
                            found_sources,
                            list
                        ):

                            sources.extend(
                                found_sources
                            )


                    except Exception:

                        pass


                # =================================================
                # ESCALATION
                # =================================================

                if tool_name == "create_escalation":

                    try:

                        parsed = json.loads(
                            result
                        )


                        if (
                            parsed.get(
                                "status"
                            )
                            ==
                            "confirmation_required"
                        ):

                            pending_action = (
                                parsed.get(
                                    "action"
                                )
                            )


                    except Exception:

                        pass


                # =================================================
                # SEND TOOL RESULT BACK TO GEMINI
                # =================================================

                messages.append(

                    ToolMessage(

                        content=result,

                        tool_call_id=
                            tool_call["id"]

                    )

                )


        # =================================================
        # SAFETY FALLBACK
        # =================================================

        return {

            "answer":
                """
### ⚠️ Unable to Complete Safely

I could not complete the investigation confidently
within the available information.

Please review the request with a ParcelPilot
support specialist.
""",

            "sources":
                clean_sources(
                    sources
                ),

            "pending_action":
                pending_action

        }


    # =====================================================
    # RETURN AGENT OBJECT
    # =====================================================

    return type(

        "ParcelPilotAgent",

        (),

        {

            "invoke":
                staticmethod(invoke)

        }

    )()