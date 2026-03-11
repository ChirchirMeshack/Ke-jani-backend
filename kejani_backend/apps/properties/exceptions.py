class SubscriptionLimitError(Exception):
    """
    Raised by services when a landlord tries to exceed their plan limits.
    Views catch this and return a structured 403 response.

    Frontend uses `upgrade_url` to redirect to the billing page.
    """
    def __init__(self, resource, current, limit, plan_name, upgrade_url="/billing/upgrade"):
        self.resource    = resource     # "units" or "properties"
        self.current     = current      # how many they have now
        self.limit       = limit        # their plan limit
        self.plan_name   = plan_name    # e.g. "Solo"
        self.upgrade_url = upgrade_url
        super().__init__(
            f"You have reached the {limit} {resource} limit on your {plan_name} plan."
        )

    def to_response_dict(self):
        """Returns the dict sent to the frontend in the 403 response body."""
        return {
            "error":       "subscription_limit_reached",
            "resource":    self.resource,
            "current":     self.current,
            "limit":       self.limit,
            "plan":        self.plan_name,
            "message":     str(self),
            "upgrade_url": self.upgrade_url,
        }
