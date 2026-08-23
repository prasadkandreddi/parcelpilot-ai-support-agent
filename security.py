def get_user_context(
    role,
    account
):

    account = account.strip()

    # Customer

    if role == "customer":

        return {

            "role": "customer",

            "account_scope":
                account,

            "can_access_all_accounts":
                False

        }

    # Internal users

    return {

        "role": role,

        "account_scope":
            "ALL_ACCOUNTS",

        "can_access_all_accounts":
            True

    }