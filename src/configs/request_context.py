from contextvars import ContextVar

# Holds the Bearer token for the current request.
# Set in main.py before graph invocation, read in call_api().
bearer_token_var: ContextVar[str] = ContextVar("bearer_token", default="")


def propagate_auth_token(config) -> None:
    """Copy auth token from LangGraph Server config into bearer_token_var.

    LangGraph Server puts the validated token in
    config["configurable"]["langgraph_auth_user"]["token"].
    Downstream code (get_llm, claims_client) reads bearer_token_var.
    This bridges the two.  Called once at graph entry.
    """
    if bearer_token_var.get():
        return
    auth_user = (config or {}).get("configurable", {}).get("langgraph_auth_user")
    if isinstance(auth_user, dict) and auth_user.get("token"):
        bearer_token_var.set(auth_user["token"])
