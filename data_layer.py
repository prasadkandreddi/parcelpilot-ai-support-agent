from pathlib import Path

import re

import pandas as pd


class DataStore:

    def __init__(
        self,
        path
    ):

        self.path = Path(path)

        self.tables = {}

        self.sheets = []

        self.dataset_time = (
            "Not available"
        )

        if self.path.exists():

            self.load()

        else:

            print(
                f"Excel file not found: {self.path}"
            )


    # =====================================================
    # LOAD EXCEL
    # =====================================================

    def load(self):

        excel_file = pd.ExcelFile(
            self.path
        )

        self.sheets = (
            excel_file.sheet_names
        )


        for sheet in self.sheets:

            df = pd.read_excel(

                self.path,

                sheet_name=sheet

            )

            df.columns = [

                str(column).strip()

                for column in df.columns

            ]

            self.tables[sheet] = df


        # Find snapshot information

        if "README" in self.tables:

            readme = self.tables["README"]

            text = readme.to_string(
                index=False
            )

            self.dataset_time = text


    # =====================================================
    # FIND COLUMN
    # =====================================================

    def find_column(
        self,
        dataframe,
        candidates
    ):

        columns = {

            str(column).lower():
                column

            for column
            in dataframe.columns

        }


        for candidate in candidates:

            if candidate.lower() in columns:

                return columns[
                    candidate.lower()
                ]


        return None


    # =====================================================
    # ACCOUNT ACCESS CONTROL
    # =====================================================

    def apply_access_control(
        self,
        dataframe,
        user_context
    ):
        """
        Enforce account-level access before any structured-data
        result is returned to the model.

        Customer context is normally provided as an account name
        (for example, "Northstar Logistics"), while operational
        tables such as orders and tickets use account_id
        (for example, "ACCT-001"). Resolve the customer name through
        the accounts table before filtering.
        """

        # Internal ParcelPilot users can access all accounts.
        if user_context["can_access_all_accounts"]:
            return dataframe

        requested_account = (
            str(user_context["account_scope"])
            .strip()
            .lower()
        )

        # ---------------------------------------------------------
        # Resolve account name -> account_id
        # ---------------------------------------------------------
        account_id = None

        accounts_df = self.tables.get("accounts")

        if accounts_df is not None and not accounts_df.empty:

            name_column = self.find_column(
                accounts_df,
                [
                    "account_name",
                    "customer_name",
                    "customer",
                    "account"
                ]
            )

            id_column = self.find_column(
                accounts_df,
                [
                    "account_id",
                    "customer_id"
                ]
            )

            if name_column and id_column:

                names = (
                    accounts_df[name_column]
                    .astype(str)
                    .str.strip()
                    .str.lower()
                )

                exact_match = accounts_df.loc[
                    names == requested_account
                ]

                if not exact_match.empty:
                    account_id = str(
                        exact_match.iloc[0][id_column]
                    ).strip().lower()

                else:
                    # Safe partial-name fallback, e.g.
                    # "Northstar" -> "Northstar Logistics".
                    partial_match = accounts_df.loc[
                        names.str.contains(
                            re.escape(requested_account),
                            na=False
                        )
                    ]

                    if len(partial_match) == 1:
                        account_id = str(
                            partial_match.iloc[0][id_column]
                        ).strip().lower()

        # ---------------------------------------------------------
        # Determine which account column this table uses.
        # Prefer account_id because orders/tickets use it.
        # ---------------------------------------------------------
        account_column = self.find_column(
            dataframe,
            [
                "account_id",
                "customer_id",
                "account_name",
                "customer_name",
                "account",
                "customer"
            ]
        )

        # If a customer-scoped table has no account identifier,
        # expose nothing rather than risk leaking data.
        if account_column is None:
            return dataframe.iloc[0:0]

        values = (
            dataframe[account_column]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        # ---------------------------------------------------------
        # Match resolved account ID
        # ---------------------------------------------------------
        if account_id:
            mask = values == account_id

            if mask.any():
                return dataframe.loc[mask]

        # ---------------------------------------------------------
        # Fallback for tables that store account name instead
        # of account ID.
        # ---------------------------------------------------------
        name_column = self.find_column(
            dataframe,
            [
                "account_name",
                "customer_name",
                "customer",
                "account"
            ]
        )

        if name_column:
            name_values = (
                dataframe[name_column]
                .astype(str)
                .str.strip()
                .str.lower()
            )

            mask = name_values == requested_account

            if mask.any():
                return dataframe.loc[mask]

        # Safe default: no matching account = no data.
        return dataframe.iloc[0:0]


    # =====================================================
    # STRUCTURED DATA LOOKUP
    # =====================================================

    def lookup(
        self,
        request,
        user_context
    ):

        if not self.tables:

            return (
                "No ParcelPilot Excel data "
                "is available."
            )


        request_lower = (
            request.lower()
        )


        results = []


        # Extract IDs such as ORD-1001

        ids = re.findall(

            r"\b(?:ord|tkt|ticket|order)"
            r"[-_]?\d+\b",

            request_lower

        )


        for sheet_name, dataframe in (
            self.tables.items()
        ):

            # README isn't operational data

            if sheet_name.lower() == "readme":

                continue


            dataframe = self.apply_access_control(

                dataframe,

                user_context

            )


            if dataframe.empty:

                continue


            result = dataframe.copy()


            # -----------------------------------------
            # Search by IDs
            # -----------------------------------------

            if ids:

                mask = pd.Series(

                    False,

                    index=result.index

                )


                for identifier in ids:

                    digits = re.sub(

                        r"\D",

                        "",

                        identifier

                    )


                    for column in result.columns:

                        values = (

                            result[column]
                            .astype(str)
                            .str.lower()

                        )


                        mask = (

                            mask

                            |

                            values.str.contains(

                                digits,

                                na=False

                            )

                        )


                result = result.loc[
                    mask
                ]


            # -----------------------------------------
            # Keyword search
            # -----------------------------------------

            else:

                words = re.findall(

                    r"[a-zA-Z0-9_-]{3,}",

                    request_lower

                )


                ignored_words = {

                    "find",

                    "show",

                    "what",

                    "with",

                    "from",

                    "about",

                    "should",

                    "please",

                    "tell",

                    "give"

                }


                words = [

                    word

                    for word in words

                    if word not in ignored_words

                ]


                if words:

                    mask = pd.Series(

                        False,

                        index=result.index

                    )


                    for column in result.columns:

                        values = (

                            result[column]
                            .astype(str)
                            .str.lower()

                        )


                        for word in words[:8]:

                            mask = (

                                mask

                                |

                                values.str.contains(

                                    re.escape(word),

                                    na=False

                                )

                            )


                    filtered = result.loc[
                        mask
                    ]


                    if not filtered.empty:

                        result = filtered


            if not result.empty:

                results.append(

                    f"SHEET: {sheet_name}\n"

                    +

                    result.head(20).to_json(

                        orient="records",

                        date_format="iso"

                    )

                )


        if not results:

            return (
                "No matching records were found "
                "within the user's permitted data scope."
            )


        return "\n\n".join(
            results[:6]
        )


    # =====================================================
    # CALCULATOR
    # =====================================================

    def calculate(
        self,
        request,
        user_context
    ):

        text = request.lower()


        # Three hours

        if "three hours" in text:

            return (
                "3 hours = 180 minutes."
            )


        # Hours to minutes

        hours_match = re.search(

            r"(\d+(?:\.\d+)?)\s*hours?",

            text

        )


        if hours_match:

            hours = float(
                hours_match.group(1)
            )

            return (
                f"{hours} hours = "
                f"{hours * 60} minutes."
            )


        # Simple arithmetic

        expression = re.sub(

            r"[^0-9+\-*/(). ]",

            "",

            request

        )


        if expression.strip():

            try:

                result = eval(

                    expression,

                    {
                        "__builtins__":
                            {}
                    }

                )

                return str(result)

            except Exception:

                pass


        return (
            "I need a specific numerical "
            "calculation to calculate this."
        )


    # =====================================================
    # PROACTIVE ISSUE DETECTION
    # =====================================================

    def issue_detection(
        self
    ):

        tickets = None


        # Find ticket sheet dynamically

        for sheet_name, dataframe in (
            self.tables.items()
        ):

            columns = " ".join(

                str(column)

                for column
                in dataframe.columns

            ).lower()


            if "ticket" in columns:

                tickets = dataframe

                break


        if tickets is None:

            return {

                "sla_risk":
                    pd.DataFrame(),

                "recurring":
                    pd.DataFrame(),

                "multi_customer":
                    pd.DataFrame()

            }


        df = tickets.copy()


        # -------------------------------------------------
        # Severity
        # -------------------------------------------------

        severity_column = self.find_column(

            df,

            [

                "severity",

                "priority",

                "ticket_priority"

            ]

        )


        # -------------------------------------------------
        # SLA
        # -------------------------------------------------

        sla_column = self.find_column(

            df,

            [

                "sla_due",

                "sla_deadline",

                "due_at",

                "resolution_due"

            ]

        )


        sla_risk = pd.DataFrame()


        if sla_column:

            dates = pd.to_datetime(

                df[sla_column],

                errors="coerce"

            )


            now = pd.Timestamp(
                "2026-08-16 11:00:00"
            )


            mask = (

                dates.notna()

                &

                (

                    dates
                    <=
                    now + pd.Timedelta(
                        hours=4
                    )

                )

            )


            sla_risk = df.loc[
                mask
            ].copy()


        # -------------------------------------------------
        # RECURRING ISSUES
        # -------------------------------------------------

        issue_column = self.find_column(

            df,

            [

                "issue",

                "issue_type",

                "category",

                "subject",

                "problem"

            ]

        )


        recurring = pd.DataFrame()


        if issue_column:

            counts = (

                df[
                    issue_column
                ]
                .astype(str)
                .value_counts()
                .reset_index()

            )


            counts.columns = [

                "issue",

                "ticket_count"

            ]


            recurring = counts[
                counts[
                    "ticket_count"
                ] >= 2
            ]


        # -------------------------------------------------
        # MULTI-CUSTOMER
        # -------------------------------------------------

        multi_customer = (
            pd.DataFrame()
        )


        account_column = self.find_column(

            df,

            [

                "account",

                "account_name",

                "customer",

                "customer_name"

            ]

        )


        if issue_column and account_column:

            grouped = (

                df.groupby(
                    issue_column
                )[account_column]
                .nunique()
                .reset_index()

            )


            grouped.columns = [

                "issue",

                "customer_count"

            ]


            multi_customer = (

                grouped[
                    grouped[
                        "customer_count"
                    ] >= 2
                ]
                .sort_values(
                    "customer_count",
                    ascending=False
                )

            )


        return {

            "sla_risk":
                sla_risk,

            "recurring":
                recurring,

            "multi_customer":
                multi_customer

        }